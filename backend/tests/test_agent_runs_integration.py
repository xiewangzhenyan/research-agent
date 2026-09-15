"""Opt-in integration tests against a disposable migrated PostgreSQL database.

RUN_TASK_DB_TESTS=1 python -m pytest tests/test_agent_runs_integration.py
Never enable against the production database.
"""

import asyncio
import json
import os
from contextlib import asynccontextmanager
from unittest.mock import patch
from uuid import uuid4

import pytest
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from pydantic_ai.models.function import DeltaToolCall, FunctionModel
from sqlalchemy import delete

from app.core.config import settings
from app.core.exceptions import AlreadyExistsError, NotFoundError, RateLimitError
from app.db.models.user import User
from app.db.session import get_worker_db_context
from app.repositories.agent_run import AgentRunRepository
from app.schemas.agent_run import AgentRunCreate, AgentRunResume
from app.services.agent_run import AgentRunService
from app.worker.agent_runs import connect, try_run

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_TASK_DB_TESTS") != "1", reason="requires disposable database"
)


@asynccontextmanager
async def users(*, real_readiness=False):
    assert settings.POSTGRES_DB.endswith("_review"), "Refusing to test a non-review database"
    ids = [uuid4(), uuid4()]
    async with get_worker_db_context() as db:
        db.add_all([User(id=i, email=f"task-test-{i}@example.invalid") for i in ids])
    try:
        if real_readiness:
            yield ids
        else:
            # These fixtures exercise execution/recovery, not model judgement.
            # Keep the readiness policy real and replace only its paid classifier.
            from app.services.task_readiness import ReadinessAssessment

            async def ready(request, context, config, answers, usage, validate):
                await validate()
                return ReadinessAssessment(), usage

            with patch("app.services.task_readiness.assess_with_model", side_effect=ready):
                yield ids
    finally:
        async with get_worker_db_context() as db:
            runs = [r for uid in ids for r in await AgentRunRepository(db).list(uid)]
            await db.execute(delete(User).where(User.id.in_(ids)))
        async with await connect() as conn:
            saver = AsyncPostgresSaver(conn)
            for run in runs:
                await saver.adelete_thread(f"run:{run.id}")


async def create(uid, **kwargs):
    data = AgentRunCreate(
        idempotency_key=kwargs.pop("idempotency_key", uuid4()),
        prompt=kwargs.pop("prompt", "请整理一份任务说明"),
        **kwargs,
    )
    async with get_worker_db_context() as db:
        return await AgentRunService(db, uid).create(data)


async def get(uid, rid):
    async with get_worker_db_context() as db:
        return await AgentRunService(db, uid).get(rid)


async def text_stream(messages, info):
    yield "任务完成，内容已持久保存。"


def test_submission_isolation_and_limit():
    async def check():
        async with users() as (a, b):
            key = uuid4()
            runs = await asyncio.gather(
                create(a, idempotency_key=key), create(a, idempotency_key=key)
            )
            assert runs[0].id == runs[1].id
            with pytest.raises(AlreadyExistsError):
                await create(a, idempotency_key=key, prompt="不同内容")
            with pytest.raises(NotFoundError):
                await get(b, runs[0].id)
            async with get_worker_db_context() as db:
                with pytest.raises(NotFoundError):
                    await AgentRunService(db, b).cancel(runs[0].id)
            for _ in range(4):
                await create(a)
            with pytest.raises(RateLimitError):
                await create(a)

    asyncio.run(check())


def test_duplicate_delivery_single_result_and_events():
    async def check():
        async with users() as (a, _):
            run = await create(a)
            with patch(
                "app.agents.assistant._build_model",
                return_value=FunctionModel(stream_function=text_stream),
            ):
                await asyncio.gather(try_run(run.id), try_run(run.id))
                await try_run(run.id)
            saved = await get(a, run.id)
            assert saved.status == "completed", saved.error
            assert saved.attempt == 1
            assert "持久保存" in saved.result["content"]
            async with get_worker_db_context() as db:
                events = await AgentRunRepository(db).events(run.id, 0)
                replay = await AgentRunRepository(db).events(run.id, 2)
            assert [e.seq for e in events] == list(range(1, saved.event_seq + 1))
            assert [e.seq for e in replay] == [e.seq for e in events if e.seq > 2]
            assert sum(e.kind == "completed" for e in events) == 1

    asyncio.run(check())


