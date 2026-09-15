"""Real durable checkpoints, mandatory inputs, evidence bounds and cancellation."""

import asyncio
import os
from unittest.mock import AsyncMock, patch

import pytest
from pydantic_ai.models.function import DeltaToolCall, FunctionModel

from app.core.exceptions import AlreadyExistsError, BadRequestError, NotFoundError
from app.db.session import get_worker_db_context
from app.repositories.agent_run import AgentRunRepository
from app.schemas.agent_run import AgentRunResume
from app.services.agent_run import AgentRunService
from app.services.clarification import END_EVIDENCE, RETRY_EVIDENCE, SKIP, ClarificationQuestion
from app.services.task_readiness import ReadinessAssessment
from app.worker.agent_runs import try_run
from tests.test_agent_runs_integration import get, users
from tests.test_durable_chat import state, submit
from tests.test_knowledge_collaboration import fixture, search_result
from tests.test_work_tasks import selection

pytestmark = pytest.mark.skipif(os.getenv("RUN_TASK_DB_TESTS") != "1", reason="disposable DB only")


def blocker(text="请选择待比较的范围"):
    return ReadinessAssessment(
        issues=[
            ClarificationQuestion(
                question=text,
                kind="ambiguity",
                reason="范围不同会改变结果",
                options=["A与B", "A与C"],
            )
        ]
    )


async def answer(uid, run, text):
    async with get_worker_db_context() as db:
        return await AgentRunService(db, uid).resume(
            run.id,
            AgentRunResume(
                question_id=run.pending_input["question_id"],
                answers={
                    c["call_id"]: [text] * len(c["questions"]) for c in run.pending_input["calls"]
                },
            ),
        )


def test_missing_inputs_stop_before_generation_and_survive_worker_reclaim():
    async def check():
        seen = []

        async def assess(request, context, config, answers, usage, validate):
            await validate()
            return (blocker() if not answers else ReadinessAssessment()), usage

        async def stream(messages, info):
            seen.append(str(messages))
            yield "范围已明确，可以继续。"

        async with users(real_readiness=True) as (a, b):
            with (
                patch(
                    "app.services.task_readiness.assess_with_model", side_effect=assess
                ) as assessment,
                patch(
                    "app.agents.assistant._build_model",
                    return_value=FunctionModel(stream_function=stream),
                ),
            ):
                turn = await submit(a, message="比较这些方案")
                await try_run(turn.id)
                waiting = await get(a, turn.id)
                assert waiting.status == "waiting_input", waiting.error
                assert not seen and waiting.pending_input["calls"][0]["questions"][0]["required"]
                await try_run(turn.id)  # another worker/browser absence never starts generation
                assert assessment.await_count == 1
                with pytest.raises(NotFoundError):
                    await answer(b, waiting, "A与B")
                for skipped in (SKIP, "不知道", "随便"):
                    with pytest.raises(BadRequestError):
                        await answer(a, waiting, skipped)
                assert (await get(a, turn.id)).status == "waiting_input"
                next_turn = await submit(
                    a, conversation_id=turn.conversation_id, message="继续解释"
                )
                resumed = await answer(a, waiting, "A与B")
                duplicate = await answer(a, waiting, "A与B")
                assert resumed.id == duplicate.id
                await try_run(turn.id)
                saved = await get(a, turn.id)
                assert saved.status == "completed", saved.error
                assert len(seen) == 1 and "A与B" in seen[0]
                assert assessment.await_count == 2
                transcript = await state(a, turn.conversation_id)
                supplements = [
                    m
                    for m in transcript["messages"]
                    if m.role == "user" and m.content.startswith("补充信息：")
                ]
                assert len(supplements) == 1 and "A与B" in supplements[0].content
                assert transcript["messages"][-1].role == "assistant"
                from app.services.chat_execution import prepare_context
                from app.services.model_config import resolve_generation_config

                context = await prepare_context(
                    next_turn.request, a, None, resolve_generation_config({})
                )
                assert any(
                    "A与B" in m["content"] for m in context["history"] if m["role"] == "user"
                )
                async with get_worker_db_context() as db:
                    audit = [
                        e
                        for e in await AgentRunRepository(db).events(turn.id, 0)
                        if e.kind == "clarification_answered"
                    ]
                    assert len(audit) == 1 and audit[0].data["items"][0]["answer"] == "A与B"

    asyncio.run(check())


