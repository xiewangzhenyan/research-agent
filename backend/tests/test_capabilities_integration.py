"""Real PostgreSQL CRUD, tenant isolation, immutable skills and durable MCP consent."""

import asyncio
import json
import os
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch
from uuid import UUID

import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr
from pydantic_ai.models.function import DeltaToolCall, FunctionModel
from sqlalchemy import select

from app.core.config import settings
from app.core.exceptions import (
    AlreadyExistsError,
    AuthorizationError,
    BadRequestError,
    NotFoundError,
)
from app.db.models.capability import CapabilityAudit
from app.db.models.user import User
from app.db.session import get_worker_db_context
from app.schemas.capability import AssetWrite, BindingsWrite, SkillFileWrite, ToggleAction
from app.schemas.project import ProjectWrite
from app.services.capability_assets import CapabilityService
from app.services.capability_runtime import ALLOW, DENY, checked, snapshot
from app.services.mcp_connections import test_connection as discover
from app.services.project import ProjectService
from app.worker.agent_runs import try_run
from tests.test_agent_runs_integration import get, users
from tests.test_capability_security import ENTRY
from tests.test_clarification_integration import answer
from tests.test_durable_chat import state, submit

pytestmark = pytest.mark.skipif(os.getenv("RUN_TASK_DB_TESTS") != "1", reason="disposable DB only")
CATALOG = {
    "tools": [
        {
            "name": "lookup",
            "description": "Get a record",
            "inputSchema": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
                "additionalProperties": False,
            },
        }
    ],
    "resources": [],
    "prompts": [],
}


@asynccontextmanager
async def service(uid, project=None):
    async with get_worker_db_context() as db:
        yield CapabilityService(db, await db.get(User, uid), project)


async def binding(s, ids):
    return await s.bind(BindingsWrite(asset_ids=ids, revision=(await s.bindings())["revision"]))


async def create_mcp(uid, auto=False):
    async with service(uid) as s:
        value = await s.save(
            "mcp",
            AssetWrite(name="Test MCP", enabled=True, config={"url": "https://test.invalid/mcp"}),
        )
    aid = UUID(value["id"])
    with patch("app.services.mcp_connections.exchange", AsyncMock(return_value=CATALOG)):
        async with service(uid) as s:
            value = await discover(s, aid, value["revision"])
    async with service(uid) as s:
        value = await s.save(
            "mcp",
            AssetWrite(
                name=value["name"],
                enabled=True,
                revision=value["revision"],
                config={
                    **value["config"],
                    "enabled_tools": ["lookup"],
                    "auto_approved_tools": ["lookup"] if auto else [],
                },
            ),
            aid,
        )
        await binding(s, [aid])
    return value


def test_skill_crud_versions_scopes_and_revision_conflicts(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "MEDIA_DIR", str(tmp_path))

    async def check():
        async with users() as (a, b):
            async with get_worker_db_context() as db:
                project = await ProjectService(db, a).save(ProjectWrite(name="Alpha"))
                other = await ProjectService(db, a).save(ProjectWrite(name="Beta"))
            async with service(a, project.id) as s:
                value = await s.save(
                    "skill",
                    AssetWrite(
                        name="Review", scope="project", enabled=True, config={"entry": ENTRY}
                    ),
                )
                aid = UUID(value["id"])
                value = await s.publish(aid, value["revision"])
                await binding(s, [aid])
                pinned = await snapshot(s)
                assert pinned[0]["version"] == 1
            async with service(b) as s:
                assert not await s.list("skill")
                with pytest.raises(NotFoundError):
                    await s.get(aid)
            async with service(a, other.id) as s:
                with pytest.raises(AuthorizationError):
                    await binding(s, [aid])
            async with service(a, project.id) as s:
                original = value["revision"]
                value = await s.write_file(
                    aid,
                    SkillFileWrite(
                        revision=original, path="references/notes.md", content="重要约束：保留来源"
                    ),
                )
                value = await s.write_file(
                    aid,
                    SkillFileWrite(
                        revision=value["revision"], path="SKILL.md", content=ENTRY + "新流程"
                    ),
                )
                with pytest.raises(AlreadyExistsError):
                    await s.publish(aid, original)
                asset = await s.get(aid)
                assert (await s.read_file(asset, "SKILL.md", 1)).decode() == ENTRY
                assert (await s.read_file(asset, "SKILL.md")).decode().endswith("新流程")
                value = await s.publish(aid, value["revision"])
                assert len(await s.versions(aid)) == 2
                value = await s.restore(aid, value["revision"], 1)
                assert value["config"]["entry"] == ENTRY and value["published_version"] == 2
                assert [f["path"] for f in value["config"]["files"]] == ["SKILL.md"]
                await s.toggle(aid, ToggleAction(revision=value["revision"], enabled=False))
            async with get_worker_db_context() as db:
                with pytest.raises(AuthorizationError):
                    await checked(db, a, project.id, pinned[0])
            async with service(a, project.id) as s:
                asset = await s.get(aid)
                await s.remove(aid, asset.revision)
                assert (await s.bindings())["asset_ids"] == []
                assert any(
                    x.action == "deleted" and x.asset_id is None
                    for x in await s.db.scalars(
                        select(CapabilityAudit).where(CapabilityAudit.user_id == a)
                    )
                )

    asyncio.run(check())


