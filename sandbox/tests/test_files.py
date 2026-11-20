import asyncio
import base64
import hashlib
import io
import json
import tarfile
from uuid import uuid4

import httpx
import pytest
from sandbox.files import InputFile, input_archive, parse_artifacts, parse_completion
from sandbox.manager import Execution, Manager, create_app
from test_manager import IMAGE, FakeEngine


def archive(name="outputs/结果.csv", data=b"a,b\n1,2", kind=tarfile.REGTYPE, pax=None):
    out = io.BytesIO()
    with tarfile.open(fileobj=out, mode="w") as tar:
        item = tarfile.TarInfo(name)
        item.type, item.size, item.pax_headers = kind, len(data), pax or {}
        if kind in (tarfile.SYMTYPE, tarfile.LNKTYPE):
            item.linkname = "/etc/passwd"
            item.size = 0
        tar.addfile(item, io.BytesIO(data) if item.isreg() else None)
    return out.getvalue()


def output_bundle(entries):
    out = io.BytesIO()
    with tarfile.open(fileobj=out, mode="w") as tar:
        root = tarfile.TarInfo("outputs")
        root.type = tarfile.DIRTYPE
        tar.addfile(root)
        for name, data, kind in entries:
            item = tarfile.TarInfo(name)
            item.type = kind
            item.size = len(data) if item.isreg() else 0
            if item.issym() or item.islnk():
                item.linkname = "/etc/passwd"
            tar.addfile(item, io.BytesIO(data) if item.isreg() else None)
    return out.getvalue()


def test_unicode_roundtrip_and_completion():
    item = InputFile(
        name="输入.csv",
        content_base64=base64.b64encode(b"a").decode(),
        sha256=hashlib.sha256(b"a").hexdigest(),
    )
    with tarfile.open(fileobj=io.BytesIO(input_archive([item]))) as tar:
        member = tar.getmembers()[0]
        assert member.name == "输入.csv" and member.mode == 0o444
        assert member.uid == member.gid == 65532
    result = parse_artifacts(archive())
    assert result[0]["name"] == "结果.csv"
    assert base64.b64decode(result[0]["content_base64"]) == b"a,b\n1,2"
    assert parse_completion(archive(".execution-result.json", b'{"exit_code":0}')) == {
        "exit_code": 0
    }


@pytest.mark.parametrize(
    "name,kind",
    [
        ("outputs/../secret.txt", tarfile.REGTYPE),
        ("/outputs/x.txt", tarfile.REGTYPE),
        ("outputs/a.html", tarfile.REGTYPE),
        ("outputs/x.txt", tarfile.SYMTYPE),
        ("outputs/x.txt", tarfile.LNKTYPE),
        ("outputs/x.txt", tarfile.CHRTYPE),
        ("outputs/x.txt", tarfile.DIRTYPE),
    ],
)
def test_reject_unsafe_archives(name, kind):
    with pytest.raises(ValueError):
        parse_artifacts(archive(name, kind=kind))


def test_reject_oversize_truncated_and_sparse():
    with pytest.raises(ValueError):
        parse_artifacts(archive(data=b"a" * (2 * 1024**2 + 1)))
    with pytest.raises((ValueError, tarfile.TarError)):
        parse_artifacts(archive(data=b"a" * 10000)[:1600])
    with pytest.raises((ValueError, tarfile.TarError, KeyError)):
        parse_artifacts(archive(pax={"GNU.sparse.size": "100"}))
    with pytest.raises(ValueError):
        parse_completion(archive(".execution-result.json", b'{"exit_code":true}'))
    with pytest.raises(ValueError):
        parse_completion(archive(".execution-result.json", kind=tarfile.SYMTYPE))


@pytest.mark.parametrize(
    "marker_name", [".execution-result.json", "outputs/.execution-result.json"]
)
def test_completed_bundle_keeps_ten_user_files_and_excludes_internal_marker(marker_name):
    raw = output_bundle(
        [(marker_name, b'{"exit_code":0}', tarfile.REGTYPE)]
        + [(f"outputs/result-{i}.csv", b"value\n3\n", tarfile.REGTYPE) for i in range(10)]
    )
    results = parse_artifacts(raw, completion={"exit_code": 0})
    assert {row["name"] for row in results} == {f"result-{i}.csv" for i in range(10)}
    assert all(base64.b64decode(row["content_base64"]) == b"value\n3\n" for row in results)


@pytest.mark.parametrize(
    "markers",
    [
        [],
        [("outputs/.execution-result.json", b'{"exit_code":1}', tarfile.REGTYPE)],
        [("outputs/.execution-result.json", b'{"exit_code":false}', tarfile.REGTYPE)],
        [("outputs/.execution-result.json", b"not-json", tarfile.REGTYPE)],
        [("outputs/.execution-result.json", b"", tarfile.SYMTYPE)],
        [("outputs/.execution-result.json", b"", tarfile.LNKTYPE)],
        [("outputs/.execution-result.json", b"x" * 129, tarfile.REGTYPE)],
        [("outputs/.execution-result.json", b'{"exit_code":0}', tarfile.REGTYPE)] * 2,
        [("outputs/.other.json", b'{"exit_code":0}', tarfile.REGTYPE)],
    ],
)
def test_collecting_success_requires_one_matching_regular_completion_marker(markers):
    with pytest.raises(ValueError):
        parse_artifacts(
            output_bundle(markers + [("outputs/result.csv", b"a\n1\n", tarfile.REGTYPE)]),
            completion={"exit_code": 0},
        )


