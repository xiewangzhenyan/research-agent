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
                assert first[0]["validation"]["structure"] == "checked"
                assert first[0]["validation"]["sha256"] == first[0]["sha256"]
                assert first[0]["validation"]["content_validation"] == "not_verified"
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
                response = await download_artifact(run.id, fid, user, project_id=None, db=db)
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


def test_structural_check_is_atomic_and_cannot_be_self_assigned():
    from app.services.artifact_validation import ArtifactValidationError

    async def check():
        async with users() as (a, _):
            run = await create(a)
            async with get_worker_db_context() as db:
                row = await db.get(AgentRun, run.id)
                row.status, row.attempt = "running", 1
            good = validate_artifacts([artifact()], "completed")[0]
            bad = validate_artifacts(
                [artifact(b"broken", name="bad.json", mime_type="application/json")], "completed"
            )[0]
            async with get_worker_db_context() as db:
                with pytest.raises(ArtifactValidationError):
                    await RunArtifactService(db, a).save(run.id, 1, uuid4(), [good, bad])
                assert await RunArtifactService(db, a).list(run.id) == []
            async with get_worker_db_context() as db:
                saved = await RunArtifactService(db, a).save(
                    run.id, 1, uuid4(), [{**good, "validation": {"content_validation": "accepted"}}]
                )
                assert saved[0]["validation"]["content_validation"] == "not_verified"
            async with get_worker_db_context() as db:
                assert (await RunArtifactService(db, a).list(run.id))[0]["validation"] == saved[0][
                    "validation"
                ]

    asyncio.run(check())


def test_python_can_repair_invalid_output_without_saving_the_invalid_file():
    import json

    from app.core.config import settings
    from app.worker.agent_runs import try_run
    from tests.model_fixtures import ScriptedModel, tool_delta
    from tests.test_agent_runs_integration import get

    async def stream(messages, info):
        returned = [
            p for p in messages if p.type == "tool" and getattr(p, "name", None) == "run_python"
        ]
        if len(returned) == 2:
            yield "已生成并检查 JSON 格式，计算内容仍待复核。"
        else:
            yield {
                0: tool_delta(
                    name="run_python",
                    tool_call_id=f"json-{len(returned)}",
                    json_args=json.dumps({"code": f"print({len(returned)})"}),
                )
            }

    async def check():
        async with users() as (a, _):
            responses = []
            for data in [b"broken", b'{"value": 2}']:
                responses.append(
                    {
                        "state": "completed",
                        "execution_id": str(uuid4()),
                        "exit_code": 0,
                        "artifact_files": validate_artifacts(
                            [artifact(data, name="result.json", mime_type="application/json")],
                            "completed",
                        ),
                    }
                )
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
                    sandbox_client, "run_python", AsyncMock(side_effect=responses)
                ) as remote,
                patch(
                    "app.agents.assistant._build_model",
                    return_value=ScriptedModel(stream_function=stream),
                ),
            ):
                run = await create(a, tools=["run_python"])
                await try_run(run.id)
                saved = await get(a, run.id)
                assert saved.status == "completed", saved.error
                assert remote.await_count == 2
                async with get_worker_db_context() as db:
                    files = await RunArtifactService(db, a).list(run.id)
                    assert len(files) == 1
                    assert "json_syntax" in files[0]["validation"]["checks"]
                    assert files[0]["validation"]["content_validation"] == "not_verified"

    asyncio.run(check())


@pytest.mark.parametrize("named_project", [False, True])
def test_file_task_graph_persists_metadata_without_binary_events(named_project):
    from app.core.config import settings
    from app.repositories.agent_run import AgentRunRepository
    from app.schemas.agent_run import AgentRunCreate
    from app.schemas.project import ProjectWrite
    from app.services.agent_run import AgentRunService
    from app.services.project import ProjectService
    from app.worker.agent_runs import try_run
    from tests.model_fixtures import ScriptedModel, tool_delta

    async def stream(messages, info):
        if any(getattr(p, "name", None) == "run_python" and p.type == "tool" for p in messages):
            yield "文件已生成"
        else:
            yield {
                0: tool_delta(
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
                    return_value=ScriptedModel(stream_function=stream),
                ),
            ):
                project_id = None
                async with get_worker_db_context() as db:
                    if named_project:
                        project_id = (
                            await ProjectService(db, a).save(ProjectWrite(name="Compute"))
                        ).id
                    run = await AgentRunService(db, a, project_id=project_id).create(
                        AgentRunCreate(
                            idempotency_key=uuid4(), prompt="Create a file", tools=["run_python"]
                        )
                    )
                await try_run(run.id)
                async with get_worker_db_context() as db:
                    saved = await AgentRunService(db, a, project_id=project_id).get(run.id)
                assert saved.status == "completed", saved.error
                remote.assert_awaited_once_with(run.id, "print(1)", protocol=2, inputs=[])
                async with get_worker_db_context() as db:
                    events = await AgentRunRepository(db).events(run.id, 0)
                    event = next(e for e in events if e.kind == "python_result")
                    assert "artifact_files" not in event.data
                    assert "content_base64" not in str(event.data)
                    assert event.data["artifacts"][0]["name"] == "结果.csv"
                    assert (
                        len(await RunArtifactService(db, a, project_id=project_id).list(run.id))
                        == 1
                    )

    asyncio.run(check())
