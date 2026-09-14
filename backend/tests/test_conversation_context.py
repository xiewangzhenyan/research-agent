"""Fast contracts for context budgeting, source extraction and topic boundaries."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.exceptions import BadRequestError
from app.schemas.conversation_context import ContextSummary
from app.services import context_budget as budget
from app.services.conversation_context import excerpt, lookup_query
from app.services.model_config import resolve_generation_config
from app.worker import conversation_context as worker


def test_current_question_and_output_reservation_are_not_silently_truncated():
    config = resolve_generation_config({})
    with (
        patch.dict(budget.settings.AI_MODEL_CONTEXT_LIMITS, {config.model: 8192}),
        pytest.raises(BadRequestError),
    ):
        budget.check_prompt("hello", config)
    with pytest.raises(BadRequestError):
        budget.check_prompt("数" * 30000, config)
    parts = budget.envelope(
        {"prompt": "回到做饭的话题", "file_ids": ["file"], "knowledge_base_ids": ["kb"]}, config
    )
    assert (
        sum(value for key, value in parts.items() if key != "input") + budget.cost("回到做饭的话题")
        <= parts["input"]
    )
    selected, used = budget.fit_items(["数" * 5000, "complete small source"], 100)
    assert selected == ["complete small source"] and used <= 100


def test_explicit_topic_change_does_not_inherit_a_different_task():
    history = [
        {"role": "user", "content": "如何计算定积分"},
        {"role": "assistant", "content": "数学回答"},
    ]
    assert lookup_query("做饭不放花生，请推荐菜谱", history) == "做饭不放花生，请推荐菜谱"
    assert lookup_query("继续解释", history) == "如何计算定积分\n继续解释"
    # Two games share a broad domain but remain separate explicit subjects.
    assert (
        lookup_query("崩铁怎么配队", [{"role": "user", "content": "原神怎么配队"}])
        == "崩铁怎么配队"
    )


def test_excerpt_preserves_original_characters_and_marks_recoverable_offset():
    text = "开头" * 2000 + "做饭不能放花生，过敏。" + "后面" * 2000
    passage, offset = excerpt(text, "做饭花生")
    assert "不能放花生" in passage
    assert text[offset : offset + len(passage)] == passage
    assert len(passage) == 1400


@pytest.mark.anyio
async def test_summaries_require_literal_sources_and_fall_back_on_failure():
    data = [{"source": 0, "role": "user", "text": "做饭不能放花生", "partial": False}]
    summary = ContextSummary.model_validate(
        {
            "notes": [
                {
                    "source": 0,
                    "kind": "constraint",
                    "topic": "做饭",
                    "summary": "忌花生",
                    "quote": "不能放花生",
                },
                {
                    "source": 0,
                    "kind": "constraint",
                    "topic": "金额",
                    "summary": "预算",
                    "quote": "预算五千元",
                },
                {
                    "source": 7,
                    "kind": "constraint",
                    "topic": "做饭",
                    "summary": "不存在",
                    "quote": "不能放花生",
                },
            ]
        }
    )
    assert len(worker.validated_notes(summary, data)) == 1
    agent = MagicMock()
    agent.run = AsyncMock(side_effect=TimeoutError)
    with patch.object(worker, "Agent", return_value=agent), patch.object(worker, "_build_model"):
        notes, mode, usage = await worker.summarize(
            data, resolve_generation_config({}).model_dump(), True
        )
    assert mode == "excerpt" and notes[0]["quote"] == data[0]["text"]
    assert usage["model_attempted"] is True
    assert agent.run.await_args.kwargs["usage_limits"].request_limit == 1
    with patch.object(worker, "Agent") as constructor:
        await worker.summarize(data, {}, False)
    constructor.assert_not_called()


@pytest.mark.anyio
async def test_summary_indexes_separate_source_roles_without_promoting_assistant_claims():
    data = [
        {"source": 0, "role": "user", "text": "任务需要核对原文", "partial": False},
        {"source": 1, "role": "assistant", "text": "我猜测已经确认了", "partial": False},
    ]
    notes, _, _ = await worker.summarize(data, {}, False)
    assert [n["source"] for n in notes] == [0, 1]
    assert notes[0]["kind"] == "question" and notes[1]["kind"] == "progress"


@pytest.mark.anyio
async def test_budget_guard_stops_tool_result_growth_before_second_provider_request():
    from pydantic_ai import Agent
    from pydantic_ai.messages import ModelResponse, ToolCallPart
    from pydantic_ai.models.function import FunctionModel

    calls = []

    def provider(messages, info):
        calls.append(messages)
        return ModelResponse(
            parts=[ToolCallPart(tool_name="large_result", args={}, tool_call_id="once")]
        )

    agent = Agent(FunctionModel(provider), retries=0)

    @agent.tool_plain
    def large_result() -> str:
        return "数据" * 20000

    validate = AsyncMock()
    with pytest.raises(BadRequestError):
        await agent.run(
            "调用工具",
            capabilities=[budget.ContextBudgetGuard(resolve_generation_config({}), validate)],
        )
    assert len(calls) == 1
    assert validate.await_count == 2
