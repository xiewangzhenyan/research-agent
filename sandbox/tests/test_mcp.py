import asyncio
import json
from uuid import uuid4

import httpx
import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sandbox.manager import Manager, container_spec, create_app
from sandbox.mcp_gateway import MCPGateway, MCPRequest

IMAGE = "sha256:" + "a" * 64


class Engine:
    def __init__(self):
        self.jobs, self.specs = {}, []
        self.stops = []
        self.result = {"ok": True, "result": {"tools": [], "resources": [], "prompts": []}}
        self.slow = False

    async def ready(self, image):
        assert image == IMAGE

    async def ensure(self, name, spec):
        self.jobs[name] = spec
        self.specs.append(spec)

    async def inspect(self, name):
        return {"State": {"Running": self.slow, "ExitCode": 0}} if name in self.jobs else None

    async def logs(self, name):
        return {"stdout": json.dumps(self.result), "truncated": False}

    async def remove(self, name):
        self.jobs.pop(name, None)

    async def stop(self, name):
        self.stops.append(name)
        if name in self.jobs:
            self.jobs.pop(name)


def gateway(tmp_path):
    engine = Engine()
    runner = Manager(tmp_path / "jobs.db", IMAGE, engine)
    runner.slots = asyncio.Semaphore(1)
    return MCPGateway(runner, IMAGE, container_spec)


@pytest.mark.parametrize(
    "patch",
    [
        {"command": "sh"},
        {"command": "npx"},
        {"args": ["x" * 1001]},
        {"env": {"BAD=NAME": "secret"}},
        {"env": {"KEY": "x\ny"}},
        {"env": {"KEY": "x" * 21000}},
        {"arguments": {"x": "y" * 6100}},
        {"operation": "call"},
        {"args": ["\x00"]},
    ],
)
def test_untrusted_request_limits(patch):
    with pytest.raises(ValidationError):
        MCPRequest(**{"run_id": uuid4(), "command": "python", **patch})


def test_isolation_real_health_and_cleanup(tmp_path):
    async def check():
        g = gateway(tmp_path)
        assert (await g.health())["status"] == "ready"
        await g.health()
        assert len(g.runner.engine.specs) == 1
        spec = g.runner.engine.specs[0]
        assert spec["HostConfig"]["Runtime"] == "runsc"
        assert spec["NetworkDisabled"] and spec["User"] == "65532:65532"
        assert spec["HostConfig"]["ReadonlyRootfs"]
        assert not spec["HostConfig"].get("Mounts")
        assert not g.runner.engine.jobs and not g.active
        assert g.runner.slots._value == 1
        assert g.runner.db.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 0

    asyncio.run(check())


def test_failed_exchange_does_not_return_secrets_and_releases_slot(tmp_path):
    async def check():
        g = gateway(tmp_path)
        g.runner.engine.result = {"ok": False, "error": "a-secret"}
        with pytest.raises(HTTPException) as caught:
            await g.execute(MCPRequest(run_id=uuid4(), command="python", env={"KEY": "a-secret"}))
        assert "a-secret" not in caught.value.detail
        assert not g.runner.engine.jobs and g.runner.slots._value == 1

    asyncio.run(check())


def test_cancelled_request_and_run_leave_no_process(tmp_path):
    async def check():
        g = gateway(tmp_path)
        g.runner.engine.slow = True
        run_id = uuid4()
        body = MCPRequest(run_id=run_id, command="python")
        task = asyncio.create_task(g.execute(body))
        while not g.active:
            await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert not g.runner.engine.jobs and g.runner.slots._value == 1
        task = asyncio.create_task(g.execute(body))
        while not g.active:
            await asyncio.sleep(0)
        await g.runner.cancel(run_id)
        await g.cancel(run_id)
        assert len(g.runner.engine.stops) == 1
        with pytest.raises(HTTPException):
            await task
        with pytest.raises(HTTPException) as caught:
            await g.execute(body)
        assert caught.value.status_code == 409
        assert not g.runner.engine.jobs

    asyncio.run(check())


def test_python_and_stdio_share_budget(tmp_path):
    async def check():
        g = gateway(tmp_path)
        await g.runner.slots.acquire()
        with pytest.raises(HTTPException) as caught:
            await g.execute(MCPRequest(run_id=uuid4(), command="python"))
        assert caught.value.status_code == 429
        assert not g.runner.engine.specs

    asyncio.run(check())


def test_api_auth_and_validation_never_echo_credentials(tmp_path, monkeypatch):
    async def check():
        g = gateway(tmp_path)
        monkeypatch.setenv("SANDBOX_MCP_IMAGE", IMAGE)
        app = create_app(g.runner, token="t" * 64)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            assert (await client.get("/mcp/health")).status_code in (401, 403)
            r = await client.post(
                "/mcp/exchange",
                headers={"Authorization": "Bearer " + "t" * 64},
                json={"run_id": str(uuid4()), "command": "npx", "env": {"KEY": "a-secret"}},
            )
            assert r.status_code == 422 and "a-secret" not in r.text

    asyncio.run(check())
