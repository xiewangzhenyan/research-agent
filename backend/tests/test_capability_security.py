"""Untrusted packages, credential boundaries and real official-SDK protocol calls."""

import asyncio
import io
import json
import socket
import stat
import zipfile
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import httpx
import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr

from app.core.config import settings
from app.core.exceptions import BadRequestError
from app.services.capability_assets import seal, unseal
from app.services.mcp_connections import (
    PublicTransport,
    exchange,
    public_address,
    validate_secrets,
    validate_url,
)
from app.services.skill_packages import manifest, safe_path, unpack

ENTRY = (
    "---\nname: review-evidence\ndescription: 整理证据并保留来源\n---\n先检查来源，再给出结论。\n"
)


def zipped(members):
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w", zipfile.ZIP_DEFLATED) as z:
        for path, content in members:
            z.writestr(path, content)
    return b.getvalue()


@pytest.mark.parametrize(
    "path", ["../secret", "/etc/passwd", "a/../b", "a//b", "a\\b", "C:x", "a/./b", "a\0b"]
)
def test_paths_cannot_escape(path):
    with pytest.raises(BadRequestError):
        safe_path(path)


def test_packages_preserve_references_and_normalize_entry():
    meta, files = unpack(
        zipped(
            [
                ("demo/SKILL.md", ENTRY),
                ("demo/references/note.md", "资料"),
                ("demo/templates/image.png", b"\x89PNG"),
            ]
        ),
        "demo.zip",
    )
    assert meta["name"] == "review-evidence"
    assert set(files) == {"SKILL.md", "references/note.md", "templates/image.png"}
    assert (
        unpack(b"\xef\xbb\xbf" + ENTRY.replace("\n", "\r\n").encode(), "SKILL.md")[1]["SKILL.md"]
        == ENTRY.encode()
    )


@pytest.mark.parametrize(
    "members",
    [
        [("a/SKILL.md", ENTRY), ("b/SKILL.md", ENTRY)],
        [("a/SKILL.md", ENTRY), ("outside.txt", "outside")],
        [("SKILL.md", ENTRY), ("../escape", "bad")],
        [("SKILL.md", ENTRY), ("SKILL.md", ENTRY)],
        [("SKILL.md", ENTRY), ("huge", b"x" * 1100000)],
    ],
)
def test_unsafe_zip_members_are_rejected(members):
    with pytest.raises(BadRequestError):
        unpack(zipped(members), "skill.zip")


def test_symlinks_and_yaml_aliases_are_rejected():
    info = zipfile.ZipInfo("references/link")
    info.create_system = 3
    info.external_attr = (stat.S_IFLNK | 0o777) << 16
    with pytest.raises(BadRequestError):
        unpack(zipped([("SKILL.md", ENTRY), (info, "/etc/passwd")]), "s.zip")
    with pytest.raises(BadRequestError):
        manifest(ENTRY.replace("name: review-evidence", "name: &a review-evidence\ncopy: *a"))


def test_credentials_are_write_only_and_owner_asset_bound(monkeypatch):
    monkeypatch.setattr(
        settings, "CAPABILITY_ENCRYPTION_KEY", SecretStr(Fernet.generate_key().decode())
    )
    owner, aid = uuid4(), uuid4()
    value = seal(owner, aid, {"Authorization": "dummy-token"})
    assert "dummy-token" not in value
    a = SimpleNamespace(owner_id=owner, id=aid, secret=value)
    assert unseal(a)["Authorization"] == "dummy-token"
    a.owner_id = uuid4()
    with pytest.raises(BadRequestError):
        unseal(a)


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "https://u:p@example.com/mcp",
        "https://example.com?token=x",
        "http://example.com:99999",
        "https://example.com/#secret",
    ],
)
def test_credential_bearing_and_invalid_urls_rejected(url):
    with pytest.raises(BadRequestError):
        validate_url(url)


@pytest.mark.parametrize(
    "ip", ["127.0.0.1", "169.254.169.254", "10.0.0.3", "::1", "fc00::3", "224.0.0.1"]
)
def test_ssrf_private_and_metadata_addresses_rejected(ip):
    async def check():
        with (
            patch.object(
                asyncio.get_running_loop(),
                "getaddrinfo",
                AsyncMock(return_value=[(socket.AF_INET, 0, 0, "", (ip, 80))]),
            ),
            pytest.raises(BadRequestError),
        ):
            await public_address("attacker.invalid", 80)

    asyncio.run(check())