def test_marker_exception_does_not_relax_file_count_or_hidden_path_rules():
    marker = ("outputs/.execution-result.json", b'{"exit_code":0}', tarfile.REGTYPE)
    with pytest.raises(ValueError):
        parse_artifacts(output_bundle([marker]))
    with pytest.raises(ValueError):
        parse_artifacts(
            output_bundle(
                [marker]
                + [(f"outputs/file-{i}.csv", b"a\n1\n", tarfile.REGTYPE) for i in range(11)]
            ),
            completion={"exit_code": 0},
        )


class FileEngine(FakeEngine):
    def __init__(self, bad=False, exit_code=0):
        super().__init__()
        self.bad, self.exit_code, self.staged, self.cleaned = bad, exit_code, [], []
        self.paused = False

    async def stage_inputs(self, image, body, output_volume=None):
        self.staged.append(body)

    async def remove_input_volume(self, job):
        self.cleaned.append(str(job))

    async def inspect(self, name):
        job = self.jobs.get(name)
        return (
            {"State": {"Running": job["running"], "Paused": self.paused, "ExitCode": 0}}
            if job
            else None
        )

    async def pause(self, name):
        self.paused = True

    async def archive(self, name, path, limit):
        if path.endswith(".execution-result.json"):
            return archive(
                ".execution-result.json", json.dumps({"exit_code": self.exit_code}).encode()
            )
        assert self.paused, "Files must be frozen before collection"
        # The real Docker directory archive includes the supervisor marker.
        return output_bundle(
            [
                ("outputs/.execution-result.json", b'{"exit_code":0}', tarfile.REGTYPE),
                (
                    "outputs/../../secret.txt" if self.bad else "outputs/结果.csv",
                    b"a,b\n1,2",
                    tarfile.REGTYPE,
                ),
            ]
        )


@pytest.mark.parametrize(
    "bad,exit_code,state,count",
    [(False, 0, "completed", 1), (True, 0, "failed", 0), (False, 1, "failed", 0)],
)
def test_file_execution_freezes_collects_cleans_and_replays(tmp_path, bad, exit_code, state, count):
    async def check():
        engine = FileEngine(bad, exit_code)
        manager = Manager(tmp_path / "jobs.db", IMAGE, engine)
        body = Execution(id=uuid4(), run_id=uuid4(), code="print(2)", protocol=2)
        await manager.submit(body)
        await asyncio.gather(*list(manager.tasks.values()))
        row = manager.row(body.id)
        result = manager.public(row)
        assert result["state"] == state
        assert len(result["result"]["artifacts"]) == count
        assert row["request_json"] is None and not row["code"]
        assert str(body.id) in engine.cleaned and not engine.jobs
        assert await manager.submit(body) == result and engine.creates == 1

    asyncio.run(check())


def test_body_limit_before_json_parsing(tmp_path):
    async def check():
        app = create_app(Manager(tmp_path / "jobs.db", IMAGE, FileEngine()), token="a" * 64)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/executions",
                content=b" " * (8 * 1024**2 + 1),
                headers={"Authorization": "Bearer " + "a" * 64, "Content-Type": "application/json"},
            )
            assert response.status_code == 413

    asyncio.run(check())


def test_file_timeout_and_stop_confirmation(tmp_path, monkeypatch):
    from sandbox.manager import LIMITS

    monkeypatch.setitem(LIMITS, "timeout_seconds", 0.02)

    async def check():
        engine = FileEngine()

        async def slow_archive(*args):
            await asyncio.sleep(10)

        engine.archive = slow_archive
        manager = Manager(tmp_path / "jobs.db", IMAGE, engine)
        body = Execution(id=uuid4(), run_id=uuid4(), code="slow", protocol=2)
        await manager.submit(body)
        await asyncio.gather(*list(manager.tasks.values()))
        assert manager.row(body.id)["state"] == "timed_out"
        assert not engine.jobs

    asyncio.run(check())


def test_file_lost_running_container_never_reexecutes(tmp_path):
    import time

    async def check():
        engine = FileEngine()
        manager = Manager(tmp_path / "jobs.db", IMAGE, engine)
        body = Execution(id=uuid4(), run_id=uuid4(), code="print(1)", protocol=2)
        manager.db.execute(
            "INSERT INTO jobs(id,run_id,hash,code,state,created,result,request_json) VALUES(?,?,?,?,?,?,NULL,?)",
            (
                str(body.id),
                str(body.run_id),
                "hash",
                body.code,
                "running",
                time.time(),
                body.model_dump_json(),
            ),
        )
        manager.db.commit()
        await manager.execute(str(body.id))
        assert manager.row(body.id)["state"] == "failed" and engine.creates == 0

    asyncio.run(check())
