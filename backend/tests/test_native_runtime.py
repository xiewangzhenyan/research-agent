"""Migration contracts: durable tool boundaries, legacy messages and bounded calls."""

import asyncio
import json
import os
from typing import TypedDict
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel

from app.agents.messages import dump_messages, load_messages
from app.agents.model import structured_call
from app.agents.runtime import ToolDeferred, ToolRegistry, reasoning_text, run_tools
from app.core.exceptions import BadRequestError, RateLimitError
from app.services.model_config import resolve_generation_config
from tests.model_fixtures import ScriptedModel, model_response, tool_call


class ParentState(TypedDict, total=False):
    prompt: str
    output: str


@pytest.fixture(params=["memory", "postgres"])
async def checkpoint(request):
    thread = f"native-runtime:{uuid4()}"
    if request.param == "memory":
        yield InMemorySaver(), thread
        return
    if os.getenv("RUN_TASK_DB_TESTS") != "1":
        pytest.skip("requires disposable database")
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

    from app.core.config import settings
    from app.worker.agent_runs import connect

    assert settings.POSTGRES_DB.endswith("_review")
    async with await connect() as conn:
        saver = AsyncPostgresSaver(conn)
        try:
            yield saver, thread
        finally:
            await saver.adelete_thread(thread)


@pytest.mark.anyio
@pytest.mark.parametrize("failure", ["model", "second_tool"])
async def test_rebuilt_parent_recovers_child_without_repeating_completed_tool(failure, checkpoint):
    effects, model_inputs = [], []
    healthy = False

    def model(messages, info):
        model_inputs.append(messages)
        if not any(isinstance(m, ToolMessage) for m in messages):
            return model_response(
                [
                    tool_call("record", {"value": "first"}, "first"),
                    tool_call("record", {"value": "second"}, "second"),
                ]
            )
        if not healthy and failure == "model":
            raise RuntimeError("model interrupted after tool checkpoint")
        return AIMessage(content="finished")

    saver, thread = checkpoint

    def rebuild():
        registry = ToolRegistry(ScriptedModel(model), resolve_generation_config({}))

        @registry.register_plain
        async def record(value: str) -> str:
            if value == "second" and failure == "second_tool" and not healthy:
                raise RuntimeError("second tool interrupted before effect")
            effects.append(value)
            return value

        async def generate(state):
            result = await run_tools(registry, state["prompt"])
            return {"output": result["output"]}

        graph = StateGraph(ParentState)
        graph.add_node("generate", generate)
        graph.add_edge(START, "generate")
        graph.add_edge("generate", END)
        return graph.compile(checkpointer=saver)

    config = {"configurable": {"thread_id": thread}}
    with pytest.raises(RuntimeError):
        await rebuild().ainvoke({"prompt": "record both"}, config)
    assert effects == (["first", "second"] if failure == "model" else ["first"])
    healthy = True
    result = await rebuild().ainvoke(None, config)
    assert result["output"] == "finished"
    assert effects == ["first", "second"]
    assert len(model_inputs) == (3 if failure == "model" else 2)


@pytest.mark.anyio
async def test_legacy_pending_question_resumes_and_roundtrips_without_old_runtime():
    legacy = json.dumps(
        [
            {"kind": "request", "parts": [{"part_kind": "user-prompt", "content": "research"}]},
            {
                "kind": "response",
                "parts": [
                    {
                        "part_kind": "tool-call",
                        "tool_name": "ask_user",
                        "args": {"questions": []},
                        "tool_call_id": "question",
                    }
                ],
            },
        ]
    )

    def model(messages, info):
        reply = messages[-1]
        assert isinstance(reply, ToolMessage)
        assert reply.tool_call_id == "question" and reply.name == "ask_user"
        assert reply.content == "Use public sources"
        return AIMessage(content="resumed")

    registry = ToolRegistry(ScriptedModel(model), resolve_generation_config({}))
    result = await run_tools(
        registry, None, history=load_messages(legacy), replies={"question": "Use public sources"}
    )
    assert result["output"] == "resumed"
    assert load_messages(dump_messages(result["messages"])) == result["messages"]


@pytest.mark.anyio
async def test_system_and_dynamic_instructions_count_towards_budget():
    calls = []
    registry = ToolRegistry(
        ScriptedModel(lambda m, i: calls.append(m)), resolve_generation_config({})
    )
    registry.instructions.append("技能内容" * 100000)
    with pytest.raises(BadRequestError, match="上下文预算"):
        await run_tools(registry, "hello")
    assert calls == []


