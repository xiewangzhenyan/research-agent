"""Run only against disposable sandbox_files_review PostgreSQL."""

import asyncio
import os
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.api.routes.v1.agent_runs import download_artifact
from app.core.exceptions import AlreadyExistsError, BadRequestError, NotFoundError, RateLimitError
from app.db.models.agent_run import AgentRun
from app.db.models.user import User
from app.db.session import get_worker_db_context
from app.services import sandbox_client
from app.services.file_upload import FileUploadService
from app.services.run_artifact import RunArtifactService
from app.services.sandbox_files import validate_artifacts
from tests.test_agent_runs_integration import create, users
from tests.test_sandbox_files import artifact

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_TASK_DB_TESTS") != "1", reason="requires disposable database"
)


def test_artifact_atomic_idempotent_scoped_and_fenced():
    async def check():
        async with users() as (a, b):
            run = await create(a)
            eid = uuid4()
            files = validate_artifacts([artifact()], "completed")
            async with get_worker_db_context() as db:
                current = await db.get(AgentRun, run.id)
                current.status, current.attempt = "running", 1
            async with get_worker_db_context() as db:
                first = await RunArtifactService(db, a).save(run.id, 1, eid, files)
            async with get_worker_db_context() as db:
                assert await RunArtifactService(db, a).save(run.id, 1, eid, files) == first
                assert len(await RunArtifactService(db, a).list(run.id)) == 1
                with pytest.raises(NotFoundError):
                    await RunArtifactService(db, b).list(run.id)
                from uuid import UUID

                fid = UUID(first[0]["id"])
                with pytest.raises(NotFoundError):
                    await RunArtifactService(db, b).get(run.id, fid)
                with pytest.raises(NotFoundError):
                    await RunArtifactService(db, a).get(uuid4(), fid)
                user = await db.get(User, a)
                response = await download_artifact(run.id, fid, user, db)
                assert response.body == b"a,b\n1,2"
                assert response.headers["content-disposition"].startswith("attachment;")
                assert "sandbox" in response.headers["content-security-policy"]
            async with get_worker_db_context() as db:
                with pytest.raises(AlreadyExistsError):
                    await RunArtifactService(db, a).save(run.id, 0, uuid4(), files)
                with pytest.raises(AlreadyExistsError):
                    await RunArtifactService(db, a).delete(run.id, fid)
                current = await db.get(AgentRun, run.id)
                current.status = "cancelled"
            async with get_worker_db_context() as db:
                with pytest.raises(AlreadyExistsError):
                    await RunArtifactService(db, a).save(run.id, 1, uuid4(), files)
                await RunArtifactService(db, a).delete(run.id, fid)
                assert await RunArtifactService(db, a).list(run.id) == []

    asyncio.run(check())


def test_input_permissions_and_snapshot_on_submission():
    async def check():
        async with users() as (a, b):
            async with get_worker_db_context() as db:
                file = await FileUploadService(db).upload(
                    user_id=a, file_data=b"a,b\n1,2", filename="数据.csv", content_type="text/csv"
                )
            try:
                health = {"status": "ready", "file_execution": {"inputs_read_only": True}}
                with (
                    patch.object(sandbox_client, "health", AsyncMock(return_value=health)),
                    patch(
                        "app.services.agent_run.resolve_tools",
                        AsyncMock(return_value=["run_python"]),
                    ),
                ):
                    run = await create(a, tools=["run_python"], input_file_ids=[file.id])
                    assert run.request["sandbox_protocol"] == 2
                    assert run.request["input_snapshot"][0]["id"] == str(file.id)
                    assert "content_base64" not in str(run.request)
                    with pytest.raises(NotFoundError):
                        await create(b, tools=["run_python"], input_file_ids=[file.id])
                with pytest.raises(BadRequestError):
                    await create(a, tools=[], input_file_ids=[file.id])
            finally:
                from app.services.file_storage import get_file_storage

                await get_file_storage().delete(file.storage_path)

    asyncio.run(check())


def test_quota_prevents_partial_write():
    async def check():
        async with users() as (a, _):
            run = await create(a)
            async with get_worker_db_context() as db:
                row = await db.get(AgentRun, run.id)
                row.status, row.attempt = "running", 1
            files = validate_artifacts([artifact(b"a" * (2 * 1024**2))], "completed")
            for _ in range(10):
                async with get_worker_db_context() as db:
                    await RunArtifactService(db, a).save(run.id, 1, uuid4(), files)
            async with get_worker_db_context() as db:
                with pytest.raises(RateLimitError):
                    await RunArtifactService(db, a).save(run.id, 1, uuid4(), files)
                assert len(await RunArtifactService(db, a).list(run.id)) == 10

    asyncio.run(check())


def test_file_task_graph_persists_metadata_without_binary_events():
    from pydantic_ai.models.function import DeltaToolCall, FunctionModel

    from app.core.config import settings
    from app.repositories.agent_run import AgentRunRepository
    from app.worker.agent_runs import try_run
    from tests.test_agent_runs_integration import get

    async def stream(messages, info):
        if any(
            getattr(p, "tool_name", None) == "run_python" and p.part_kind == "tool-return"
            for m in messages
            for p in m.parts
        ):
            yield "文件已生成"
        else:
            yield {
                0: DeltaToolCall(
                    name="run_python", json_args='{"code":"print(1)"}', tool_call_id="file-one"
                )
            }

    async def check():
        async with users() as (a, _):
            response = {
                "state": "completed",
                "execution_id": str(uuid4()),
                "exit_code": 0,
                "artifact_files": validate_artifacts([artifact()], "completed"),
            }
            with (
                patch.object(settings, "SANDBOX_ALLOW_PUBLIC", True),
                patch.object(
                    sandbox_client,
                    "health",
                    AsyncMock(
                        return_value={
                            "status": "ready",
                            "file_execution": {"inputs_read_only": True},
                        }
                    ),
                ),
                patch.object(
                    sandbox_client, "run_python", AsyncMock(return_value=response)
                ) as remote,
                patch(
                    "app.agents.assistant._build_model",
                    return_value=FunctionModel(stream_function=stream),
                ),
            ):
                run = await create(a, tools=["run_python"])
                await try_run(run.id)
                saved = await get(a, run.id)
                assert saved.status == "completed", saved.error
                remote.assert_awaited_once_with(run.id, "print(1)", protocol=2, inputs=[])
                async with get_worker_db_context() as db:
                    events = await AgentRunRepository(db).events(run.id, 0)
                    event = next(e for e in events if e.kind == "python_result")
                    assert "artifact_files" not in event.data
                    assert "content_base64" not in str(event.data)
                    assert event.data["artifacts"][0]["name"] == "结果.csv"
                    assert len(await RunArtifactService(db, a).list(run.id)) == 1

    asyncio.run(check())
