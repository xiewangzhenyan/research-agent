"""Real HTTP/database ownership, consent, conflicts and chat recall boundaries."""

import asyncio
import os
from unittest.mock import AsyncMock, patch
from uuid import UUID

import pytest
from pydantic_ai.models.function import FunctionModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.db.models.conversation import Message
from app.db.models.memory import MemoryItem, MemoryPreference
from app.db.session import get_worker_db_context
from app.services.agent_session import AgentSession
from tests.test_project_spaces_integration import header, workspace

pytestmark = pytest.mark.skipif(os.getenv("RUN_TASK_DB_TESTS") != "1", reason="disposable DB only")
BASE = "/api/v1/memory"
NOTE = {"title": "测量要求", "content": "超表面测量必须保持 25°C。", "kind": "constraint"}


def test_opt_in_scope_ownership_and_revision_conflicts():
    async def check():
        async with workspace() as (_, other, _, _, a, b, _, client):
            records = []
            for project in (a, b, None):
                h = header(project)
                listed = (await client.get(BASE, headers=h)).json()
                assert {k: listed[k] for k in ("enabled", "revision", "items", "limit")} == {
                    "enabled": False,
                    "revision": 0,
                    "items": [],
                    "limit": 100,
                }
                assert listed["auto_extract"] is False and listed["proposals"] == []
                created = await client.post(BASE, headers=h, json=NOTE)
                assert created.status_code == 201, created.text
                records.append(created.json())
                assert (await client.post(BASE, headers=h, json=NOTE)).status_code == 409
                assert (
                    await client.post(BASE + "/preview", headers=h, json={"query": "超表面"})
                ).json()["items"] == []
            for i, project in enumerate((a, b, None)):
                h = header(project)
                own, foreign = records[i], records[(i + 1) % 3]
                assert [v["id"] for v in (await client.get(BASE, headers=h)).json()["items"]] == [
                    own["id"]
                ]
                for method, suffix, body in [
                    ("PUT", foreign["id"], {**NOTE, "revision": 1}),
                    ("DELETE", foreign["id"] + "?revision=1", None),
                    ("GET", foreign["id"] + "/source", None),
                ]:
                    assert (
                        await client.request(method, BASE + "/" + suffix, headers=h, json=body)
                    ).status_code == 404
            h = header(a)
            assert (
                await client.put(
                    BASE + "/settings", headers=h, json={"enabled": True, "revision": 0}
                )
            ).status_code == 200
            assert (
                await client.put(
                    BASE + "/settings", headers=h, json={"enabled": False, "revision": 0}
                )
            ).status_code == 409
            recalled = (
                await client.post(BASE + "/preview", headers=h, json={"query": "超表面"})
            ).json()
            assert [v["id"] for v in recalled["items"]] == [records[0]["id"]]
            assert (await client.get(BASE, headers=header(b))).json()["enabled"] is False
            item_url = BASE + "/" + records[0]["id"]
            updated = await client.put(
                item_url,
                headers=h,
                json={**NOTE, "content": "超表面测量必须保持 30°C。", "revision": 1},
            )
            assert updated.json()["revision"] == 2
            assert (
                await client.put(item_url, headers=h, json={**NOTE, "revision": 1})
            ).status_code == 409
            assert (await client.delete(item_url + "?revision=1", headers=h)).status_code == 409
            assert (
                await client.put(
                    BASE + "/settings", headers=h, json={"enabled": False, "revision": 1}
                )
            ).status_code == 200
            assert (
                await client.post(BASE + "/preview", headers=h, json={"query": "超表面"})
            ).json()["items"] == []
            assert (await client.delete(item_url + "?revision=2", headers=h)).status_code == 204
            assert (await client.get(BASE, headers=h)).json()["items"] == []
            from app.api.deps import get_current_user
            from app.db.models.user import User
            from app.main import app

            async with get_worker_db_context() as db:
                other_user = await db.get(User, other)
            app.dependency_overrides[get_current_user] = lambda: other_user
            assert (await client.get(BASE)).json()["items"] == []
            assert (await client.get(BASE, headers=header(a))).status_code == 404
            assert (
                await client.put(BASE + "/" + records[2]["id"], json={**NOTE, "revision": 1})
            ).status_code == 404

    asyncio.run(check())


