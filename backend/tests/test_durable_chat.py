"""Normal chat acceptance, recovery and isolation against a disposable database."""

import asyncio
import json
import os
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import DeltaToolCall, FunctionModel
from sqlalchemy import select

from app.core.exceptions import AlreadyExistsError, NotFoundError
from app.db.models.conversation import Message
from app.db.session import get_worker_db_context
from app.repositories.agent_run import AgentRunRepository
from app.schemas.agent_run import AgentRunResume
from app.schemas.chat_turn import ChatTurnCreate
from app.schemas.project import ProjectWrite
from app.services.agent_run import AgentRunService
from app.services.chat_execution import choose_route
from app.services.chat_turn import ChatTurnService
from app.services.model_config import resolve_generation_config
from app.services.project import ProjectService
from app.worker.agent_runs import try_run
from tests.test_agent_runs_integration import get, text_stream, users
from tests.test_knowledge_collaboration import fixture, roles, search_result

pytestmark = pytest.mark.skipif(os.getenv("RUN_TASK_DB_TESTS") != "1", reason="disposable DB only")


async def submit(uid, project_id=None, **kw):
    data = ChatTurnCreate(idempotency_key=kw.pop("idempotency_key", uuid4()), **kw)
    async with get_worker_db_context() as db:
        return await ChatTurnService(db, uid, project_id=project_id).create(data)


async def state(uid, cid, project_id=None, **kw):
    async with get_worker_db_context() as db:
        return await ChatTurnService(db, uid, project_id=project_id).state(cid, **kw)


def test_atomic_idempotent_submission_and_history_after_absent_client():
    async def check():
        async with users() as (a, b):
            key = uuid4()
            one, two = await asyncio.gather(
                *[submit(a, message="保留这段会话", idempotency_key=key) for _ in range(2)]
            )
            assert one.id == two.id
            snapshot = await state(a, one.conversation_id)
            assert [m.role for m in snapshot["messages"]] == ["user", "assistant"]
            with pytest.raises(AlreadyExistsError):
                await submit(a, message="不同内容", idempotency_key=key)
            with pytest.raises(NotFoundError):
                await state(b, one.conversation_id)
            with patch(
                "app.agents.assistant._build_model",
                return_value=FunctionModel(stream_function=text_stream),
            ):
                # No browser connection exists; a fresh worker claims the saved turn.
                await asyncio.gather(try_run(one.id), try_run(one.id))
                await try_run(one.id)
            saved = await get(a, one.id)
            assert saved.status == "completed", saved.error
            snapshot = await state(a, one.conversation_id)
            assert len(snapshot["messages"]) == 2
            assert snapshot["messages"][1].id == one.assistant_message_id
            assert "持久保存" in snapshot["messages"][1].content
            assert snapshot["runs"][0]["request"] == {"routing": saved.request["routing"]}
            assert snapshot["runs"][0]["result"] is None
            assert "messages" not in await state(a, one.conversation_id, include_messages=False)

    asyncio.run(check())


def test_same_conversation_order_and_previous_answer_context():
    async def check():
        observed = []

        async def stream(messages, info):
            observed.append(str(messages))
            yield "前一轮的独有答案"

        async with users() as (a, _):
            first = await submit(a, message="第一轮")
            second = await submit(a, conversation_id=first.conversation_id, message="继续解释")
            async with get_worker_db_context() as db:
                assert first.id in await AgentRunRepository(db).candidates()
                assert second.id not in await AgentRunRepository(db).candidates()
            await try_run(second.id)
            assert (await get(a, second.id)).attempt == 0
            with patch(
                "app.agents.assistant._build_model",
                return_value=FunctionModel(stream_function=stream),
            ):
                await try_run(first.id)
                await try_run(second.id)
            assert (await get(a, second.id)).status == "completed"
            assert len(observed) == 2 and "前一轮的独有答案" in observed[1]
            assert "继续解释" not in observed[0]

    asyncio.run(check())