def test_http_transport_pins_dns_preserves_tls_hostname_and_blocks_cross_origin():
    async def check():
        seen = []

        async def handle(self, request):
            seen.append(
                (str(request.url), request.headers["host"], request.extensions["sni_hostname"])
            )
            return httpx.Response(200, stream=httpx.ByteStream(b"ok"))

        with (
            patch("app.services.mcp_connections.public_address", AsyncMock(return_value="1.1.1.1")),
            patch.object(httpx.AsyncHTTPTransport, "handle_async_request", handle),
        ):
            async with httpx.AsyncClient(
                transport=PublicTransport("https://example.com/mcp")
            ) as client:
                response = await client.get("https://example.com/mcp")
                assert response.text == "ok" and str(response.url) == "https://example.com/mcp"
                with pytest.raises(BadRequestError):
                    await client.get("https://other.example/mcp")
        assert seen == [("https://1.1.1.1/mcp", "example.com", "example.com")]

    asyncio.run(check())


def test_official_sdk_initialization_discovery_and_call_over_http():
    async def check():
        seen = []

        async def server(request):
            if request.method != "POST":
                return httpx.Response(405)
            data = json.loads(request.content)
            seen.append(data)
            if "id" not in data:
                return httpx.Response(202)
            method = data["method"]
            result = (
                {
                    "protocolVersion": "2025-11-25",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "test", "version": "1"},
                }
                if method == "initialize"
                else {
                    "tools": [
                        {
                            "name": "lookup",
                            "description": "Read data",
                            "inputSchema": {"type": "object"},
                        }
                    ]
                }
                if method == "tools/list"
                else {"content": [{"type": "text", "text": "actual result"}], "isError": False}
            )
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": data["id"], "result": result})

        asset = SimpleNamespace(
            config={"transport": "streamable-http", "url": "https://mcp.example/mcp"}, secret=None
        )
        with patch(
            "app.services.mcp_connections.PublicTransport",
            side_effect=lambda origin: httpx.MockTransport(server),
        ):
            catalog = await exchange(asset)
            result = await exchange(asset, "call", name="lookup", arguments={"query": "中文"})
        assert catalog["tools"][0]["name"] == "lookup"
        assert result["content"][0]["text"] == "actual result"
        assert next(x for x in seen if x["method"] == "tools/call")["params"]["arguments"] == {
            "query": "中文"
        }
        with pytest.raises(BadRequestError):
            await exchange(
                SimpleNamespace(config={"transport": "stdio", "command": "npx"}, secret=None)
            )

    asyncio.run(check())


def test_headers_cannot_override_routing_or_inject_lines():
    for values in ({"Host": "internal"}, {"Authorization": "hello\r\nHost: internal"}):
        with pytest.raises(BadRequestError):
            validate_secrets("streamable-http", values)


def test_public_skill_metadata_never_exposes_blob_locations_or_secrets():
    from datetime import UTC, datetime

    from app.services.capability_assets import CapabilityService

    owner, aid = uuid4(), uuid4()
    user = SimpleNamespace(id=owner, is_app_admin=False)
    asset = SimpleNamespace(
        id=aid,
        owner_id=owner,
        project_id=None,
        kind="skill",
        scope="personal",
        name="test",
        description="Test",
        tags=[],
        enabled=True,
        revision=3,
        config={
            "entry": ENTRY,
            "files": {
                "SKILL.md": {"storage": "private/blob/location", "size": 20, "sha256": "digest"}
            },
        },
        secret="ciphertext-never-returned",
        catalog={},
        status="published",
        status_message="",
        tested_at=None,
        published_version=1,
        updated_at=None,
        created_at=datetime.now(UTC),
    )
    s = CapabilityService(None, user)
    value = s.public(asset, detail=True)
    assert value["config"]["entry"] == ENTRY
    text = json.dumps(value)
    assert "private/blob/location" not in text and "ciphertext-never-returned" not in text
    assert value["has_credentials"] is True
    assert s.usable(asset)
    asset.scope, asset.project_id = "project", uuid4()
    assert not s.usable(asset)
    with pytest.raises(Exception, match="另一个窗口"):
        s.check_revision(asset, 2)


def test_skill_storage_deduplicates_and_repairs_partial_writes(tmp_path):
    from app.services.skill_storage import SkillStorage

    async def check():
        store = SkillStorage(tmp_path)
        owner = str(uuid4())
        key = await store.save(owner, "untrusted/../filename", ENTRY.encode())
        assert await store.save(owner, "different-name", ENTRY.encode()) == key
        path = store.get_full_path(key)
        path.write_bytes(b"partial")
        assert await store.save(owner, "restore", ENTRY.encode()) == key
        assert await store.load(key) == ENTRY.encode()
        assert len(list((tmp_path / owner).iterdir())) == 1

    asyncio.run(check())


