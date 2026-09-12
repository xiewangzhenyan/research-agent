"""Dedicated PostgreSQL task worker: python -m app.worker.agent_runs [--setup].

Session advisory locks prevent overlapping graph writers across workers/restarts.
The lock and checkpointer share a connection: losing it also prevents checkpoint
writes. An attempt fence rejects stale business writes. No Redis handoff is needed.
"""

import asyncio
import logging
import sys
from datetime import UTC, datetime, timedelta
from uuid import UUID

import psycopg
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.types import Command
from psycopg.rows import dict_row

from app.agents.tool_catalog import PYTHON_TOOL
from app.core.config import settings
from app.core.exceptions import AuthorizationError, ExternalServiceError
from app.db.models.user import User
from app.db.session import get_worker_db_context
from app.repositories.agent_run import AgentRunRepository
from app.services import sandbox_client
from app.services.agent_run_graph import build_run_graph
from app.services.knowledge import KnowledgeService
from app.services.knowledge_collaboration import WORKFLOW_VERSION, build_collaboration_graph

logger = logging.getLogger(__name__)


async def connect():
    return await psycopg.AsyncConnection.connect(
        host=settings.POSTGRES_HOST,
        port=settings.POSTGRES_PORT,
        user=settings.POSTGRES_USER,
        password=settings.POSTGRES_PASSWORD,
        dbname=settings.POSTGRES_DB,
        autocommit=True,
        prepare_threshold=0,
        row_factory=dict_row,
        connect_timeout=10,
        keepalives=1,
        keepalives_idle=15,
        keepalives_interval=5,
        keepalives_count=3,
    )


def lock_key(run_id):
    return UUID(str(run_id)).int % (2**63 - 1)


class LostRun(Exception):
    pass


async def stop_sandbox(run_id, request):
    if PYTHON_TOOL in (request.get("tools") or []):
        await sandbox_client.cancel_run(run_id)