def test_pagination_project_boundary_and_invalid_cursor():
    async def check():
        async with users() as (a, b):
            async with get_worker_db_context() as db:
                project = await ProjectService(db, a).save(ProjectWrite(name="专属项目"))
            turn = await submit(a, project_id=project.id, message="项目会话")
            with pytest.raises(NotFoundError):
                await state(a, turn.conversation_id)
            with pytest.raises(NotFoundError):
                await submit(b, project_id=project.id, message="禁止访问")
            with pytest.raises(NotFoundError):
                await submit(a, conversation_id=turn.conversation_id, message="错误项目")
            async with get_worker_db_context() as db:
                now = datetime.now(UTC) - timedelta(days=1)
                db.add_all(
                    [
                        Message(
                            conversation_id=turn.conversation_id,
                            role="user",
                            content=str(i),
                            created_at=now + timedelta(seconds=i),
                        )
                        for i in range(105)
                    ]
                )
            all_ids, cursor = [], None
            while True:
                page = await state(a, turn.conversation_id, project.id, before=cursor)
                all_ids.extend(m.id for m in page["messages"])
                cursor = page["before"]
                if not cursor:
                    break
                from uuid import UUID

                cursor = UUID(cursor)
            assert len(all_ids) == len(set(all_ids)) == 107
            with pytest.raises(NotFoundError):
                await state(a, turn.conversation_id, project.id, before=uuid4())

    asyncio.run(check())


def test_durable_clarification_and_worker_recovery():
    async def stream(messages, info):
        if any(
            getattr(p, "tool_name", None) == "ask_user" and p.part_kind == "tool-return"
            for m in messages
            for p in m.parts
        ):
            yield "使用 Markdown，继续完成。"
        else:
            yield {
                0: DeltaToolCall(
                    name="ask_user",
                    json_args=json.dumps(
                        {
                            "questions": [
                                {"question": "使用什么格式？", "options": ["Markdown", "文本"]}
                            ]
                        }
                    ),
                    tool_call_id="format-q",
                )
            }

    async def check():
        async with users() as (a, _):
            turn = await submit(a, message="整理内容")
            with patch(
                "app.agents.assistant._build_model",
                return_value=FunctionModel(stream_function=stream),
            ):
                await try_run(turn.id)
                snapshot = await state(a, turn.conversation_id)
                run = snapshot["runs"][0]
                assert run["status"] == "waiting_input", run["error"]
                next_turn = await submit(
                    a, conversation_id=turn.conversation_id, message="下一件事"
                )
                await try_run(next_turn.id)
                assert (await get(a, next_turn.id)).attempt == 0
                async with get_worker_db_context() as db:
                    await AgentRunService(db, a).resume(
                        turn.id,
                        AgentRunResume(
                            question_id=run["pending_input"]["question_id"],
                            answers={"format-q": ["Markdown"]},
                        ),
                    )
                await try_run(turn.id)
            snapshot = await state(a, turn.conversation_id)
            assert snapshot["runs"][0]["status"] == "completed", snapshot["runs"][0]["error"]
            assert "Markdown" in snapshot["messages"][1].content
            assert "Markdown" in snapshot["messages"][1].tool_calls[0].result

    asyncio.run(check())