def test_durable_question_pause_and_resume():
    async def stream(messages, info):
        if any(
            getattr(p, "tool_name", None) == "ask_user" and p.part_kind == "tool-return"
            for m in messages
            for p in m.parts
        ):
            yield "收到补充信息，使用 Markdown 输出。"
        else:
            yield {
                0: DeltaToolCall(
                    name="ask_user",
                    json_args=json.dumps(
                        {
                            "questions": [
                                {"question": "使用什么格式？", "options": ["Markdown", "纯文本"]}
                            ]
                        }
                    ),
                    tool_call_id="format-q",
                )
            }

    async def check():
        async with users() as (a, b):
            run = await create(a)
            with patch(
                "app.agents.assistant._build_model",
                return_value=FunctionModel(stream_function=stream),
            ):
                await try_run(run.id)
                paused = await get(a, run.id)
                assert paused.status == "waiting_input", paused.error
                assert paused.pending_input["calls"][0]["call_id"] == "format-q"
                reply = AgentRunResume(
                    question_id=paused.pending_input["question_id"],
                    answers={"format-q": ["Markdown"]},
                )
                async with get_worker_db_context() as db:
                    with pytest.raises(NotFoundError):
                        await AgentRunService(db, b).resume(run.id, reply)
                async with get_worker_db_context() as db:
                    await AgentRunService(db, a).resume(run.id, reply)
                    await AgentRunService(db, a).resume(run.id, reply)
                await try_run(run.id)
            saved = await get(a, run.id)
            assert saved.status == "completed", saved.error
            assert "Markdown" in saved.result["content"]
            assert saved.attempt == 2

    asyncio.run(check())


def test_cancel_running_stops_generation_before_terminal_state():
    async def check():
        entered = asyncio.Event()
        stopped = asyncio.Event()

        async def slow(messages, info):
            entered.set()
            try:
                await asyncio.sleep(30)
                yield "不应保存此内容"
            finally:
                stopped.set()

        async with users() as (a, _):
            run = await create(a)
            with patch(
                "app.agents.assistant._build_model",
                return_value=FunctionModel(stream_function=slow),
            ):
                work = asyncio.create_task(try_run(run.id))
                await asyncio.wait_for(entered.wait(), 10)
                async with get_worker_db_context() as db:
                    current = await AgentRunService(db, a).cancel(run.id)
                    assert current.status == "cancelling"
                await asyncio.wait_for(work, 10)
            saved = await get(a, run.id)
            assert stopped.is_set()
            assert saved.status == "cancelled"
            assert saved.result is None

    asyncio.run(check())


def test_worker_interruption_recovers_completed_retrieval_node():
    async def check():
        entered = asyncio.Event()

        async def slow(messages, info):
            entered.set()
            await asyncio.sleep(30)
            yield "unreachable"

        async with users() as (a, _):
            run = await create(a)
            with patch(
                "app.agents.assistant._build_model",
                return_value=FunctionModel(stream_function=slow),
            ):
                work = asyncio.create_task(try_run(run.id))
                await asyncio.wait_for(entered.wait(), 10)
                work.cancel()
                await asyncio.gather(work, return_exceptions=True)
            assert (await get(a, run.id)).status == "running"
            with patch(
                "app.agents.assistant._build_model",
                return_value=FunctionModel(stream_function=text_stream),
            ):
                await try_run(run.id)
            saved = await get(a, run.id)
            assert saved.status == "completed", saved.error
            assert saved.attempt == 2
            async with get_worker_db_context() as db:
                events = await AgentRunRepository(db).events(run.id, 0)
            assert (
                sum(e.kind == "step_completed" and e.data.get("step") == "retrieve" for e in events)
                == 1
            )

    asyncio.run(check())


