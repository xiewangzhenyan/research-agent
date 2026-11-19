"""Task output reuse checks byte integrity without claiming content correctness."""

import asyncio
import base64
import hashlib
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.core.exceptions import BadRequestError, NotFoundError
from app.services.sandbox_files import INPUT_LIMIT, input_name, load_execution_inputs


def fixture():
    content = b"a,b\n1,2"
    item = SimpleNamespace(
        id=uuid4(),
        run_id=uuid4(),
        name="../data.csv",
        size=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
        content=content,
    )
    ref = {
        key: str(getattr(item, key)) if key in {"id", "run_id"} else getattr(item, key)
        for key in ("id", "run_id", "name", "size", "sha256")
    }
    snapshot = json.dumps(
        {
            "version": "work-context-v1",
            "task_id": str(uuid4()),
            "revision": 2,
            "requirements": [],
            "artifacts": [ref],
            "previous_results": [],
        }
    )
    request = {
        "work_task": {"id": json.loads(snapshot)["task_id"], "revision": 2},
        "sandbox_protocol": 2,
    }
    return item, snapshot, request


@pytest.mark.parametrize(
    "failure",
    [
        None,
        "bytes",
        "digest",
        "name",
        "size",
        "deleted",
        "revision",
        "outside",
        "duplicate",
        "quota",
        "strict",
        "protocol",
        "unsupported",
        "no_task",
        "no_context",
    ],
)
def test_selected_artifact_inputs(failure):
    async def check():
        item, snapshot, request = fixture()
        selected = [item.id]
        current = snapshot
        records = []
        if failure == "bytes":
            item.content = b"a,b\n3,4"
        elif failure == "digest":
            item.sha256 = "0" * 64
        elif failure == "name":
            item.name = "changed.csv"
        elif failure == "size":
            item.size += 1
        elif failure == "revision":
            current = snapshot.replace('"revision": 2', '"revision": 3')
        elif failure == "outside":
            selected = [uuid4()]
        elif failure == "duplicate":
            selected *= 2
        elif failure == "quota":
            records = [{"size": INPUT_LIMIT}]
        elif failure == "strict":
            request.update(knowledge_base_ids=[str(uuid4())], knowledge_strict=True)
        elif failure == "protocol":
            request["sandbox_protocol"] = 1
        elif failure == "unsupported":
            item.name = "file.pdf"
        elif failure == "no_task":
            request.pop("work_task")
        elif failure == "no_context":
            snapshot = ""
        uid, project_id = uuid4(), uuid4()
        with (
            patch("app.services.sandbox_files.load_inputs", AsyncMock(return_value=([], records))),
            patch(
                "app.services.work_task.WorkTaskService.context", AsyncMock(return_value=current)
            ),
            patch(
                "app.services.run_artifact.RunArtifactService.get",
                AsyncMock(side_effect=NotFoundError(message="deleted"))
                if failure == "deleted"
                else AsyncMock(return_value=item),
            ) as get,
        ):

            async def load():
                return await load_execution_inputs(
                    None,
                    uid,
                    request,
                    artifact_ids=selected,
                    work_context=snapshot,
                    project_id=project_id,
                )

            if failure:
                with pytest.raises((BadRequestError, NotFoundError)):
                    await load()
            else:
                inputs, mounted = await load()
                get.assert_awaited_once_with(item.run_id, item.id)
                assert base64.b64decode(inputs[0]["content_base64"]) == item.content
                assert mounted[0]["sha256"] == item.sha256
                assert mounted[0]["run_id"] == str(item.run_id)
                assert inputs[0]["name"] == input_name(item.id, item.name)
                assert ".." not in inputs[0]["name"] and "/" not in inputs[0]["name"]
                assert "content_base64" not in str(mounted)

    asyncio.run(check())


def test_unselected_artifacts_are_not_loaded():
    async def check():
        with (
            patch("app.services.sandbox_files.load_inputs", AsyncMock(return_value=([], []))),
            patch("app.services.run_artifact.RunArtifactService.get", AsyncMock()) as get,
        ):
            assert await load_execution_inputs(None, uuid4(), {}) == ([], [])
            get.assert_not_awaited()

    asyncio.run(check())


def test_uploads_and_task_outputs_share_file_count_budget():
    async def check():
        item, snapshot, request = fixture()
        request["input_file_ids"] = [str(uuid4()) for _ in range(5)]
        with (
            patch("app.services.sandbox_files.load_inputs", AsyncMock()) as load,
            pytest.raises(BadRequestError, match="最多 5"),
        ):
            await load_execution_inputs(
                None, uuid4(), request, artifact_ids=[item.id], work_context=snapshot
            )
        load.assert_not_awaited()

    asyncio.run(check())
