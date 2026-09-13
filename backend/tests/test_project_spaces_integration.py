"""Real database and HTTP project boundaries; opt in only on disposable databases."""

import asyncio
import os
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import IntegrityError

from app.api.deps import get_current_user
from app.core.exceptions import NotFoundError
from app.db.models.agent_run import AgentRun
from app.db.models.conversation import Conversation
from app.db.models.knowledge import KnowledgeBase
from app.db.models.user import User
from app.db.session import get_db_session, get_worker_db_context
from app.main import app
from app.schemas.conversation import ConversationCreate
from app.schemas.project import ProjectWrite
from app.services.agent_session import AgentSession
from app.services.conversation import ConversationService
from app.services.project import ProjectService
from app.services.run_artifact import RunArtifactService
from app.services.sandbox_files import validate_artifacts
from tests.test_agent_runs_integration import users
from tests.test_sandbox_files import artifact

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_TASK_DB_TESTS") != "1", reason="requires disposable database"
)


@asynccontextmanager
async def workspace():
    async with users() as (owner, other):
        async with get_worker_db_context() as db:
            user = await db.get(User, owner)
            kb = KnowledgeBase(user_id=owner, name="Account library")
            foreign = KnowledgeBase(user_id=other, name="Private library")
            db.add_all([kb, foreign])
            await db.flush()
            projects = ProjectService(db, owner)
            a = await projects.save(ProjectWrite(name="A", knowledge_base_ids=[kb.id]))
            b = await projects.save(ProjectWrite(name="B", knowledge_base_ids=[kb.id]))
        previous = app.dependency_overrides.copy()

        async def session():
            async with get_worker_db_context() as db:
                yield db

        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_db_session] = session
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                yield owner, other, kb, foreign, a, b, user, client
        finally:
            app.dependency_overrides.clear()
            app.dependency_overrides.update(previous)


def header(project):
    return {"X-Project-ID": str(project.id)} if project else {}


def test_account_libraries_reusable_project_defaults_are_snapshots():
    async def check():
        async with workspace() as (owner, other, kb, foreign, a, b, user, client):
            conversations = []
            for project in (a, b, None):
                response = await client.post(
                    "/api/v1/conversations", headers=header(project), json={}
                )
                assert response.status_code == 201, response.text
                conv = response.json()
                assert conv["project_id"] == (str(project.id) if project else None)
                assert conv["active_knowledge_base_ids"] == ([str(kb.id)] if project else [])
                conversations.append(conv)
                # Account-wide knowledge listing ignores the current workspace.
                bases = await client.get("/api/v1/knowledge/bases", headers=header(project))
                assert {v["id"] for v in bases.json()["items"]} == {str(kb.id)}
            changed = await client.put(
                f"/api/v1/projects/{a.id}", json={"name": "A revised", "knowledge_base_ids": []}
            )
            assert changed.status_code == 200
            old = await client.get(
                f"/api/v1/conversations/{conversations[0]['id']}", headers=header(a)
            )
            assert old.json()["active_knowledge_base_ids"] == [str(kb.id)]
            new = await client.post("/api/v1/conversations", headers=header(a), json={})
            assert new.json()["active_knowledge_base_ids"] == []
            denied = await client.post(
                "/api/v1/projects",
                json={"name": "Forbidden", "knowledge_base_ids": [str(foreign.id)]},
            )
            assert denied.status_code == 404
            async with get_worker_db_context() as db:
                assert (await db.get(KnowledgeBase, kb.id)).user_id == owner
                with pytest.raises(NotFoundError):
                    await ProjectService(db, other).get(a.id)

    asyncio.run(check())


def test_conversation_lists_details_mutations_and_shares_cannot_cross_projects():
    async def check():
        async with workspace() as (owner, other, kb, foreign, a, b, user, client):
            ids = []
            for project in (None, a, b):
                created = await client.post(
                    "/api/v1/conversations", headers=header(project), json={"title": "Private"}
                )
                cid = created.json()["id"]
                ids.append(cid)
                await client.post(
                    f"/api/v1/conversations/{cid}/messages",
                    headers=header(project),
                    json={"content": "Private task details"},
                )
            for i, project in enumerate((None, a, b)):
                listed = await client.get("/api/v1/conversations", headers=header(project))
                assert listed.json()["total"] == 1
                assert [v["id"] for v in listed.json()["items"]] == [ids[i]]
                target = ids[(i + 1) % 3]
                for method, suffix, body in [
                    ("GET", "", None),
                    ("GET", "/messages", None),
                    ("PATCH", "", {"title": "Intrusion"}),
                    ("DELETE", "", None),
                    ("POST", "/messages", {"content": "Intrusion"}),
                    ("POST", "/archive", None),
                    ("GET", "/shares", None),
                    ("POST", "/shares", {"generate_link": True}),
                    ("DELETE", f"/messages/{uuid4()}/rate", None),
                ]:
                    response = await client.request(
                        method,
                        f"/api/v1/conversations/{target}{suffix}",
                        headers=header(project),
                        json=body,
                    )
                    assert response.status_code == 404, (method, suffix, response.text)
                    assert "Private task details" not in response.text
            assert (
                await client.get("/api/v1/conversations", headers={"X-Project-ID": str(uuid4())})
            ).status_code == 404
            app.dependency_overrides[get_current_user] = lambda: User(id=other, is_active=True)
            assert (await client.get("/api/v1/conversations", headers=header(a))).status_code == 404
            assert (
                await client.put(f"/api/v1/projects/{a.id}", json={"name": "Intrusion"})
            ).status_code == 404
            assert (await client.get("/api/v1/projects")).json() == []

    asyncio.run(check())