def test_personal_sharing_system_admin_and_secret_replacement(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "MEDIA_DIR", str(tmp_path))
    monkeypatch.setattr(
        settings, "CAPABILITY_ENCRYPTION_KEY", SecretStr(Fernet.generate_key().decode())
    )

    async def check():
        async with users() as (a, b):
            async with service(a) as s:
                with pytest.raises(AuthorizationError):
                    await s.save(
                        "skill", AssetWrite(name="System", scope="system", config={"entry": ENTRY})
                    )
                value = await s.save(
                    "skill", AssetWrite(name="Personal", enabled=True, config={"entry": ENTRY})
                )
                value = await s.publish(UUID(value["id"]), value["revision"])
                project = await ProjectService(s.db, a).save(
                    ProjectWrite(name="Shared within account")
                )
            async with service(a, project.id) as s:
                await binding(s, [value["id"]])
                assert len(await snapshot(s)) == 1
            async with service(a) as s:
                assert (await s.bindings())["asset_ids"] == []
                s.user.is_app_admin = True
                value = await s.save(
                    "mcp",
                    AssetWrite(
                        name="Shared MCP",
                        scope="system",
                        config={"url": "https://test.invalid/mcp"},
                        secrets={"Authorization": "dummy-sensitive-header"},
                    ),
                )
                assert value["has_credentials"] and "dummy-sensitive-header" not in json.dumps(
                    value
                )
                asset = await s.get(UUID(value["id"]))
                assert asset.secret and "dummy-sensitive-header" not in asset.secret
            async with service(b) as s:
                found = (await s.list("mcp"))[0]
                assert not found["can_edit"] and found["has_credentials"]
                with pytest.raises(NotFoundError):
                    await s.remove(UUID(value["id"]), value["revision"])
            async with service(a) as s:
                value = await s.save(
                    "mcp",
                    AssetWrite(
                        name=value["name"],
                        scope="system",
                        revision=value["revision"],
                        config=value["config"],
                        secrets={},
                    ),
                    UUID(value["id"]),
                )
                assert not value["has_credentials"]

    asyncio.run(check())


@pytest.mark.parametrize("decision", [ALLOW, DENY, "revoke", "change"])
def test_mcp_requires_exact_durable_consent_and_rechecks_policy(decision):
    async def check():
        async with users() as (a, b):
            value = await create_mcp(a)
            args = {
                "server_id": value["id"],
                "tool_name": "lookup",
                "arguments": {"query": "record-17"},
            }

            async def stream(messages, info):
                results = [
                    p.content
                    for m in messages
                    for p in m.parts
                    if getattr(p, "tool_name", None) == "call_mcp_tool"
                    and p.part_kind == "tool-return"
                ]
                if any(
                    isinstance(r, dict) and (r.get("content") or r.get("denied")) for r in results
                ):
                    yield "已按授权处理。"
                else:
                    yield {
                        0: DeltaToolCall(
                            name="call_mcp_tool",
                            json_args=json.dumps(args),
                            tool_call_id="mcp_call",
                        )
                    }

            remote = AsyncMock(
                return_value={
                    "content": [{"type": "text", "text": "record value"}],
                    "isError": False,
                }
            )
            with (
                patch(
                    "app.agents.assistant._build_model",
                    return_value=FunctionModel(stream_function=stream),
                ),
                patch("app.services.capability_runtime.exchange", remote),
            ):
                turn = await submit(a, message="使用连接查询 record-17")
                await try_run(turn.id)
                waiting = await get(a, turn.id)
                assert waiting.status == "waiting_input", waiting.error
                q = waiting.pending_input["calls"][0]["questions"][0]
                assert q["options"] == [DENY, ALLOW] and "record-17" in q["details"]
                assert not remote.called
                with pytest.raises(NotFoundError):
                    await answer(b, waiting, ALLOW)
                with pytest.raises(BadRequestError):
                    await answer(a, waiting, "yes")
                if decision in ("revoke", "change"):
                    async with service(a) as s:
                        if decision == "revoke":
                            await binding(s, [])
                        else:
                            await s.toggle(
                                UUID(value["id"]),
                                ToggleAction(revision=value["revision"], enabled=False),
                            )
                await answer(a, waiting, decision if decision in (ALLOW, DENY) else ALLOW)
                await try_run(turn.id)
                saved = await get(a, turn.id)
                if decision in (ALLOW, DENY):
                    assert saved.status == "completed", saved.error
                    assert remote.await_count == (1 if decision == ALLOW else 0)
                    assert (await state(a, turn.conversation_id))["messages"][-1].content
                else:
                    assert saved.status == "failed" and not remote.called

    asyncio.run(check())


