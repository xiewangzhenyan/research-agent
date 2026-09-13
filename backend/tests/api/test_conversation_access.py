"""Exercise HTTP authorization with real services and isolated repository doubles."""

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.deps import (
    get_conversation_service,
    get_conversation_share_service,
    get_current_user,
)
from app.api.project_deps import scoped_conversation_service
from app.core.exceptions import NotFoundError
from app.db.models.conversation import Conversation, Message
from app.db.models.conversation_share import ConversationShare
from app.db.models.user import User, UserRole
from app.main import app
from app.repositories import conversation_repo, conversation_share_repo, message_rating_repo
from app.schemas.conversation import MessageCreate
from app.services import agent as agent_service
from app.services.conversation import ConversationService
from app.services.conversation_share import ConversationShareService

pytestmark = pytest.mark.anyio


@pytest.fixture
async def access(monkeypatch):
    now = datetime.now(UTC)
    owner = User(id=uuid4(), email="owner@example.invalid", role=UserRole.USER, is_active=True)
    other = User(id=uuid4(), email="other@example.invalid", role=UserRole.USER, is_active=True)
    admin = User(id=uuid4(), email="admin@example.invalid", role=UserRole.ADMIN, is_active=True)
    conversation = Conversation(
        id=uuid4(),
        user_id=owner.id,
        title="Private research notes",
        is_archived=False,
        is_demo=False,
        active_knowledge_base_ids=[],
        active_knowledge_document_ids=None,
        knowledge_strict=True,
        created_at=now,
        updated_at=now,
        messages=[],
    )
    message = Message(
        id=uuid4(),
        conversation_id=conversation.id,
        role="assistant",
        content="Account A private research result",
        created_at=now,
        updated_at=now,
        tool_calls=[],
        files=[],
    )
    conversation.messages.append(message)
    state = SimpleNamespace(
        owner=owner,
        other=other,
        admin=admin,
        user=owner,
        conversation=conversation,
        message=message,
        share=None,
        db=AsyncMock(),
    )

    async def get_conversation(_db, cid, **_kwargs):
        return conversation if cid == conversation.id else None

    async def get_share(_db, cid, uid):
        if state.share and state.share.conversation_id == cid and state.share.shared_with == uid:
            return state.share
        return None

    async def create_message(_db, *, conversation_id, **data):
        created = Message(
            id=uuid4(),
            conversation_id=conversation_id,
            created_at=now,
            updated_at=now,
            tool_calls=[],
            files=[],
            **data,
        )
        conversation.messages.append(created)
        return created

    async def update_conversation(_db, *, db_conversation, update_data):
        for key, value in update_data.items():
            setattr(db_conversation, key, value)
        return db_conversation

    state.read_messages = AsyncMock(side_effect=lambda *_a, **_k: list(conversation.messages))
    state.create_message = AsyncMock(side_effect=create_message)
    state.update = AsyncMock(side_effect=update_conversation)
    state.archive = AsyncMock(return_value=conversation)
    state.delete = AsyncMock(return_value=True)
    state.revoke = AsyncMock(return_value=True)
    monkeypatch.setattr(
        conversation_repo, "get_conversation_by_id", AsyncMock(side_effect=get_conversation)
    )
    monkeypatch.setattr(conversation_repo, "get_messages_by_conversation", state.read_messages)
    monkeypatch.setattr(
        conversation_repo,
        "count_messages",
        AsyncMock(side_effect=lambda *_a: len(conversation.messages)),
    )
    monkeypatch.setattr(conversation_repo, "create_message", state.create_message)
    monkeypatch.setattr(conversation_repo, "update_conversation", state.update)
    monkeypatch.setattr(conversation_repo, "archive_conversation", state.archive)
    monkeypatch.setattr(conversation_repo, "delete_conversation", state.delete)
    monkeypatch.setattr(conversation_share_repo, "get_share", AsyncMock(side_effect=get_share))
    monkeypatch.setattr(
        conversation_share_repo,
        "get_by_token",
        AsyncMock(
            side_effect=lambda _db, token: (
                state.share if state.share and state.share.share_token == token else None
            )
        ),
    )
    monkeypatch.setattr(
        conversation_share_repo, "get_by_id", AsyncMock(side_effect=lambda *_a: state.share)
    )
    monkeypatch.setattr(conversation_share_repo, "delete", state.revoke)
    monkeypatch.setattr(
        message_rating_repo, "get_user_ratings_for_messages", AsyncMock(return_value={})
    )
    monkeypatch.setattr(
        message_rating_repo, "get_rating_counts_for_messages", AsyncMock(return_value={})
    )
    state.service = ConversationService(state.db)

    def grant(permission):
        state.share = ConversationShare(
            id=uuid4(),
            conversation_id=conversation.id,
            shared_by=owner.id,
            shared_with=other.id,
            permission=permission,
            created_at=now,
        )
        return state.share

    state.grant = grant
    state.path = f"/api/v1/conversations/{conversation.id}"
    previous_overrides = app.dependency_overrides.copy()
    app.dependency_overrides[get_current_user] = lambda: state.user
    app.dependency_overrides[get_conversation_service] = lambda: state.service
    app.dependency_overrides[scoped_conversation_service] = lambda: state.service
    app.dependency_overrides[get_conversation_share_service] = lambda: ConversationShareService(
        state.db
    )
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            state.client = client
            yield state
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous_overrides)