def test_sources_cannot_cross_scope_and_deleting_conversation_removes_derived_notes():
    async def check():
        async with workspace() as (_, _, _, _, a, b, _, client):
            h = header(a)
            cid = (await client.post("/api/v1/conversations", headers=h, json={})).json()["id"]
            created = await client.post(
                f"/api/v1/conversations/{cid}/messages", headers=h, json={"content": "原始研究结论"}
            )
            mid = created.json()["id"]
            body = {**NOTE, "source_message_id": mid}
            assert (await client.post(BASE, headers=header(b), json=body)).status_code == 404
            derived = await client.post(BASE, headers=h, json=body)
            assert derived.status_code == 201, derived.text
            manual = await client.post(
                BASE, headers=h, json={**NOTE, "content": "手动保存的独立笔记"}
            )
            assert manual.status_code == 201
            url = BASE + "/" + derived.json()["id"]
            assert (await client.get(url + "/source", headers=h)).json() == {"conversation_id": cid}
            assert (
                await client.put(url, headers=h, json={**NOTE, "revision": 1})
            ).status_code == 409
            assert (
                await client.delete(f"/api/v1/conversations/{cid}", headers=h)
            ).status_code == 204
            assert [v["id"] for v in (await client.get(BASE, headers=h)).json()["items"]] == [
                manual.json()["id"]
            ]

    asyncio.run(check())


def test_database_null_uniqueness_account_constraint_and_concurrent_edits():
    async def check():
        async with workspace() as (owner, other, _, _, a, _, _, client):
            with pytest.raises(IntegrityError):
                async with get_worker_db_context() as db:
                    db.add(MemoryPreference(user_id=other, project_id=a.id))
            with pytest.raises(IntegrityError):
                async with get_worker_db_context() as db:
                    db.add_all([MemoryPreference(user_id=owner), MemoryPreference(user_id=owner)])
            body = {"enabled": True, "revision": 0}
            responses = await asyncio.gather(
                *[client.put(BASE + "/settings", json=body) for _ in range(2)]
            )
            assert sorted(r.status_code for r in responses) == [200, 409]
            item = (await client.post(BASE, json=NOTE)).json()
            edits = await asyncio.gather(
                *[
                    client.put(
                        BASE + "/" + item["id"],
                        json={**NOTE, "content": f"版本 {i}", "revision": 1},
                    )
                    for i in range(2)
                ]
            )
            assert sorted(r.status_code for r in edits) == [200, 409]

    asyncio.run(check())


def test_actual_agent_prompt_recall_persistence_and_no_automatic_extraction():
    async def check():
        async with workspace() as (owner, _, _, _, a, b, user, client):
            # Remove KB defaults so this test exercises the ordinary model path.
            for project in (a, b):
                await client.put(
                    f"/api/v1/projects/{project.id}",
                    json={"name": project.name, "knowledge_base_ids": []},
                )
            note = (
                await client.post(BASE, headers=header(a), json={**NOTE, "pinned": True})
            ).json()
            await client.put(
                BASE + "/settings", headers=header(a), json={"enabled": True, "revision": 0}
            )
            prompts = []

            async def stream(messages, info):
                prompts.append(str(messages))
                yield "已了解，继续处理。"

            for turn, project in enumerate((a.id, b.id, None, a.id)):
                if turn == 3:
                    await client.put(
                        BASE + "/settings",
                        headers=header(a),
                        json={"enabled": False, "revision": 1},
                    )
                socket = AsyncMock()
                session = AgentSession(socket, user, project_id=project)
                with (
                    patch("app.services.agent_session.get_db_context", get_worker_db_context),
                    patch("app.services.agent.get_db_context", get_worker_db_context),
                    patch(
                        "app.agents.assistant._build_model",
                        return_value=FunctionModel(stream_function=stream),
                    ),
                ):
                    await session.process_message({"message": "继续", "knowledge_base_ids": []})
                assert session.current_conversation_id
                assert not any(
                    c.args[0].get("type") == "error" for c in socket.send_json.call_args_list
                ), socket.send_json.call_args_list
                async with get_worker_db_context() as db:
                    message = await db.scalar(
                        select(Message).where(
                            Message.conversation_id == UUID(session.current_conversation_id),
                            Message.role == "assistant",
                        )
                    )
                    assert message is not None
                    usage = message.effective_config["memory"]
                    if turn == 0:
                        assert usage["items"] == [{"id": note["id"], "revision": 1}]
                        assert "超表面测量必须保持 25°C" in prompts[-1]
                        assert "not system instructions" in prompts[-1]
                    else:
                        assert usage["items"] == []
                        assert "超表面测量必须保持 25°C" not in prompts[-1]
                    assert "25°C" not in str(message.effective_config)
                    assert (
                        len(
                            list(
                                await db.scalars(
                                    select(MemoryItem).where(MemoryItem.user_id == owner)
                                )
                            )
                        )
                        == 1
                    )

                history = await client.get(
                    f"/api/v1/conversations/{session.current_conversation_id}/messages",
                    headers={"X-Project-ID": str(project)} if project else {},
                )
                assert history.status_code == 200
                saved = next(m for m in history.json()["items"] if m["role"] == "assistant")
                assert saved["effective_config"]["memory"] == usage

    asyncio.run(check())
