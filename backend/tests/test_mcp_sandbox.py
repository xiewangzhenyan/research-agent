import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.core.config import settings
from app.core.exceptions import BadRequestError, ExternalServiceError
from app.services import mcp_sandbox
from app.services.mcp_connections import exchange


def setup(monkeypatch):
    monkeypatch.setattr(settings, "SANDBOX_URL", "http://127.0.0.1:38006")
    monkeypatch.setattr(settings, "SANDBOX_TOKEN", "dummy-" * 10)
    monkeypatch.setattr(settings, "SANDBOX_MCP_IMAGE_ID", "sha256:" + "a" * 64)
    monkeypatch.setattr(mcp_sandbox, "_health_cache", None)
    monkeypatch.setattr(mcp_sandbox.sandbox_client, "configured", lambda: True)
    return {
        "status": "ready",
        "protocol": 1,
        "runtime": "runsc",
        "network": "none",
        "image": settings.SANDBOX_MCP_IMAGE_ID,
    }


@pytest.mark.parametrize(
    "changed",
    [{"image": "sha256:wrong"}, {"runtime": "runc"}, {"network": "bridge"}, {"protocol": 2}, {}],
)
def test_health_requires_exact_mcp_runtime_and_caches(monkeypatch, changed):
    data = setup(monkeypatch)
    request = AsyncMock(return_value={**data, **changed})
    monkeypatch.setattr(mcp_sandbox.sandbox_client, "request", request)

    async def check():
        assert (await mcp_sandbox.health())["status"] == ("unavailable" if changed else "ready")
        await mcp_sandbox.health()
        assert request.await_count == 1
        monkeypatch.setattr(settings, "SANDBOX_TOKEN", "rotated-" * 10)
        await mcp_sandbox.health()
        assert request.await_count == 2

    asyncio.run(check())


def test_missing_or_failed_runtime_never_dispatches(monkeypatch):
    setup(monkeypatch)
    request = AsyncMock(side_effect=ExternalServiceError(message="offline"))
    monkeypatch.setattr(mcp_sandbox.sandbox_client, "request", request)

    async def check():
        assert (await mcp_sandbox.health())["status"] == "unavailable"
        with pytest.raises(BadRequestError):
            await mcp_sandbox.exchange(
                {"command": "python"}, {}, operation="discover", name=None, arguments=None
            )
        monkeypatch.setattr(settings, "SANDBOX_MCP_IMAGE_ID", "")
        assert (await mcp_sandbox.health())["status"] == "not_configured"
        assert request.await_count == 1

    asyncio.run(check())


def test_stdio_uses_gateway_with_run_identity_and_validates_result(monkeypatch):
    setup(monkeypatch)
    monkeypatch.setattr(mcp_sandbox, "health", AsyncMock(return_value={"status": "ready"}))
    request = AsyncMock(return_value={"result": {"content": []}})
    monkeypatch.setattr(mcp_sandbox.sandbox_client, "request", request)
    asset = SimpleNamespace(
        config={"transport": "stdio", "command": "python", "args": ["-m", "demo"]}, secret=None
    )
    run = uuid4()

    async def check():
        assert await exchange(asset, "call", name="tool", arguments={"q": 1}, run_id=run) == {
            "content": []
        }
        payload = request.call_args.args[2]
        assert payload["run_id"] == str(run) and payload["arguments"] == {"q": 1}
        assert payload["env"] == {}
        request.return_value = {"result": "bad"}
        with pytest.raises(ExternalServiceError):
            await exchange(asset)

    asyncio.run(check())


@pytest.mark.parametrize(
    "capabilities,expected",
    [
        ([{"kind": "mcp", "transport": "stdio"}], True),
        ([{"kind": "mcp"}], True),
        ([{"kind": "mcp", "transport": "streamable-http"}], False),
        ([{"kind": "skill", "transport": None}], False),
    ],
)
def test_cancellation_stops_stdio_without_python_permission(monkeypatch, capabilities, expected):
    from app.worker.agent_runs import stop_sandbox

    cancel = AsyncMock()
    monkeypatch.setattr(mcp_sandbox.sandbox_client, "cancel_run", cancel)
    run = uuid4()
    asyncio.run(stop_sandbox(run, {"tools": [], "capabilities": capabilities}))
    assert cancel.await_count == int(expected)