def test_progress_survives_cancel_and_restart_without_duplicate_messages():
    async def check():
        entered, finish = asyncio.Event(), asyncio.Event()

        async def stream(messages, info):
            yield "已经生成的开头"
            entered.set()
            await finish.wait()
            yield "后续内容"

        async with users() as (a, _):
            turn = await submit(a, message="长回答")
            with patch(
                "app.agents.assistant._build_model",
                return_value=FunctionModel(stream_function=stream),
            ):
                work = asyncio.create_task(try_run(turn.id))
                await asyncio.wait_for(entered.wait(), 10)
                work.cancel()  # process shutdown, not a user cancel
                with pytest.raises(asyncio.CancelledError):
                    await work
                assert (await get(a, turn.id)).status == "running"
                finish.set()
                await try_run(turn.id)
            snapshot = await state(a, turn.conversation_id)
            assert snapshot["runs"][0]["status"] == "completed", snapshot["runs"][0]["error"]
            assert len(snapshot["messages"]) == 2
            assert snapshot["messages"][1].content == "已经生成的开头后续内容"
            cancelled = await submit(a, conversation_id=turn.conversation_id, message="取消排队")
            async with get_worker_db_context() as db:
                await AgentRunService(db, a).cancel(cancelled.id)
            await try_run(cancelled.id)
            assert (await state(a, turn.conversation_id))["runs"][-1]["status"] == "cancelled"

    asyncio.run(check())


def test_auto_collaboration_preserves_citations_and_scoped_history():
    async def check():
        async with fixture() as (a, other, bid, source):
            turn = await submit(a, message="综合比较条款并整理报告", knowledge_base_ids=[bid])
            selected = AsyncMock(
                return_value={"route": "knowledge_collaboration", "reason": "综合多份资料"}
            )
            with (
                patch("app.services.chat_execution.choose_route", selected),
                patch(
                    "app.services.knowledge.KnowledgeService.search",
                    side_effect=search_result([source]),
                ),
                patch("app.services.knowledge_collaboration.run_role", side_effect=roles([])),
            ):
                await try_run(turn.id)
                await try_run(turn.id)
            saved = await get(a, turn.id)
            assert saved.status == "completed", saved.error
            snapshot = await state(a, turn.conversation_id)
            message = snapshot["messages"][1]
            assert "30天" in message.content
            payload = json.loads(message.tool_calls[0].result)
            assert payload["items"][0]["citation_id"]
            assert payload["items"][0]["content"] == ""
            from app.db.models.knowledge import KnowledgeCitation

            async with get_worker_db_context() as db:
                citations = list(
                    await db.scalars(
                        select(KnowledgeCitation).where(KnowledgeCitation.message_id == message.id)
                    )
                )
                assert len(citations) == 1 and "30天" in citations[0].source["content"]

    asyncio.run(check())


def test_automatic_router_fast_path_and_safe_fallback():
    async def check():
        config = resolve_generation_config({})
        request = {
            "prompt": "综合比较并评估多个方案",
            "knowledge_base_ids": [str(uuid4())],
            "knowledge_strict": True,
        }
        with patch(
            "app.services.chat_execution._build_model",
            return_value=FunctionModel(
                lambda m, i: ModelResponse(
                    parts=[
                        ToolCallPart(
                            i.output_tools[0].name,
                            {
                                "route": "knowledge_collaboration",
                                "confidence": "high",
                                "reason": "需要交叉研究",
                            },
                        )
                    ]
                )
            ),
        ) as model:
            assert (
                await choose_route({**request, "knowledge_base_ids": []}, {"query": "test"}, config)
            )["route"] == "standard"
            assert not model.called
            assert (await choose_route(request, {"query": "test"}, config))[
                "route"
            ] == "knowledge_collaboration"
        with patch(
            "app.services.chat_execution.Agent.run", side_effect=RuntimeError("router unavailable")
        ):
            assert (await choose_route(request, {"query": "test"}, config))["route"] == "standard"

    asyncio.run(check())


