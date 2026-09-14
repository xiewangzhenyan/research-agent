import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from pydantic_ai.models.function import FunctionModel

from app.agents.assistant import Deps, get_agent
from app.core.config import settings
from app.core.exceptions import AuthorizationError, ExternalServiceError
from app.services import sandbox_client
from app.services.tool_policy import resolve_tools, tool_catalog


def test_python_is_never_implicitly_authorized():
    async def check():
        user = SimpleNamespace(is_app_admin=True)
        with patch.object(sandbox_client, "health", AsyncMock(return_value={"status": "ready"})):
            assert await resolve_tools(user, None) == [
                "current_datetime",
                "ask_user",
                "create_document",
            ]
            assert await resolve_tools(user, []) == []
            assert await resolve_tools(user, ["run_python"]) == ["run_python"]
            with (
                patch.object(settings, "SANDBOX_ALLOW_PUBLIC", False),
                pytest.raises(AuthorizationError),
            ):
                await resolve_tools(SimpleNamespace(is_app_admin=False), ["run_python"])

    asyncio.run(check())


def test_unready_sandbox_and_missing_credentials_fail_closed():
    async def check():
        with patch.object(settings, "SANDBOX_URL", ""):
            assert (await sandbox_client.health())["status"] == "not_configured"
            with pytest.raises(ExternalServiceError):
                await sandbox_client.run_python(uuid4(), "print(1)")
            with pytest.raises(AuthorizationError):
                await resolve_tools(SimpleNamespace(is_app_admin=True), ["run_python"])
            catalog = await tool_catalog(SimpleNamespace(is_app_admin=False))
            assert not next(i["available"] for i in catalog["items"] if i["id"] == "run_python")
            assert "SANDBOX_TOKEN" not in str(catalog)

    asyncio.run(check())


def test_disabled_tools_are_not_advertised_to_model():
    async def model(messages, info):
        assert info.function_tools == []
        from pydantic_ai.messages import ModelResponse, TextPart

        return ModelResponse(parts=[TextPart("无需工具")])

    async def check():
        with patch("app.agents.assistant._build_model", return_value=FunctionModel(model)):
            result = await get_agent().agent.run("直接回答", deps=Deps(allowed_tools=()))
            assert result.output == "无需工具"

    asyncio.run(check())


def test_execution_ids_isolate_runs_and_reuse_identical_code():
    async def check():
        ids = []

        async def fake_request(method, path, payload=None, **kwargs):
            ids.append(payload["id"])
            return {
                **payload,
                "state": "completed",
                "result": {"stdout": "2", "stderr": "", "exit_code": 0},
            }

        with patch.object(sandbox_client, "request", fake_request):
            run = uuid4()
            await sandbox_client.run_python(run, "print(2)")
            await sandbox_client.run_python(run, "print(2)")
            await sandbox_client.run_python(uuid4(), "print(2)")
        assert ids[0] == ids[1] and ids[0] != ids[2]

    asyncio.run(check())


def test_foreign_execution_response_and_false_cancel_confirmation_rejected():
    async def check():
        with (
            patch.object(
                sandbox_client,
                "request",
                AsyncMock(return_value={"id": str(uuid4()), "state": "completed"}),
            ),
            pytest.raises(ExternalServiceError),
        ):
            await sandbox_client.run_python(uuid4(), "print(1)")
        with (
            patch.object(sandbox_client, "request", AsyncMock(return_value={"stopped": False})),
            pytest.raises(ExternalServiceError),
        ):
            await sandbox_client.cancel_run(uuid4())

    asyncio.run(check())