def test_incomplete_answer_is_rechecked_new_question_ids_and_bounded_stop():
    async def check():
        async def assess(request, context, config, answers, usage, validate):
            return blocker("仍缺少关键范围"), usage

        async with users(real_readiness=True) as (a, _):
            with (
                patch(
                    "app.services.task_readiness.assess_with_model", side_effect=assess
                ) as assessment,
                patch("app.agents.assistant._build_model") as generation,
            ):
                turn = await submit(a, message="分析并比较方案")
                await try_run(turn.id)
                first = await get(a, turn.id)
                await answer(a, first, "给出了一些背景，但未说明范围")
                await try_run(turn.id)
                second = await get(a, turn.id)
                assert second.status == "waiting_input"
                assert first.pending_input["question_id"] != second.pending_input["question_id"]
                with pytest.raises(AlreadyExistsError):
                    await answer(a, first, "A与B")
                await answer(a, second, "仍只有背景介绍")
                await try_run(turn.id)
                saved = await get(a, turn.id)
                assert saved.status == "completed" and "未继续执行" in saved.result["content"]
                assert assessment.await_count == 3 and not generation.called

    asyncio.run(check())


def test_requirement_change_and_cancel_reject_old_mandatory_answers():
    async def check():
        async with users(real_readiness=True) as (a, _):
            with patch(
                "app.services.task_readiness.assess_with_model",
                new=AsyncMock(return_value=(blocker(), {})),
            ):
                turn = await submit(a, message="创建任务：比较范围并生成报告")
                await try_run(turn.id)
                waiting = await get(a, turn.id)
                new = await submit(
                    a,
                    conversation_id=turn.conversation_id,
                    message="完整新目标",
                    work_task=selection(turn, "replace"),
                )
                with pytest.raises(AlreadyExistsError):
                    await answer(a, waiting, "A与B")
                await try_run(new.id)
                next_wait = await get(a, new.id)
                async with get_worker_db_context() as db:
                    await AgentRunService(db, a).cancel(new.id)
                with pytest.raises(AlreadyExistsError):
                    await answer(a, next_wait, "A与B")

    asyncio.run(check())


def test_same_response_cannot_generate_file_while_asking_a_required_question():
    async def stream(messages, info):
        yield {
            0: DeltaToolCall(
                name="create_document",
                json_args='{"document":{"format":"md","title":"未获确认的文档","content":"内容"}}',
                tool_call_id="doc",
            ),
            1: DeltaToolCall(
                name="ask_user",
                json_args='{"questions":[{"question":"处理哪个对象？","kind":"missing_input","options":["A","B"]}]}',
                tool_call_id="ask",
            ),
        }

    async def check():
        async with users() as (a, _):
            with (
                patch(
                    "app.agents.assistant._build_model",
                    return_value=FunctionModel(stream_function=stream),
                ),
                patch(
                    "app.services.agent_run_graph.render_async", new_callable=AsyncMock
                ) as render,
            ):
                turn = await submit(a, message="生成文档")
                await try_run(turn.id)
            waiting = await get(a, turn.id)
            assert waiting.status == "waiting_input", waiting.error
            assert not render.called
            with pytest.raises(BadRequestError):
                await answer(a, waiting, SKIP)

    asyncio.run(check())


def test_optional_preference_can_use_default_without_mandatory_recheck():
    async def stream(messages, info):
        if any(getattr(p, "part_kind", None) == "tool-return" for m in messages for p in m.parts):
            yield "按默认格式完成。"
        else:
            yield {
                0: DeltaToolCall(
                    name="ask_user",
                    json_args='{"questions":[{"question":"偏好什么语气？","kind":"preference","options":["简洁","详细"]}]}',
                    tool_call_id="pref",
                )
            }

    async def check():
        async with users() as (a, _):
            with patch(
                "app.agents.assistant._build_model",
                return_value=FunctionModel(stream_function=stream),
            ):
                turn = await submit(a, message="你好")
                await try_run(turn.id)
                waiting = await get(a, turn.id)
                assert waiting.status == "waiting_input", waiting.error
                assert not waiting.pending_input["calls"][0]["questions"][0]["required"]
                await answer(a, waiting, SKIP)
                await try_run(turn.id)
                assert (await get(a, turn.id)).status == "completed"

    asyncio.run(check())


@pytest.mark.parametrize(
    "reply", [END_EVIDENCE, RETRY_EVIDENCE, "请检索服务续期条件，不能把用户说法当成证据"]
)
def test_knowledge_shortfall_retries_once_then_waits_and_never_uses_user_claims_as_citations(reply):
    async def check():
        async with fixture() as (a, _, bid, _source):
            with (
                patch(
                    "app.services.knowledge.KnowledgeService.search", side_effect=search_result([])
                ) as search,
                patch(
                    "app.services.chat_execution.choose_route",
                    new=AsyncMock(return_value={"route": "standard", "reason": "直接检索"}),
                ),
            ):
                turn = await submit(a, message="说明服务续期条件", knowledge_base_ids=[bid])
                await try_run(turn.id)
                waiting = await get(a, turn.id)
                assert waiting.status == "waiting_input", waiting.error
                assert search.await_count == 2
                assert waiting.pending_input["kind"] == "evidence"
                await answer(a, waiting, reply)
                await try_run(turn.id)
                result = await get(a, turn.id)
                assert result.status == "completed", result.error
                assert not result.result.get("citations")
                assert search.await_count == (2 if reply == END_EVIDENCE else 3)
                transcript = await state(a, turn.conversation_id)
                assert not transcript["messages"][-1].tool_calls

    asyncio.run(check())


