import asyncio
from uuid import uuid4

import httpx
import pytest
from fastapi import HTTPException
from sandbox.manager import Engine, Execution, Manager, container_spec, create_app, decode_logs

IMAGE = "sha256:" + "a" * 64


class FakeEngine:
    def __init__(self):
        self.jobs = {}
        self.creates = 0
        self.available = True
        self.cannot_stop = False

    async def ready(self, image):
        if not self.available:
            raise RuntimeError("runtime absent")

    async def probe(self, image):
        await self.ready(image)

    async def inspect(self, name):
        job = self.jobs.get(name)
        if job and job["code"] != "slow":
            job["running"] = False
        return {"State": {"Running": job["running"], "ExitCode": 0}} if job else None

    async def ensure(self, name, spec):
        if name not in self.jobs:
            self.creates += 1
            self.jobs[name] = {"code": spec["Cmd"][0], "running": True}

    async def logs(self, name):
        return {"stdout": "2\n", "stderr": "", "truncated": False}

    async def stop(self, name):
        if self.cannot_stop:
            raise RuntimeError("daemon unreachable")
        if name in self.jobs:
            self.jobs[name]["running"] = False

    async def remove(self, name):
        self.jobs.pop(name, None)


def test_container_policy_has_no_business_access():
    spec = container_spec(IMAGE, "print(1+1)", uuid4(), uuid4())
    host = spec["HostConfig"]
    assert spec["User"] == "65532:65532"
    assert spec["NetworkDisabled"] and host["NetworkMode"] == "none"
    assert host["Runtime"] == "runsc" and host["ReadonlyRootfs"]
    assert host["CapDrop"] == ["ALL"] and host["SecurityOpt"] == ["no-new-privileges:true"]
    assert not host.get("Binds") and not host.get("Devices")
    assert host["Memory"] == host["MemorySwap"] == 256 * 1024**2
    assert host["PidsLimit"] == 64 and host["NanoCpus"] == 1000000000
    assert all("size=" in mount for mount in host["Tmpfs"].values())
    assert spec["Entrypoint"] == ["python", "-I", "-B", "-c"]
    assert not any("TOKEN" in env or "PASSWORD" in env for env in spec["Env"])
    with pytest.raises(ValueError):
        container_spec("python:latest", "print(1)", uuid4(), uuid4())


def test_decode_logs_separates_streams_and_bounds_output():
    def frame(channel, payload):
        return bytes([channel, 0, 0, 0]) + len(payload).to_bytes(4, "big") + payload

    result = decode_logs(frame(1, "中文\n".encode()) + frame(2, b"error"))
    assert result == {"stdout": "中文\n", "stderr": "error", "truncated": False}
    large = decode_logs(frame(1, b"x" * 100000))
    assert len(large["stdout"]) == 32768 and large["truncated"]
    assert decode_logs(frame(1, b"hello")[:-2])["truncated"]
    invalid = decode_logs(frame(1, b"\xff" * 20000))
    assert len(invalid["stdout"].encode()) <= 32768 and invalid["truncated"]


def test_idempotency_conflicts_and_restart_read(tmp_path):
    async def check():
        engine = FakeEngine()
        path = tmp_path / "jobs.db"
        manager = Manager(path, IMAGE, engine)
        body = Execution(id=uuid4(), run_id=uuid4(), code="print(1+1)")
        await asyncio.gather(manager.submit(body), manager.submit(body))
        await asyncio.gather(*list(manager.tasks.values()))
        assert engine.creates == 1
        saved = manager.public(manager.row(body.id))
        assert saved["state"] == "completed" and saved["result"]["stdout"] == "2\n"
        with pytest.raises(HTTPException) as conflict:
            await manager.submit(body.model_copy(update={"code": "different"}))
        assert conflict.value.status_code == 409
        reopened = Manager(path, IMAGE, engine)
        assert (await reopened.submit(body)) == saved
        assert engine.creates == 1

    asyncio.run(check())


def test_missing_runtime_refuses_without_creating_job(tmp_path):
    async def check():
        engine = FakeEngine()
        engine.available = False
        manager = Manager(tmp_path / "jobs.db", IMAGE, engine)
        body = Execution(id=uuid4(), run_id=uuid4(), code="print(1)")
        with pytest.raises(RuntimeError):
            await manager.submit(body)
        assert manager.row(body.id) is None
        assert not engine.creates

    asyncio.run(check())