async def execute(run_id, conn):
    # Confirm external processes stopped before a task can become cancelled.
    async with get_worker_db_context() as db:
        pending_cancel = await AgentRunRepository(db).get(run_id)
    if pending_cancel and pending_cancel.status == "cancelling":
        await stop_sandbox(run_id, pending_cancel.request)
        async with get_worker_db_context() as db:
            repo = AgentRunRepository(db)
            current = await repo.get(run_id, lock=True)
            if current and current.status == "cancelling":
                current.status, current.finished_at = "cancelled", datetime.now(UTC)
                await repo.event(current, "cancelled", {"message": "任务及隔离计算已停止"})
        return
    async with get_worker_db_context() as db:
        repo = AgentRunRepository(db)
        run = await repo.get(run_id, lock=True)
        if not run or run.status not in ("queued", "running", "cancelling"):
            return
        if run.status == "cancelling":
            return  # Next claim confirms the sandbox stop outside this transaction.
        if (
            run.attempt >= 12 or run.created_at < datetime.now(UTC) - timedelta(days=7)
        ) and PYTHON_TOOL in (run.request.get("tools") or []):
            run.status = "cancelling"
            run.error = "任务超过恢复上限，正在停止隔离计算"
            await repo.event(run, "cancelling", {"message": run.error})
            return
        if run.attempt >= 12 or run.created_at < datetime.now(UTC) - timedelta(days=7):
            run.status, run.error, run.finished_at = (
                "failed",
                "任务已超过恢复次数或 7 天有效期，请新建任务",
                datetime.now(UTC),
            )
            await repo.event(run, "failed", {"message": run.error})
            return
        run.attempt += 1
        run.status, run.started_at = "running", datetime.now(UTC)
        attempt, user_id = run.attempt, run.user_id
        request, configuration, resume_input = run.request, run.effective_config, run.resume_input
        await repo.event(
            run,
            "running",
            {
                "message": "开始执行" if attempt == 1 else "从已保存的执行位置继续",
                "attempt": attempt,
            },
        )

    saver = AsyncPostgresSaver(conn)

    async def check_connection():
        # Share the saver lock: its pipeline must not overlap heartbeat queries.
        async with saver.lock:
            await conn.execute("SELECT 1")

    async def mutate(kind, data, **updates):
        # Verify the same lock/checkpoint connection is still alive before writes.
        await check_connection()
        async with get_worker_db_context() as db:
            repo = AgentRunRepository(db)
            current = await repo.get(run_id, lock=True)
            if not current or current.attempt != attempt or current.status != "running":
                raise LostRun()
            for key, value in updates.items():
                setattr(current, key, value)
            await repo.event(current, kind, data)

    async def graph_work():
        # Recheck ownership/readiness when starting or resuming a task.
        async with get_worker_db_context() as db:
            owner = await db.get(User, user_id)
            if not owner or not owner.is_active:
                raise AuthorizationError(message="账号已停用")
            await KnowledgeService(db, user_id).validate_scope(
                [UUID(v) for v in request["knowledge_base_ids"]], None, require_ready=True
            )
        if request.get("mode") == "knowledge_collaboration":
            if request.get("workflow_version") != WORKFLOW_VERSION or request.get("tools"):
                raise ValueError("Unsupported collaboration workflow or tools")
            graph = build_collaboration_graph(
                saver,
                user_id=user_id,
                configuration=configuration,
                emit=mutate,
                retrieval_snapshot=request.get("retrieval_snapshot"),
            )
        else:
            graph = build_run_graph(
                saver,
                user_id=user_id,
                configuration=configuration,
                emit=mutate,
                run_id=run_id,
                sandbox_request=request,
                attempt=attempt,
                allowed_tools=request.get("tools"),
                retrieval_snapshot=request.get("retrieval_snapshot"),
            )
        graph_config = {"configurable": {"thread_id": f"run:{run_id}"}, "recursion_limit": 20}
        snapshot = await graph.aget_state(graph_config)
        graph_input = None
        if not snapshot.values:
            graph_input = {"prompt": request["prompt"], "base_ids": request["knowledge_base_ids"]}
        elif any(task.interrupts for task in snapshot.tasks):
            pending = snapshot.values.get("pending")
            if resume_input and pending and resume_input["question_id"] == pending["question_id"]:
                graph_input = Command(resume=resume_input)
            else:
                await mutate(
                    "waiting_input",
                    {"message": "等待补充信息"},
                    status="waiting_input",
                    pending_input=pending,
                )
                return
        async with asyncio.timeout(300):
            await graph.ainvoke(graph_input, graph_config)
        snapshot = await graph.aget_state(graph_config)
        if any(task.interrupts for task in snapshot.tasks):
            await mutate(
                "waiting_input",
                {"message": "等待补充信息"},
                status="waiting_input",
                pending_input=snapshot.values["pending"],
            )
        else:
            await mutate(
                "completed",
                {"message": "任务已完成"},
                status="completed",
                result={
                    "content": snapshot.values["output"],
                    "citations": snapshot.values.get("citations", []),
                    "usage": snapshot.values.get("usage", {}),
                    "retrieval_runs": snapshot.values.get("retrieval_runs", []),
                    **(
                        {"collaboration": snapshot.values["collaboration"]}
                        if snapshot.values.get("collaboration")
                        else {}
                    ),
                },
                pending_input=None,
                finished_at=datetime.now(UTC),
            )

    async def watch_cancel():
        while True:
            await asyncio.sleep(1)
            await check_connection()
            async with get_worker_db_context() as db:
                current = await AgentRunRepository(db).get(run_id)
                if not current or current.attempt != attempt or current.status == "cancelling":
                    raise LostRun()

    work = asyncio.create_task(graph_work())
    watcher = asyncio.create_task(watch_cancel())
    try:
        done, _ = await asyncio.wait({work, watcher}, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            task.result()
    except asyncio.CancelledError:
        # Process shutdown leaves a recoverable running row, never a false failure.
        raise
    except Exception as exc:
        work.cancel()
        await asyncio.gather(work, return_exceptions=True)
        try:
            await stop_sandbox(run_id, request)
        except ExternalServiceError:
            # Stop reconciliation has priority over graph retries after an uncertain result.
            async with get_worker_db_context() as db:
                repo = AgentRunRepository(db)
                current = await repo.get(run_id, lock=True)
                if current and current.attempt == attempt and current.status == "running":
                    current.status = "cancelling"
                    await repo.event(
                        current, "cancelling", {"message": "正在确认隔离计算停止，稍后自动更新"}
                    )
            return
        async with get_worker_db_context() as db:
            repo = AgentRunRepository(db)
            current = await repo.get(run_id, lock=True)
            if (
                current
                and current.attempt == attempt
                and current.status in ("running", "cancelling")
            ):
                if current.status == "cancelling":
                    current.status, current.error = "cancelled", None
                elif isinstance(exc, psycopg.Error):
                    # DB connectivity errors stay recoverable; do not leak connection details.
                    return
                else:
                    current.status, current.error = (
                        "failed",
                        "任务执行失败或超时，请稍后新建任务重试",
                    )
                    logger.warning("Task %s failed: %s", run_id, type(exc).__name__)
                current.finished_at, current.pending_input = datetime.now(UTC), None
                await repo.event(
                    current, current.status, {"message": current.error or "任务已停止"}
                )
    finally:
        work.cancel()
        watcher.cancel()
        await asyncio.gather(work, watcher, return_exceptions=True)


async def try_run(run_id):
    async with await connect() as conn:
        row = await (
            await conn.execute("SELECT pg_try_advisory_lock(%s) AS acquired", (lock_key(run_id),))
        ).fetchone()
        if not row["acquired"]:
            return False
        try:
            await execute(run_id, conn)
        finally:
            if not conn.closed:
                await conn.execute("SELECT pg_advisory_unlock(%s)", (lock_key(run_id),))
        return True


async def loop():
    while True:
        try:
            async with get_worker_db_context() as db:
                candidates = await AgentRunRepository(db).candidates()
            for run_id in candidates:
                if await try_run(run_id):
                    break
        except Exception:
            logger.exception("Background task dispatcher unavailable")
        await asyncio.sleep(2)


async def maintain():
    """Expire unanswered questions and remove terminal/orphan checkpoint payloads."""
    while True:
        try:
            async with await connect() as conn:
                rows = await (
                    await conn.execute(
                        "SELECT DISTINCT c.thread_id FROM checkpoints c LEFT JOIN agent_runs r "
                        "ON c.thread_id = 'run:' || r.id::text "
                        "WHERE c.thread_id LIKE 'run:%' AND (r.id IS NULL OR "
                        "r.status IN ('completed', 'cancelled', 'failed') OR "
                        "(r.status = 'waiting_input' AND r.created_at < now() - interval '7 days')) LIMIT 100"
                    )
                ).fetchall()
                for row in rows:
                    run_id = UUID(row["thread_id"][4:])
                    locked = await (
                        await conn.execute(
                            "SELECT pg_try_advisory_lock(%s) AS acquired", (lock_key(run_id),)
                        )
                    ).fetchone()
                    if not locked["acquired"]:
                        continue
                    try:
                        async with get_worker_db_context() as db:
                            repo = AgentRunRepository(db)
                            run = await repo.get(run_id, lock=True)
                            if (
                                run
                                and run.status == "waiting_input"
                                and run.created_at < datetime.now(UTC) - timedelta(days=7)
                            ):
                                run.status, run.error = (
                                    "failed",
                                    "等待补充信息已超过 7 天，请新建任务",
                                )
                                run.finished_at, run.pending_input = datetime.now(UTC), None
                                await repo.event(run, "failed", {"message": run.error})
                            removable = run is None or run.status in (
                                "completed",
                                "failed",
                                "cancelled",
                            )
                        if removable:
                            await AsyncPostgresSaver(conn).adelete_thread(row["thread_id"])
                    finally:
                        await conn.execute("SELECT pg_advisory_unlock(%s)", (lock_key(run_id),))
        except Exception:
            logger.exception("Task checkpoint cleanup unavailable")
        await asyncio.sleep(60)


async def main():
    if "--setup" in sys.argv:
        async with await connect() as conn:
            await AsyncPostgresSaver(conn).setup()
        print("Task checkpoint schema ready")
        return
    await asyncio.gather(loop(), loop(), maintain())


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    asyncio.run(main())
