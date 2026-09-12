import asyncio
import base64
import hashlib
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.core.exceptions import BadRequestError, ExternalServiceError, NotFoundError
from app.services import sandbox_client
from app.services.sandbox_files import load_inputs, validate_artifacts


def artifact(data=b"a,b\n1,2", **changes):
    return {
        "name": "结果.csv",
        "mime_type": "text/csv",
        "size": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "content_base64": base64.b64encode(data).decode(),
        **changes,
    }


@pytest.mark.parametrize(
    "changes",
    [
        {"name": "../x.csv"},
        {"mime_type": "text/html"},
        {"size": True},
        {"sha256": "0" * 64},
        {"content_base64": "%%%"},
        {"size": 0},
    ],
)
def test_reject_corrupt_artifact(changes):
    with pytest.raises(ExternalServiceError):
        validate_artifacts([artifact(**changes)], "completed")


def test_bundle_validation_and_no_failed_artifacts():
    assert validate_artifacts([artifact()], "completed")[0]["content"] == b"a,b\n1,2"
    for files, state in [
        ([artifact(), artifact()], "completed"),
        ([artifact()], "failed"),
        ([artifact(b"a" * (2 * 1024**2 + 1))], "completed"),
    ]:
        with pytest.raises(ExternalServiceError):
            validate_artifacts(files, state)


def test_input_owner_and_content_snapshot(tmp_path):
    async def check():
        uid, fid = uuid4(), uuid4()
        path = tmp_path / "data.csv"
        path.write_bytes(b"a,b\n1,2")
        row = SimpleNamespace(id=fid, filename="数据.csv", size=7, storage_path="data.csv")
        with (
            patch(
                "app.services.sandbox_files.FileUploadService.get_user_file",
                AsyncMock(return_value=row),
            ) as owned,
            patch(
                "app.services.sandbox_files.get_file_storage",
                return_value=SimpleNamespace(get_full_path=lambda _: path),
            ),
        ):
            inputs, snapshot = await load_inputs(None, uid, [fid])
            owned.assert_awaited_once_with(fid, uid)
            assert inputs[0]["name"].startswith(fid.hex)
            path.write_bytes(b"a,b\n3,4")
            with pytest.raises(BadRequestError):
                await load_inputs(None, uid, [fid], snapshot)
            with pytest.raises(BadRequestError):
                await load_inputs(None, uid, [fid, fid])
        with (
            patch(
                "app.services.sandbox_files.FileUploadService.get_user_file",
                AsyncMock(side_effect=NotFoundError(message="missing")),
            ),
            pytest.raises(NotFoundError),
        ):
            await load_inputs(None, uuid4(), [fid])

    asyncio.run(check())


def test_client_v2_identity_changes_with_input_and_rejects_false_success():
    async def check():
        ids = []

        async def remote(method, path, payload=None, **kwargs):
            ids.append(payload["id"])
            return {
                **payload,
                "state": "completed",
                "result": {"exit_code": 0, "artifacts": [artifact()]},
            }

        with patch.object(sandbox_client, "request", remote):
            run = uuid4()
            first = await sandbox_client.run_python(run, "print(1)", protocol=2, inputs=[])
            await sandbox_client.run_python(run, "print(1)", protocol=2, inputs=[])
            await sandbox_client.run_python(
                run, "print(1)", protocol=2, inputs=[{"name": "x.txt", "sha256": "a"}]
            )
            assert ids[0] == ids[1] != ids[2]
            assert first["artifact_files"][0]["content"] == b"a,b\n1,2"

        async def lying(method, path, payload=None, **kwargs):
            return {**payload, "state": "completed", "result": {"exit_code": 1}}

        with patch.object(sandbox_client, "request", lying), pytest.raises(ExternalServiceError):
            await sandbox_client.run_python(uuid4(), "print(1)", protocol=2)

    asyncio.run(check())