def test_connection_test_records_failure_and_revokes_readiness():
    from app.core.exceptions import ExternalServiceError
    from app.services.mcp_connections import test_connection

    async def check():
        asset = SimpleNamespace(
            kind="mcp",
            revision=4,
            config={"enabled_tools": ["old"], "auto_approved_tools": []},
            status="ready",
        )
        service = SimpleNamespace(
            get=AsyncMock(return_value=asset),
            check_revision=lambda a, v: None,
            audit=AsyncMock(),
            db=SimpleNamespace(flush=AsyncMock(), refresh=AsyncMock()),
            public=lambda a, **kw: {"status": a.status},
        )
        with patch(
            "app.services.mcp_connections.exchange",
            AsyncMock(side_effect=ExternalServiceError(message="连接失败")),
        ):
            result = await test_connection(service, uuid4(), 4)
        assert result["status"] == "unavailable" and asset.revision == 5
        assert asset.tested_at and asset.status_message == "连接失败"

    asyncio.run(check())


def test_skill_runtime_and_mcp_schema_only_load_selected_capabilities():
    from contextlib import asynccontextmanager

    from pydantic_ai import Agent
    from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart
    from pydantic_ai.models.function import FunctionModel

    from app.services.capability_runtime import install

    async def check():
        aid = str(uuid4())

        @asynccontextmanager
        async def db():
            yield None

        asset = SimpleNamespace(name="published skill", description="User summary", kind="skill")
        version = SimpleNamespace(
            manifest={"description": "Published summary"},
            files={"SKILL.md": {}, "references/note.md": {}},
        )
        service = SimpleNamespace(
            version=AsyncMock(return_value=version),
            read_file=AsyncMock(return_value=ENTRY.encode()),
            audit=AsyncMock(),
        )
        seen = []

        def model(messages, info):
            seen.append(str(messages))
            if len(seen) == 1:
                return ModelResponse(
                    parts=[ToolCallPart("read_skill_file", {"skill_id": aid}, "read")]
                )
            return ModelResponse(parts=[TextPart("Read complete")])

        agent = Agent(FunctionModel(model))
        with (
            patch("app.services.capability_runtime.get_worker_db_context", db),
            patch(
                "app.services.capability_runtime.checked", AsyncMock(return_value=(service, asset))
            ),
        ):
            await install(
                agent,
                [{"id": aid, "kind": "skill", "version": 1}],
                user_id=uuid4(),
                project_id=None,
                run_id=uuid4(),
                decisions={},
                emit=AsyncMock(),
            )
            result = await agent.run("Use selected capability")
        assert result.output == "Read complete" and len(seen) == 2
        assert "先检查来源" not in seen[0] and "先检查来源" in seen[1]
        service.read_file.assert_awaited_once_with(asset, "SKILL.md", 1)

    asyncio.run(check())


def test_mcp_schema_runtime_lists_only_enabled_tools_and_rejects_other_ids():
    from contextlib import asynccontextmanager

    from pydantic_ai import Agent
    from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart
    from pydantic_ai.models.function import FunctionModel

    from app.services.capability_runtime import install

    async def check():
        aid = str(uuid4())

        @asynccontextmanager
        async def db():
            yield None

        asset = SimpleNamespace(
            name="MCP",
            description="search",
            kind="mcp",
            config={"enabled_tools": ["allowed"]},
            catalog={
                "tools": [
                    {"name": "allowed", "description": "public", "inputSchema": {"type": "object"}},
                    {"name": "hidden", "description": "private tool"},
                ]
            },
        )
        seen = []

        def model(messages, info):
            seen.append(str(messages))
            if len(seen) == 1:
                return ModelResponse(
                    parts=[ToolCallPart("describe_mcp", {"server_id": aid}, "list")]
                )
            if len(seen) == 2:
                return ModelResponse(
                    parts=[
                        ToolCallPart(
                            "describe_mcp", {"server_id": aid, "tool_name": "allowed"}, "schema"
                        )
                    ]
                )
            return ModelResponse(parts=[TextPart("complete")])

        agent = Agent(FunctionModel(model))
        with (
            patch("app.services.capability_runtime.get_worker_db_context", db),
            patch("app.services.capability_runtime.checked", AsyncMock(return_value=(None, asset))),
        ):
            await install(
                agent,
                [{"id": aid, "kind": "mcp", "revision": 1}],
                user_id=uuid4(),
                project_id=None,
                run_id=uuid4(),
                decisions={},
                emit=AsyncMock(),
            )
            await agent.run("List enabled tools")
        assert "private tool" not in str(seen) and "inputSchema" in seen[-1]

    asyncio.run(check())


