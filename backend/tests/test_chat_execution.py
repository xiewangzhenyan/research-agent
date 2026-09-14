"""Fast contracts for chat routing, recoverable streaming and bounded context."""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from pydantic import ValidationError
from pydantic_ai import PartDeltaEvent, PartStartEvent
from pydantic_ai.messages import (
    TextPart,
    TextPartDelta,
    ThinkingPart,
    ThinkingPartDelta,
    ToolCallPart,
)

from app.schemas.chat_turn import ChatTurnCreate
from app.services import chat_execution as chat
from app.services.model_config import resolve_generation_config


def request(**overrides):
    return {
        "prompt": "Compare multiple sources and review their conclusions",
        "knowledge_base_ids": [str(uuid4())],
        "knowledge_strict": True,
        "knowledge_document_ids": None,
        "file_ids": [],
        **overrides,
    }


@pytest.mark.anyio
@pytest.mark.parametrize(
    "overrides",
    [
        {"knowledge_base_ids": []},
        {"knowledge_strict": False},
        {"knowledge_document_ids": [str(uuid4())]},
        {"file_ids": [str(uuid4())]},
        {"prompt": "Define LSPR"},
    ],
)
async def test_direct_questions_and_restricted_scopes_never_invoke_router(overrides):
    with patch.object(chat, "Agent") as agent:
        result = await chat.choose_route(request(**overrides), {}, resolve_generation_config({}))
    assert result["route"] == "standard"
    agent.assert_not_called()


@pytest.mark.anyio
@pytest.mark.parametrize("outcome", ["high", "uncertain", "standard", "failure"])
async def test_collaboration_requires_confident_decision_and_model_failure_falls_back(outcome):
    agent = MagicMock()
    agent.run = AsyncMock()
    if outcome == "failure":
        agent.run.side_effect = TimeoutError("provider unavailable")
    else:
        agent.run.return_value = SimpleNamespace(
            output=chat.RouteChoice(
                route="standard" if outcome == "standard" else "knowledge_collaboration",
                confidence="uncertain" if outcome == "uncertain" else "high",
                reason="Several independent comparisons",
            )
        )
    data = request()
    with patch.object(chat, "Agent", return_value=agent), patch.object(chat, "_build_model"):
        result = await chat.choose_route(
            data, {"query": data["prompt"]}, resolve_generation_config({})
        )
    assert result["route"] == ("knowledge_collaboration" if outcome == "high" else "standard")
    assert "tools" not in result and "knowledge_base_ids" not in result
    assert agent.run.await_args.kwargs["usage_limits"].request_limit == 1


@pytest.mark.anyio
async def test_progress_coalesces_tokens_and_keeps_final_text_thinking_and_tool_result():
    emit = AsyncMock()
    progress = chat.ChatProgress(emit)
    with patch.object(chat.time, "monotonic", return_value=10):
        await progress.handle(PartStartEvent(index=0, part=TextPart(content="Hello")))
    assert emit.await_count == 1
    with patch.object(chat.time, "monotonic", return_value=10.1):
        await progress.handle(PartDeltaEvent(index=0, delta=TextPartDelta(content_delta=" world")))
        await progress.handle(PartStartEvent(index=1, part=ThinkingPart(content="Check")))
        await progress.handle(
            PartDeltaEvent(index=1, delta=ThinkingPartDelta(content_delta=" facts"))
        )
        await progress.handle(
            SimpleNamespace(
                event_kind="function_tool_call",
                part=ToolCallPart(tool_name="current_datetime", args={}, tool_call_id="clock"),
            )
        )
        await progress.handle(
            SimpleNamespace(
                event_kind="function_tool_result",
                part=SimpleNamespace(tool_call_id="clock", content={"timezone": "Asia/Shanghai"}),
            )
        )
        assert emit.await_count == 1
        await progress.flush()
    assert emit.await_args.args == (
        "chat_progress",
        {"content": "Hello world", "thinking": "Check facts"},
    )
    assert progress.calls["clock"]["result"] == '{"timezone": "Asia/Shanghai"}'
    progress.thinking = "x" * 150001
    with pytest.raises(ValueError):
        await progress.flush()
    assert emit.await_count == 2


@pytest.mark.anyio
async def test_context_keeps_complete_recent_messages_in_order_and_scopes_memory():
    uid, pid, cid, mid = uuid4(), uuid4(), uuid4(), uuid4()
    db = AsyncMock()
    memory = MagicMock()
    memory.recall = AsyncMock(return_value=[])
    recent = [
        {"role": "user", "content": "recent question"},
        {"role": "assistant", "content": "recent answer"},
    ]
    recalled_context = {
        "history": recent,
        "history_context": "",
        "rewrite_history": recent,
        "budgets": {"memory": 1600},
        "context_usage": {"estimated_input_tokens": 0},
    }

    @asynccontextmanager
    async def database():
        yield db

    data = request(conversation_id=str(cid), user_message_id=str(mid))
    with (
        patch.object(chat, "get_worker_db_context", database),
        patch(
            "app.services.conversation_context.recall", AsyncMock(return_value=recalled_context)
        ) as recall,
        patch.object(chat, "MemoryService", return_value=memory) as memory_constructor,
        patch.object(chat, "memory_context", return_value=""),
        patch.object(chat, "usage_record", return_value={}),
        patch.object(
            chat, "rewrite_query", AsyncMock(return_value=("resolved query", "rewritten"))
        ),
    ):
        config = resolve_generation_config({})
        context = await chat.prepare_context(data, uid, pid, config)
    assert context["history"] == recent
    assert context["query"] == "resolved query"
    assert context["memory_context"] == ""
    recall.assert_awaited_once_with(db, data, uid, pid, config)
    memory_constructor.assert_called_once_with(db, uid, project_id=pid)
    memory.recall.assert_awaited_once_with(data["prompt"], strict_knowledge=True)


@pytest.mark.anyio
async def test_python_attachments_are_not_loaded_twice_into_language_model_context():
    data = request(file_ids=[str(uuid4())], tools=["run_python"])
    with patch.object(chat, "get_worker_db_context") as database:
        text = await chat.chat_input(
            data, {"memory_context": "remember preference"}, uuid4(), None, []
        )
    database.assert_not_called()
    assert text == data["prompt"] + "remember preference"


@pytest.mark.parametrize(
    "data",
    [
        {"message": "  "},
        {"message": "x" * 30001},
        {"message": "hello", "mode": "knowledge_collaboration"},
    ],
)
def test_submission_rejects_empty_oversized_or_client_routed_requests(data):
    with pytest.raises(ValidationError):
        ChatTurnCreate(idempotency_key=uuid4(), **data)