def test_auto_approved_mcp_is_deduplicated_within_a_run():
    async def check():
        async with users() as (a, _):
            value = await create_mcp(a, auto=True)
            args = {"server_id": value["id"], "tool_name": "lookup", "arguments": {"query": "one"}}

            async def stream(messages, info):
                results = [
                    p
                    for m in messages
                    for p in m.parts
                    if getattr(p, "tool_name", None) == "call_mcp_tool"
                    and p.part_kind == "tool-return"
                ]
                if len(results) >= 2:
                    yield "只调用了一次远程服务。"
                else:
                    yield {
                        0: DeltaToolCall(
                            name="call_mcp_tool",
                            json_args=json.dumps(args),
                            tool_call_id=f"call{len(results)}",
                        )
                    }

            remote = AsyncMock(return_value={"content": [{"type": "text", "text": "one"}]})
            with (
                patch(
                    "app.agents.assistant._build_model",
                    return_value=FunctionModel(stream_function=stream),
                ),
                patch("app.services.capability_runtime.exchange", remote),
            ):
                turn = await submit(a, message="用工具查询")
                await try_run(turn.id)
                saved = await get(a, turn.id)
                assert saved.status == "completed", saved.error
                assert remote.await_count == 1

    asyncio.run(check())


def test_skill_loads_only_published_selected_files(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "MEDIA_DIR", str(tmp_path))

    async def check():
        async with users() as (a, _):
            async with service(a) as s:
                skill = await s.save(
                    "skill", AssetWrite(name="Review", enabled=True, config={"entry": ENTRY})
                )
                skill = await s.publish(UUID(skill["id"]), skill["revision"])
                await binding(s, [skill["id"]])
            seen = []

            async def stream(messages, info):
                seen.append(str(messages))
                if any(
                    getattr(p, "tool_name", None) == "read_skill_file"
                    and p.part_kind == "tool-return"
                    for m in messages
                    for p in m.parts
                ):
                    yield "已读取发布版本。"
                else:
                    yield {
                        0: DeltaToolCall(
                            name="read_skill_file",
                            json_args=json.dumps({"skill_id": skill["id"]}),
                            tool_call_id="skill",
                        )
                    }

            with patch(
                "app.agents.assistant._build_model",
                return_value=FunctionModel(stream_function=stream),
            ):
                turn = await submit(a, message="按技能流程整理资料")
                await try_run(turn.id)
            saved = await get(a, turn.id)
            assert saved.status == "completed", saved.error
            assert "先检查来源，再给出结论" not in seen[0]
            assert "先检查来源，再给出结论" in seen[1]

    asyncio.run(check())


def test_unsharing_a_system_skill_revokes_runtime_without_blocking_new_chat(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "MEDIA_DIR", str(tmp_path))

    async def check():
        async with users() as (a, b):
            async with service(a) as s:
                s.user.is_app_admin = True
                value = await s.save(
                    "skill",
                    AssetWrite(
                        name="Shared", scope="system", enabled=True, config={"entry": ENTRY}
                    ),
                )
                value = await s.publish(UUID(value["id"]), value["revision"])
            async with service(b) as s:
                await binding(s, [value["id"]])
                pinned = await snapshot(s)
                assert len(pinned) == 1
            async with service(a) as s:
                await s.save(
                    "skill",
                    AssetWrite(
                        name="Private",
                        scope="personal",
                        enabled=True,
                        revision=value["revision"],
                        config={"entry": ENTRY},
                    ),
                    UUID(value["id"]),
                )
            async with service(b) as s:
                assert (await s.bindings())["asset_ids"] == []
                assert await snapshot(s) == []
                with pytest.raises(NotFoundError):
                    await checked(s.db, b, None, pinned[0])
            turn = await submit(b, message="普通问答仍可提交")
            assert turn.request["capabilities"] == []

    asyncio.run(check())