@pytest.mark.anyio
async def test_unknown_tool_fails_before_any_effect():
    registry = ToolRegistry(
        ScriptedModel(lambda m, i: model_response([tool_call("unauthorized", {})])),
        resolve_generation_config({}),
    )
    with pytest.raises(BadRequestError, match="未授权"):
        await run_tools(registry, "hello")


@pytest.mark.anyio
async def test_cancellation_during_model_prevents_tool_dispatch():
    entered = asyncio.Event()
    effects = []

    async def model(messages, info):
        entered.set()
        await asyncio.Event().wait()
        return model_response([tool_call("effect", {})])

    registry = ToolRegistry(ScriptedModel(model), resolve_generation_config({}))

    @registry.register_plain
    async def effect() -> str:
        effects.append(True)
        return "done"

    task = asyncio.create_task(run_tools(registry, "hello"))
    await asyncio.wait_for(entered.wait(), 2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert effects == []


class Decision(BaseModel):
    accepted: bool


@pytest.mark.anyio
async def test_structured_validation_retries_are_bounded_and_revalidate_each_call():
    calls = []
    validate = AsyncMock()

    def model(messages, info):
        calls.append(messages)
        return model_response(
            [
                tool_call(
                    "Decision", {"accepted": "invalid"} if len(calls) == 1 else {"accepted": True}
                )
            ]
        )

    result = await structured_call(
        ScriptedModel(model),
        Decision,
        "classify",
        "hello",
        resolve_generation_config({}),
        retries=1,
        validate=validate,
    )
    assert result.output.accepted is True
    assert result.usage == {"requests": 2, "tool_calls": 0, "input_tokens": 2, "output_tokens": 2}
    assert validate.await_count == 2
    calls.clear()
    with pytest.raises(RateLimitError):
        await structured_call(
            ScriptedModel(model),
            Decision,
            "classify",
            "hello",
            resolve_generation_config({}),
            retries=4,
            request_limit=1,
        )
    assert len(calls) == 1


def test_responses_reasoning_summary_blocks_are_streamed():
    assert (
        reasoning_text(
            AIMessage(
                content=[
                    {
                        "type": "reasoning",
                        "summary": [{"type": "summary_text", "text": "Reviewing evidence"}],
                    }
                ]
            )
        )
        == "Reviewing evidence"
    )


def test_unsupported_legacy_parts_fail_closed():
    with pytest.raises(ValueError, match="Unsupported legacy"):
        load_messages([{"kind": "request", "parts": [{"part_kind": "unknown"}]}])


def test_native_image_budget_does_not_count_base64_as_text():
    from app.agents.messages import image_content
    from app.services.context_budget import request_cost

    message = HumanMessage(content=[image_content(b"x" * 200000, "image/png")])
    assert 2000 <= request_cost(message) < 2200


@pytest.mark.anyio
async def test_deferred_batch_resolves_remaining_calls_before_requesting_model():
    effects = []

    def model(messages, info):
        if not any(isinstance(m, ToolMessage) for m in messages):
            return model_response(
                [
                    tool_call("approval", {}, "approve"),
                    tool_call("lookup", {}, "lookup"),
                ]
            )
        assert {m.tool_call_id for m in messages if isinstance(m, ToolMessage)} == {
            "approve",
            "lookup",
        }
        return AIMessage(content="finished")

    registry = ToolRegistry(ScriptedModel(model), resolve_generation_config({}))

    @registry.register_plain
    async def approval() -> str:
        raise ToolDeferred(metadata={"questions": [{"question": "Allow?"}]})

    @registry.register_plain
    async def lookup() -> str:
        effects.append("lookup")
        return "found"

    paused = await run_tools(registry, "research")
    assert paused["pending"][0]["call_id"] == "approve" and effects == []
    result = await run_tools(
        registry,
        None,
        history=paused["messages"],
        usage=paused["usage"],
        replies={"approve": "decision recorded"},
    )
    assert result["output"] == "finished" and effects == ["lookup"]
    assert result["usage"]["requests"] == 2


@pytest.mark.anyio
async def test_malformed_streamed_tool_arguments_fail_before_dispatch():
    from tests.model_fixtures import tool_delta

    effects = []

    async def stream(messages, info):
        yield {0: tool_delta(name="lookup", json_args="{broken", tool_call_id="broken")}

    registry = ToolRegistry(ScriptedModel(stream_function=stream), resolve_generation_config({}))

    @registry.register_plain
    async def lookup() -> str:
        effects.append(True)
        return "found"

    with pytest.raises(BadRequestError, match="无效的工具调用"):
        await run_tools(registry, "research")
    assert effects == []