def test_unavailable_readiness_fails_closed_before_any_tool_or_generation():
    from app.services.task_readiness import ReadinessUnavailable

    async def check():
        async with users(real_readiness=True) as (a, _):
            with (
                patch(
                    "app.services.task_readiness.assess_with_model",
                    side_effect=ReadinessUnavailable(message="offline"),
                ),
                patch("app.agents.assistant._build_model") as generation,
                patch("app.services.agent_run_graph.render_async") as render,
            ):
                turn = await submit(a, message="生成文档")
                await try_run(turn.id)
                saved = await get(a, turn.id)
                assert saved.status == "failed" and "必要信息检查暂不可用" in saved.error
                assert not generation.called and not render.called

    asyncio.run(check())


def test_second_retrieval_can_recover_with_real_source_validation():
    from pydantic_ai.messages import ModelResponse, ToolCallPart

    from tests.test_knowledge_collaboration import answer as supported_answer
    from tests.test_knowledge_collaboration import record_search

    async def check():
        async with fixture() as (a, _, bid, source):
            count = 0

            async def search(*args, **kwargs):
                nonlocal count
                count += 1
                return record_search(kwargs, [] if count == 1 else [source])

            def model(messages, info):
                return ModelResponse(
                    parts=[ToolCallPart(info.output_tools[0].name, supported_answer())]
                )

            with (
                patch("app.services.knowledge.KnowledgeService.search", side_effect=search),
                patch(
                    "app.services.knowledge_answer._build_model", return_value=FunctionModel(model)
                ),
            ):
                turn = await submit(a, message="服务期限？", knowledge_base_ids=[bid])
                await try_run(turn.id)
                saved = await get(a, turn.id)
                assert saved.status == "completed", saved.error
                assert count == 2 and saved.result["citations"][0]["citation_id"]
                from sqlalchemy import select

                from app.db.models.knowledge import KnowledgeCitation

                async with get_worker_db_context() as db:
                    citation = await db.scalar(
                        select(KnowledgeCitation).where(
                            KnowledgeCitation.message_id == saved.assistant_message_id
                        )
                    )
                    assert citation.source["quotes"] == [source["content"]]
                assert len(saved.result["retrieval_runs"]) == 2
                assert not saved.pending_input

    asyncio.run(check())


def test_collaboration_review_rejection_waits_and_retries_through_review_again():
    from collections import Counter

    from tests.test_knowledge_collaboration import roles

    async def check():
        async with fixture() as (a, _, bid, source):
            calls = []
            with (
                patch(
                    "app.services.knowledge.KnowledgeService.search",
                    side_effect=search_result([source]),
                ),
                patch(
                    "app.services.knowledge_collaboration.run_role",
                    side_effect=roles(calls, reject=True),
                ),
                patch(
                    "app.services.chat_execution.choose_route",
                    new=AsyncMock(
                        return_value={"route": "knowledge_collaboration", "reason": "综合审校"}
                    ),
                ),
            ):
                turn = await submit(a, message="综合分析服务条款", knowledge_base_ids=[bid])
                await try_run(turn.id)
                waiting = await get(a, turn.id)
                assert waiting.status == "waiting_input", waiting.error
                assert Counter(calls)["critic"] == 2
                await answer(a, waiting, RETRY_EVIDENCE)
                await try_run(turn.id)
                saved = await get(a, turn.id)
                assert saved.status == "completed", saved.error
                assert not saved.result["citations"] and "已停止回答" in saved.result["content"]
                assert Counter(calls)["critic"] == 4 and Counter(calls)["writer"] == 4
                assert saved.result["usage"]["requests"] == 12

    asyncio.run(check())


def test_deleted_clarification_blocks_resumption_before_generation():
    from uuid import uuid5

    from app.db.models.conversation import Message

    async def check():
        async with users(real_readiness=True) as (a, _):
            with (
                patch(
                    "app.services.task_readiness.assess_with_model",
                    new=AsyncMock(return_value=(blocker(), {})),
                ),
                patch("app.agents.assistant._build_model") as generation,
            ):
                turn = await submit(a, message="比较方案")
                await try_run(turn.id)
                waiting = await get(a, turn.id)
                await answer(a, waiting, "A与B")
                async with get_worker_db_context() as db:
                    message = await db.get(
                        Message,
                        uuid5(turn.id, "clarification:" + waiting.pending_input["question_id"]),
                    )
                    await db.delete(message)
                await try_run(turn.id)
                saved = await get(a, turn.id)
                assert saved.status == "failed" and not generation.called

    asyncio.run(check())