def test_http_acceptance_restoration_and_memory_scope():
    from uuid import UUID

    from tests.test_project_spaces_integration import header, workspace

    async def check():
        async with workspace() as (_, _, _, _, project, other_project, _, client):
            h = header(project)
            assert (await client.get(f"/api/v1/projects/{project.id}")).status_code == 200
            assert (
                await client.put(
                    "/api/v1/memory/settings", headers=h, json={"enabled": True, "revision": 0}
                )
            ).status_code == 200
            assert (
                await client.post(
                    "/api/v1/memory",
                    headers=h,
                    json={
                        "title": "测量条件",
                        "content": "超表面测量保持 25°C",
                        "kind": "constraint",
                    },
                )
            ).status_code == 201
            payload = {
                "idempotency_key": str(uuid4()),
                "message": "超表面测量条件是什么",
                "knowledge_base_ids": [],
            }
            accepted = await client.post("/api/v1/chat/turns", headers=h, json=payload)
            assert accepted.status_code == 201, accepted.text
            turn = accepted.json()
            assert (await client.post("/api/v1/chat/turns", headers=h, json=payload)).json()[
                "id"
            ] == turn["id"]
            assert (
                await client.get(
                    f"/api/v1/chat/conversations/{turn['conversation_id']}/state",
                    headers=header(other_project),
                )
            ).status_code == 404
            observed = []

            async def stream(messages, info):
                observed.append(str(messages))
                yield "按已保存条件进行测量。"

            with patch(
                "app.agents.assistant._build_model",
                return_value=FunctionModel(stream_function=stream),
            ):
                await try_run(UUID(turn["id"]))
            restored = await client.get(
                f"/api/v1/chat/conversations/{turn['conversation_id']}/state", headers=h
            )
            assert restored.status_code == 200, restored.text
            answer = restored.json()["messages"][1]
            assert "25°C" in observed[0]
            assert answer["effective_config"]["memory"]["status"] == "used"
            assert "25°C" not in str(answer["effective_config"])

    asyncio.run(check())


def test_chat_python_requires_permission_and_keeps_artifacts():
    from app.core.config import settings
    from app.core.exceptions import AuthorizationError
    from app.services import sandbox_client
    from app.services.run_artifact import RunArtifactService
    from app.services.sandbox_files import validate_artifacts
    from tests.test_sandbox_files import artifact

    async def stream(messages, info):
        if any(
            getattr(p, "tool_name", None) == "run_python" and p.part_kind == "tool-return"
            for m in messages
            for p in m.parts
        ):
            yield "计算完成，结果文件已保存。"
        else:
            yield {
                0: DeltaToolCall(
                    name="run_python", json_args='{"code":"print(1)"}', tool_call_id="chat-python"
                )
            }

    async def check():
        async with users() as (a, _):
            health = AsyncMock(
                return_value={"status": "ready", "file_execution": {"inputs_read_only": True}}
            )
            with (
                patch.object(sandbox_client, "health", health),
                patch.object(settings, "SANDBOX_ALLOW_PUBLIC", False),
            ):
                with pytest.raises(AuthorizationError):
                    await submit(a, message="执行代码", python_enabled=True)
                async with get_worker_db_context() as db:
                    assert await AgentRunRepository(db).list(a) == []
            remote_result = {
                "state": "completed",
                "execution_id": str(uuid4()),
                "exit_code": 0,
                "artifact_files": validate_artifacts([artifact()], "completed"),
            }
            with (
                patch.object(settings, "SANDBOX_ALLOW_PUBLIC", True),
                patch.object(sandbox_client, "health", health),
                patch.object(
                    sandbox_client, "run_python", AsyncMock(return_value=remote_result)
                ) as remote,
                patch(
                    "app.agents.assistant._build_model",
                    return_value=FunctionModel(stream_function=stream),
                ),
            ):
                turn = await submit(a, message="执行计算并生成文件", python_enabled=True)
                await try_run(turn.id)
            saved = await get(a, turn.id)
            assert saved.status == "completed", saved.error
            remote.assert_awaited_once_with(turn.id, "print(1)", protocol=2, inputs=[])
            snapshot = await state(a, turn.conversation_id)
            assert snapshot["messages"][1].tool_calls[0].tool_name == "run_python"
            async with get_worker_db_context() as db:
                assert len(await RunArtifactService(db, a).list(turn.id)) == 1

    asyncio.run(check())