def test_process_kill_releases_lock_and_recovers_checkpoint():
    import sys

    async def check():
        async with users() as (a, _):
            run = await create(a)
            script = """
import asyncio
from uuid import UUID
from unittest.mock import patch
from pydantic_ai.models.function import FunctionModel
from app.worker.agent_runs import try_run
async def stream(messages, info):
    print("MODEL_ENTERED", flush=True)
    await asyncio.sleep(120)
    yield "unreachable"
async def main():
    with patch("app.agents.assistant._build_model", return_value=FunctionModel(stream_function=stream)):
        await try_run(UUID(RUN_ID))
asyncio.run(main())
""".replace("RUN_ID", repr(str(run.id)))
            proc = await asyncio.create_subprocess_exec(
                sys.executable,
                "-c",
                script,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            try:
                assert await asyncio.wait_for(proc.stdout.readline(), 20) == b"MODEL_ENTERED\n"
                proc.kill()
                await proc.wait()
            finally:
                if proc.returncode is None:
                    proc.kill()
                    await proc.wait()
            with patch(
                "app.agents.assistant._build_model",
                return_value=FunctionModel(stream_function=text_stream),
            ):
                await try_run(run.id)
            saved = await get(a, run.id)
            assert saved.status == "completed", saved.error
            assert saved.attempt == 2
            async with get_worker_db_context() as db:
                events = await AgentRunRepository(db).events(run.id, 0)
            assert (
                sum(e.kind == "step_completed" and e.data.get("step") == "retrieve" for e in events)
                == 1
            )

    asyncio.run(check())


def test_invalid_model_scope_and_queued_cancel():
    from app.core.exceptions import BadRequestError
    from app.services.knowledge import KnowledgeService

    async def check():
        async with users() as (a, b):
            with pytest.raises(BadRequestError):
                await create(a, generation={"model": "not-in-deployment"})
            async with get_worker_db_context() as db:
                base = await KnowledgeService(db, b).create_base("隔离资料", "")
            with pytest.raises(NotFoundError):
                await create(a, knowledge_base_ids=[base["id"]])
            run = await create(a)
            async with get_worker_db_context() as db:
                assert len(await AgentRunRepository(db).list(a)) == 1
                cancelled = await AgentRunService(db, a).cancel(run.id)
                assert cancelled.status == "cancelled"
            with patch("app.agents.assistant._build_model") as model:
                await try_run(run.id)
                model.assert_not_called()

    asyncio.run(check())


def test_final_checkpoint_reconciles_without_second_model_call():
    async def check():
        calls = 0

        async def stream(messages, info):
            nonlocal calls
            calls += 1
            yield "最终结果只生成一次"

        original = AgentRunRepository.event

        async def crash_final_write(self, run, kind, data):
            if kind == "completed":
                raise asyncio.CancelledError()
            return await original(self, run, kind, data)

        async with users() as (a, _):
            run = await create(a)
            with patch(
                "app.agents.assistant._build_model",
                return_value=FunctionModel(stream_function=stream),
            ):
                with (
                    patch.object(AgentRunRepository, "event", crash_final_write),
                    pytest.raises(asyncio.CancelledError),
                ):
                    await try_run(run.id)
                assert (await get(a, run.id)).status == "running"
                await try_run(run.id)
            saved = await get(a, run.id)
            assert saved.status == "completed", saved.error
            assert saved.result["content"] == "最终结果只生成一次"
            assert calls == 1

    asyncio.run(check())


def test_python_task_uses_remote_gateway_and_persists_code_output():
    from unittest.mock import AsyncMock

    from app.services import sandbox_client

    async def stream(messages, info):
        if any(
            getattr(p, "tool_name", None) == "run_python" and p.part_kind == "tool-return"
            for m in messages
            for p in m.parts
        ):
            yield "计算结果是 2"
        else:
            yield {
                0: DeltaToolCall(
                    name="run_python", json_args='{"code":"print(1+1)"}', tool_call_id="python-one"
                )
            }

    async def check():
        async with users() as (a, _):
            with (
                patch.object(settings, "SANDBOX_ALLOW_PUBLIC", True),
                patch.object(sandbox_client, "health", AsyncMock(return_value={"status": "ready"})),
                patch.object(
                    sandbox_client,
                    "run_python",
                    AsyncMock(
                        return_value={
                            "state": "completed",
                            "stdout": "2\n",
                            "stderr": "",
                            "exit_code": 0,
                        }
                    ),
                ) as remote,
                patch(
                    "app.agents.assistant._build_model",
                    return_value=FunctionModel(stream_function=stream),
                ),
            ):
                run = await create(a, tools=["run_python"])
                await try_run(run.id)
                remote.assert_awaited_once_with(run.id, "print(1+1)")
            saved = await get(a, run.id)
            assert saved.status == "completed", saved.error
            async with get_worker_db_context() as db:
                events = await AgentRunRepository(db).events(run.id, 0)
            result = next(e for e in events if e.kind == "python_result")
            assert result.data["code"] == "print(1+1)" and result.data["stdout"] == "2\n"

    asyncio.run(check())


def test_task_cancel_waits_for_external_stop_confirmation():
    from unittest.mock import AsyncMock

    from app.core.exceptions import ExternalServiceError
    from app.services import sandbox_client

    async def check():
        entered = asyncio.Event()

        async def remote(*args):
            entered.set()
            await asyncio.sleep(30)

        async def stream(messages, info):
            yield {
                0: DeltaToolCall(
                    name="run_python", json_args='{"code":"print(1+1)"}', tool_call_id="slow-python"
                )
            }

        async with users() as (a, _):
            with (
                patch.object(settings, "SANDBOX_ALLOW_PUBLIC", True),
                patch.object(sandbox_client, "health", AsyncMock(return_value={"status": "ready"})),
                patch.object(sandbox_client, "run_python", remote),
                patch.object(
                    sandbox_client, "cancel_run", AsyncMock(side_effect=ExternalServiceError())
                ),
                patch(
                    "app.agents.assistant._build_model",
                    return_value=FunctionModel(stream_function=stream),
                ),
            ):
                run = await create(a, tools=["run_python"])
                work = asyncio.create_task(try_run(run.id))
                await asyncio.wait_for(entered.wait(), 10)
                async with get_worker_db_context() as db:
                    await AgentRunService(db, a).cancel(run.id)
                await asyncio.wait_for(work, 10)
                assert (await get(a, run.id)).status == "cancelling"
            with patch.object(sandbox_client, "cancel_run", AsyncMock()) as stop:
                await try_run(run.id)
                stop.assert_awaited_once_with(run.id)
            assert (await get(a, run.id)).status == "cancelled"

    asyncio.run(check())