@pytest.mark.parametrize("suffix", ["", "/messages"])
async def test_unshared_account_cannot_read_conversation(access, suffix):
    access.user = access.other
    response = await access.client.get(access.path + suffix)
    assert response.status_code == 404
    assert access.message.content not in response.text
    access.read_messages.assert_not_awaited()


@pytest.mark.parametrize("permission", ["view", "edit"])
@pytest.mark.parametrize("suffix", ["", "/messages"])
async def test_authorized_share_can_read_without_becoming_owner(access, permission, suffix):
    access.user = access.other
    access.grant(permission)
    response = await access.client.get(access.path + suffix)
    assert response.status_code == 200
    assert access.message.content in response.text
    assert access.conversation.user_id == access.owner.id


@pytest.mark.parametrize("actor", ["owner", "admin"])
async def test_workspace_read_requires_ownership_even_for_admin(access, actor):
    access.user = getattr(access, actor)
    response = await access.client.get(access.path + "/messages")
    assert response.status_code == (200 if actor == "owner" else 404)
    if actor == "owner":
        assert response.json()["total"] == 1
    else:
        detail = await access.client.get(f"/api/v1/admin/conversations/{access.conversation.id}")
        assert detail.status_code == 200
        assert access.message.content in detail.text


@pytest.mark.parametrize("permission", [None, "view"])
@pytest.mark.parametrize(
    "method,suffix,payload",
    [
        ("POST", "/messages", {"role": "user", "content": "Unwanted message"}),
        ("PATCH", "", {"title": "Unwanted rename"}),
        ("PATCH", "", {"is_archived": True}),
        ("POST", "/archive", None),
        ("DELETE", "", None),
    ],
)
async def test_unshared_and_view_only_accounts_cannot_write(
    access, permission, method, suffix, payload
):
    access.user = access.other
    if permission:
        access.grant(permission)
    response = await access.client.request(method, access.path + suffix, json=payload)
    assert response.status_code == 404
    access.create_message.assert_not_awaited()
    access.update.assert_not_awaited()
    access.archive.assert_not_awaited()
    access.delete.assert_not_awaited()


@pytest.mark.parametrize(
    "method,suffix,payload",
    [
        ("PATCH", "", {"is_archived": True}),
        ("PATCH", "", {"active_knowledge_base_ids": []}),
        ("POST", "/archive", None),
        ("DELETE", "", None),
    ],
)
async def test_edit_share_cannot_manage_owner_resources(access, method, suffix, payload):
    access.user = access.other
    access.grant("edit")
    response = await access.client.request(method, access.path + suffix, json=payload)
    assert response.status_code == 404
    access.update.assert_not_awaited()
    access.archive.assert_not_awaited()
    access.delete.assert_not_awaited()


async def test_edit_share_can_rename_and_submit_user_text(access):
    access.user = access.other
    access.grant("edit")
    renamed = await access.client.patch(access.path, json={"title": "Shared review notes"})
    submitted = await access.client.post(
        access.path + "/messages", json={"content": "Review comment"}
    )
    assert renamed.status_code == 200
    assert submitted.status_code == 201
    assert submitted.json()["role"] == "user"
    assert access.conversation.title == "Shared review notes"


async def test_owner_can_submit_archive_and_delete(access):
    response = await access.client.post(
        access.path + "/messages", json={"role": "user", "content": "My note"}
    )
    assert response.status_code == 201
    assert response.json()["conversation_id"] == str(access.conversation.id)
    assert (await access.client.post(access.path + "/archive")).status_code == 200
    assert (await access.client.delete(access.path)).status_code == 204
    access.archive.assert_awaited_once()
    access.delete.assert_awaited_once()


@pytest.mark.parametrize(
    "payload",
    [
        {"role": "assistant", "content": "Forged answer"},
        {"role": "system", "content": "Forged instruction"},
        {"role": "user", "content": "Text", "thinking": "Forged reasoning"},
    ],
)
async def test_client_cannot_forge_server_message_fields(access, payload):
    response = await access.client.post(access.path + "/messages", json=payload)
    assert response.status_code == 422
    access.create_message.assert_not_awaited()


@pytest.mark.parametrize("suffix", ["", "/messages"])
async def test_unowned_legacy_conversation_is_not_public(access, suffix):
    access.conversation.user_id = None
    response = await access.client.get(access.path + suffix)
    assert response.status_code == 404
    assert access.message.content not in response.text


async def test_normal_update_cannot_publish_a_public_demo(access):
    response = await access.client.patch(access.path, json={"is_demo": True})
    assert response.status_code == 403
    assert access.conversation.is_demo is False
    access.update.assert_not_awaited()