def test_official_sdk_sse_with_a_real_isolated_local_server():
    import uvicorn
    from mcp.server.fastmcp import FastMCP

    async def check():
        app = FastMCP("capability-test")

        @app.tool()
        def echo(text: str) -> str:
            return "echo:" + text

        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        server = uvicorn.Server(uvicorn.Config(app.sse_app(), log_level="critical", lifespan="off"))
        task = asyncio.create_task(server.serve(sockets=[sock]))
        try:
            async with asyncio.timeout(5):
                while not server.started:
                    await asyncio.sleep(0.01)
            asset = SimpleNamespace(
                config={"transport": "sse", "url": f"http://127.0.0.1:{port}/sse"}, secret=None
            )
            # Only this test permits the local fixture. Production transport retains DNS pinning.
            with patch(
                "app.services.mcp_connections.PublicTransport",
                side_effect=lambda origin: httpx.AsyncHTTPTransport(),
            ):
                catalog = await exchange(asset)
                result = await exchange(asset, "call", name="echo", arguments={"text": "中文"})
            assert catalog["tools"][0]["name"] == "echo"
            assert result["content"][0]["text"] == "echo:中文"
        finally:
            server.should_exit = True
            await asyncio.wait_for(task, 5)
            sock.close()

    asyncio.run(check())


@pytest.mark.parametrize(
    "schema",
    [
        {"$dynamicRef": "http://169.254.169.254/latest/meta-data/"},
        {"properties": {"value": {"$ref": "https://attacker.invalid"}}},
        {"pattern": "(a+)+$"},
        {"patternProperties": {"(a+)+$": {}}},
    ],
)
def test_untrusted_schemas_cannot_fetch_urls_or_execute_pathological_regexes(schema):
    from app.services.capability_runtime import validate_arguments

    with pytest.raises(BadRequestError):
        validate_arguments(schema, {"value": "a" * 5000 + "!"})


def test_schema_checks_types_required_fields_and_complexity():
    from app.services.capability_runtime import validate_arguments

    schema = {
        "type": "object",
        "properties": {"id": {"type": "integer"}},
        "required": ["id"],
        "additionalProperties": False,
    }
    validate_arguments(schema, {"id": 17})
    for args in ({}, {"id": "seventeen"}, {"id": 17, "extra": "bad"}):
        with pytest.raises(BadRequestError):
            validate_arguments(schema, args)
    nested = {}
    for _ in range(22):
        nested = {"properties": {"x": nested}}
    with pytest.raises(BadRequestError):
        validate_arguments(nested, {})


def test_api_request_limit_precedes_parsing_even_without_content_length():
    from fastapi import APIRouter, FastAPI

    from app.api.routes.v1.capabilities import BoundedCapabilityRoute

    async def check():
        app = FastAPI()
        router = APIRouter(route_class=BoundedCapabilityRoute)
        seen = []

        @router.post("/capabilities/mcp")
        async def endpoint(data: dict):
            seen.append(data)
            return data

        app.include_router(router)

        async def oversized():
            yield b'{"large":"'
            yield b"x" * 400001
            yield b'"}'

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            result = await client.post(
                "/capabilities/mcp",
                content=oversized(),
                headers={"Content-Type": "application/json"},
            )
            assert result.status_code == 413 and not seen
            result = await client.post("/capabilities/mcp", json={"ok": True})
            assert result.status_code == 200 and seen == [{"ok": True}]

    asyncio.run(check())


def test_compressed_responses_cannot_bypass_mcp_body_limit():
    async def check():
        async def handle(self, request):
            assert request.headers["accept-encoding"] == "identity"
            return httpx.Response(
                200, headers={"content-encoding": "gzip"}, stream=httpx.ByteStream(b"encoded")
            )

        with (
            patch("app.services.mcp_connections.public_address", AsyncMock(return_value="1.1.1.1")),
            patch.object(httpx.AsyncHTTPTransport, "handle_async_request", handle),
        ):
            async with httpx.AsyncClient(
                transport=PublicTransport("https://example.com/mcp")
            ) as client:
                with pytest.raises(BadRequestError):
                    await client.get("https://example.com/mcp")

    asyncio.run(check())