def test_tasks_scope_idempotency_events_artifacts_and_explicit_empty_defaults():
    async def check():
        async with workspace() as (owner, other, kb, foreign, a, b, user, client):
            key = str(uuid4())
            payload = {"idempotency_key": key, "prompt": "Prepare a summary", "tools": []}
            created = await client.post("/api/v1/runs", headers=header(a), json=payload)
            assert created.status_code == 201, created.text
            run = created.json()
            assert run["project_id"] == str(a.id)
            assert run["request"]["knowledge_base_ids"] == [str(kb.id)]
            await client.put(f"/api/v1/projects/{a.id}", json={"name": "A changed"})
            retry = await client.post("/api/v1/runs", headers=header(a), json=payload)
            assert retry.json()["id"] == run["id"]
            assert retry.json()["request"]["knowledge_base_ids"] == [str(kb.id)]
            assert (
                await client.post("/api/v1/runs", headers=header(b), json=payload)
            ).status_code == 409
            async with get_worker_db_context() as db:
                current = await db.get(AgentRun, UUID(run["id"]))
                current.status, current.attempt = "running", 1
            async with get_worker_db_context() as db:
                files = await RunArtifactService(db, owner, project_id=a.id).save(
                    UUID(run["id"]), 1, uuid4(), validate_artifacts([artifact()], "completed")
                )
            fid = files[0]["id"]
            for project in (None, b):
                assert (await client.get("/api/v1/runs", headers=header(project))).json() == []
                for method, suffix, body in [
                    ("GET", "", None),
                    ("GET", "/events", None),
                    ("POST", "/cancel", None),
                    ("POST", "/resume", {"question_id": "q", "answers": {"q": ["answer"]}}),
                    ("GET", "/artifacts", None),
                    ("GET", f"/artifacts/{fid}", None),
                    ("DELETE", f"/artifacts/{fid}", None),
                ]:
                    response = await client.request(
                        method,
                        f"/api/v1/runs/{run['id']}{suffix}",
                        headers=header(project),
                        json=body,
                    )
                    assert response.status_code == 404, (suffix, response.text)
            download = await client.get(
                f"/api/v1/runs/{run['id']}/artifacts/{fid}", headers=header(a)
            )
            assert download.status_code == 200 and download.content == b"a,b\n1,2"
            empty = await client.post(
                "/api/v1/runs",
                headers=header(b),
                json={**payload, "idempotency_key": str(uuid4()), "knowledge_base_ids": []},
            )
            assert empty.status_code == 201
            assert empty.json()["request"]["knowledge_base_ids"] == []

    asyncio.run(check())


def test_websocket_rejects_other_project_before_history_or_persistence():
    async def check():
        async with workspace() as (owner, other, kb, foreign, a, b, user, client):
            async with get_worker_db_context() as db:
                conversation = await ConversationService(db, project_id=a.id).create_conversation(
                    ConversationCreate(user_id=owner)
                )
            for project in (None, b.id):
                session = AgentSession(AsyncMock(), user, project_id=project)
                with (
                    patch("app.services.agent_session.get_db_context", get_worker_db_context),
                    patch(
                        "app.services.agent_session.persist_user_turn", new_callable=AsyncMock
                    ) as persist,
                ):
                    with pytest.raises(NotFoundError):
                        await session.process_message(
                            {"message": "Continue", "conversation_id": str(conversation.id)}
                        )
                    persist.assert_not_awaited()
                    assert session.conversation_history == []

    asyncio.run(check())


def test_database_owner_constraint_and_deleted_library_defaults():
    async def check():
        async with workspace() as (owner, other, kb, foreign, a, b, user, client):
            with pytest.raises(IntegrityError):
                async with get_worker_db_context() as db:
                    db.add(Conversation(user_id=other, project_id=a.id))
            async with get_worker_db_context() as db:
                await db.delete(await db.get(KnowledgeBase, kb.id))
            async with get_worker_db_context() as db:
                assert await ProjectService(db, owner).defaults(a.id) == []
                assert await ProjectService(db, owner).defaults(b.id) == []
                assert all(not p.knowledge_base_ids for p in await ProjectService(db, owner).list())
                # Default namespace remains writable by clients that omit project_id.
                legacy = Conversation(user_id=owner)
                db.add(legacy)
                await db.flush()
                rows, count = await ConversationService(db).list_conversations(owner)
                assert count == 1 and rows[0].id == legacy.id

    asyncio.run(check())


def test_websocket_turn_persistence_keeps_project_and_default_knowledge():
    from app.services import agent

    async def check():
        async with workspace() as (owner, other, kb, foreign, a, b, user, client):
            with patch.object(agent, "get_db_context", get_worker_db_context):
                cid, created, _ = await agent.persist_user_turn(
                    user, "Project question", [], None, None, project_id=a.id
                )
                assert created and cid
                mid = await agent.persist_assistant_turn(
                    cid, "Project answer", "test", [], user_id=owner, project_id=a.id
                )
                assert mid
                rejected = await agent.persist_assistant_turn(
                    cid, "Wrong project answer", "test", [], user_id=owner, project_id=b.id
                )
                assert rejected is None
            async with get_worker_db_context() as db:
                conversation = await ConversationService(db, project_id=a.id).get_conversation(
                    UUID(cid), user_id=owner, include_messages=True
                )
                assert conversation.active_knowledge_base_ids == [str(kb.id)]
                assert [m.content for m in conversation.messages] == [
                    "Project question",
                    "Project answer",
                ]

    asyncio.run(check())