async def test_admin_can_publish_through_dedicated_demo_endpoint(access):
    access.user = access.admin
    response = await access.client.patch(
        f"/api/v1/admin/conversations/{access.conversation.id}/demo", params={"is_demo": "true"}
    )
    assert response.status_code == 200
    assert access.conversation.is_demo is True


async def test_admin_read_permission_does_not_grant_private_write(access):
    access.user = access.admin
    response = await access.client.post(
        access.path + "/messages", json={"content": "Admin injection"}
    )
    assert response.status_code == 404
    access.create_message.assert_not_awaited()


async def test_revocation_requires_matching_conversation_and_takes_effect_immediately(access):
    access.user = access.other
    share = access.grant("view")
    wrong_path = f"/api/v1/conversations/{uuid4()}/shares/{share.id}"
    assert (await access.client.delete(wrong_path)).status_code == 404
    access.revoke.assert_not_awaited()
    assert (await access.client.delete(f"{access.path}/shares/{share.id}")).status_code == 204
    access.revoke.assert_awaited_once()
    access.share = None
    assert (await access.client.get(access.path + "/messages")).status_code == 404


async def test_anonymous_request_cannot_read_messages(access):
    del app.dependency_overrides[get_current_user]
    response = await access.client.get(access.path + "/messages")
    assert response.status_code == 401
    access.read_messages.assert_not_awaited()


async def test_public_share_returns_only_text_and_revoked_token_stops_working(access):
    share = access.grant("view")
    share.share_token = "public-link-fixture"
    access.message.thinking = "Private reasoning"
    access.conversation.messages.append(
        Message(
            id=uuid4(),
            conversation_id=access.conversation.id,
            role="system",
            content="Private system text",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            tool_calls=[],
            files=[],
        )
    )
    del app.dependency_overrides[get_current_user]
    path = f"/api/v1/conversations/shared/{share.share_token}"
    response = await access.client.get(path)
    assert response.status_code == 200
    assert response.json()["conversation"]["messages"][0]["content"] == access.message.content
    assert len(response.json()["conversation"]["messages"]) == 1
    assert "Private reasoning" not in response.text
    assert "Private system text" not in response.text
    assert str(access.owner.id) not in response.text
    assert "tool_calls" not in response.text
    access.share = None
    assert (await access.client.get(path)).status_code == 404


async def test_public_link_cannot_grant_anonymous_write_access(access):
    response = await access.client.post(
        access.path + "/shares",
        json={"generate_link": True, "permission": "edit"},
    )
    assert response.status_code == 422


@pytest.mark.parametrize("permission", [None, "view", "edit"])
async def test_agent_turn_cannot_use_another_accounts_conversation(access, monkeypatch, permission):
    if permission:
        access.grant(permission)

    @asynccontextmanager
    async def context():
        yield access.db

    monkeypatch.setattr(agent_service, "get_db_context", context)
    with pytest.raises(NotFoundError):
        await agent_service.persist_user_turn(
            access.other,
            "Continue research",
            [],
            str(access.conversation.id),
            None,
        )
    access.create_message.assert_not_awaited()


@pytest.mark.parametrize("actor", ["owner", "other"])
async def test_assistant_persistence_rechecks_owner_identity(access, monkeypatch, actor):
    access.grant("edit")

    @asynccontextmanager
    async def context():
        yield access.db

    monkeypatch.setattr(agent_service, "get_db_context", context)
    result = await agent_service.persist_assistant_turn(
        str(access.conversation.id),
        "Generated answer",
        "test-model",
        [],
        user_id=getattr(access, actor).id,
    )
    if actor == "owner":
        assert result == str(access.conversation.messages[-1].id)
        assert access.conversation.messages[-1].role == "assistant"
        access.create_message.assert_awaited_once()
    else:
        assert result is None
        access.create_message.assert_not_awaited()


@pytest.mark.parametrize("method", ["get_conversation", "list_messages", "add_message"])
async def test_service_call_requires_explicit_actor(access, method):
    args = [access.conversation.id]
    if method == "add_message":
        args.append(MessageCreate(role="user", content="Text"))
    with pytest.raises(TypeError):
        await getattr(access.service, method)(*args)
    access.create_message.assert_not_awaited()


@pytest.mark.parametrize(
    "method,suffix,payload",
    [
        ("GET", "", None),
        ("GET", "/messages", None),
        ("PATCH", "", {"title": "Wrong project"}),
        ("DELETE", "", None),
        ("POST", "/messages", {"content": "Wrong project"}),
        ("GET", "/shares", None),
    ],
)
async def test_same_account_wrong_project_is_hidden(access, method, suffix, payload):
    access.conversation.project_id = uuid4()
    response = await access.client.request(method, access.path + suffix, json=payload)
    assert response.status_code == 404
    assert access.message.content not in response.text
    access.create_message.assert_not_awaited()
    access.read_messages.assert_not_awaited()
    access.update.assert_not_awaited()
    access.delete.assert_not_awaited()


async def test_same_account_matching_project_reads_saved_history(access):
    access.conversation.project_id = uuid4()
    access.service.project_id = access.conversation.project_id
    response = await access.client.get(access.path + "/messages")
    assert response.status_code == 200
    assert access.message.content in response.text