def test_cancel_tombstone_and_confirmation(tmp_path):
    async def check():
        engine = FakeEngine()
        manager = Manager(tmp_path / "jobs.db", IMAGE, engine)
        body = Execution(id=uuid4(), run_id=uuid4(), code="slow")
        await manager.submit(body)
        while not engine.jobs:
            await asyncio.sleep(0)
        engine.cannot_stop = True
        with pytest.raises(RuntimeError):
            await manager.cancel(body.run_id)
        assert manager.row(body.id)["state"] == "running"
        engine.cannot_stop = False
        assert (await manager.cancel(body.run_id))["stopped"]
        await asyncio.gather(*list(manager.tasks.values()))
        assert manager.row(body.id)["state"] == "cancelled"
        with pytest.raises(HTTPException) as rejected:
            await manager.submit(Execution(id=uuid4(), run_id=body.run_id, code="print(2)"))
        assert rejected.value.status_code == 409

    asyncio.run(check())


def test_missing_container_on_restart_does_not_reexecute(tmp_path):
    async def check():
        engine = FakeEngine()
        manager = Manager(tmp_path / "jobs.db", IMAGE, engine)
        body = Execution(id=uuid4(), run_id=uuid4(), code="print(1)")
        import time

        manager.db.execute(
            "INSERT INTO jobs(id,run_id,hash,code,state,created,result) VALUES(?,?,?,?,?,?,NULL)",
            (str(body.id), str(body.run_id), "hash", body.code, "running", time.time()),
        )
        manager.db.commit()
        await manager.execute(str(body.id))
        assert manager.row(body.id)["state"] == "failed"
        assert engine.creates == 0

    asyncio.run(check())


def test_control_api_requires_auth_and_redacts_failures(tmp_path):
    async def check():
        engine = FakeEngine()
        engine.available = False
        app = create_app(Manager(tmp_path / "jobs.db", IMAGE, engine), token="a" * 64)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            assert (await client.get("/health")).status_code in (401, 403)
            assert (
                await client.get("/health", headers={"Authorization": "Bearer wrong"})
            ).status_code == 401
            response = await client.get("/health", headers={"Authorization": "Bearer " + "a" * 64})
            assert response.status_code == 503
            assert "runtime absent" not in response.text

    asyncio.run(check())


def test_real_engine_rejects_runc_only_info():
    async def check():
        engine = Engine()
        await engine.http.aclose()

        async def respond(request):
            return httpx.Response(200, json={"Runtimes": {"runc": {}}})

        engine.http = httpx.AsyncClient(
            transport=httpx.MockTransport(respond), base_url="http://engine"
        )
        try:
            with pytest.raises(RuntimeError, match="gVisor"):
                await engine.ready(IMAGE)
        finally:
            await engine.http.aclose()

    asyncio.run(check())


def test_timeout_stops_execution_before_saving_terminal(tmp_path, monkeypatch):
    from sandbox.manager import LIMITS

    monkeypatch.setitem(LIMITS, "timeout_seconds", 0.01)

    async def check():
        engine = FakeEngine()
        manager = Manager(tmp_path / "jobs.db", IMAGE, engine)
        body = Execution(id=uuid4(), run_id=uuid4(), code="slow")
        await manager.submit(body)
        await asyncio.gather(*list(manager.tasks.values()))
        assert manager.row(body.id)["state"] == "timed_out"
        assert not engine.jobs

    asyncio.run(check())


def test_excess_output_stops_job(tmp_path):
    async def check():
        engine = FakeEngine()

        async def overflow(name):
            return {"stdout": "x" * 32768, "stderr": "", "truncated": True}

        engine.logs = overflow
        manager = Manager(tmp_path / "jobs.db", IMAGE, engine)
        body = Execution(id=uuid4(), run_id=uuid4(), code="slow")
        await manager.submit(body)
        await asyncio.gather(*list(manager.tasks.values()))
        assert manager.row(body.id)["state"] == "output_limit"
        assert not engine.jobs

    asyncio.run(check())


def test_raw_log_cut_is_reported_even_at_a_frame_boundary():
    async def check():
        engine = Engine()
        await engine.http.aclose()

        async def respond(request):
            return httpx.Response(200, content=b"\x01\0\0\0\0\0\0\0" * 6000)

        engine.http = httpx.AsyncClient(
            transport=httpx.MockTransport(respond), base_url="http://engine"
        )
        try:
            assert (await engine.logs("test"))["truncated"]
        finally:
            await engine.http.aclose()

    asyncio.run(check())
