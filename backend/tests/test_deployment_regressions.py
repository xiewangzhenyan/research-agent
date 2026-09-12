"""Regressions for live account actions and readable chat attachments."""

import io
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_current_user, get_user_service
from app.core.exceptions import BadRequestError
from app.core.security import get_password_hash, verify_password
from app.main import app
from app.schemas.user import UserCreate
from app.services.file_upload import FileUploadService
from app.services.user import UserService


@pytest.mark.anyio
async def test_registration_cannot_choose_admin():
    service = UserService(AsyncMock())
    service._is_first_user = AsyncMock(return_value=False)
    with patch("app.services.user.user_repo") as repo:
        repo.get_by_email = AsyncMock(return_value=None)
        repo.create = AsyncMock()
        await service.register(
            UserCreate(email="regression@example.com", password="test-password", role="admin")
        )
        assert repo.create.call_args.kwargs["role"] == "user"
        assert repo.create.call_args.kwargs["is_app_admin"] is False


@pytest.mark.anyio
async def test_password_change_verifies_existing_password():
    service = UserService(AsyncMock())
    user = SimpleNamespace(id=uuid4(), hashed_password=get_password_hash("old-password"))
    service.get_by_id = AsyncMock(return_value=user)
    with patch("app.services.user.user_repo.update", new_callable=AsyncMock) as update:
        with pytest.raises(BadRequestError):
            await service.change_password(user.id, "wrong-password", "new-password")
        update.assert_not_awaited()
        await service.change_password(user.id, "old-password", "new-password")
        encoded = update.call_args.kwargs["update_data"]["hashed_password"]
        assert verify_password("new-password", encoded)
        assert not verify_password("old-password", encoded)


@pytest.mark.anyio
async def test_password_route_validates_and_uses_authenticated_user():
    user = SimpleNamespace(id=uuid4())
    service = SimpleNamespace(change_password=AsyncMock())
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_user_service] = lambda: service
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/auth/password/change",
                json={"current_password": "old-password", "new_password": "short"},
            )
            assert response.status_code == 422
            service.change_password.assert_not_awaited()
            response = await client.post(
                "/api/v1/auth/password/change",
                json={
                    "current_password": "old-password",
                    "new_password": "new-password",
                    "user_id": str(uuid4()),
                },
            )
            assert response.status_code == 204
            service.change_password.assert_awaited_once_with(
                user.id, "old-password", "new-password"
            )
    finally:
        app.dependency_overrides.clear()


@pytest.mark.anyio
async def test_profile_cannot_bypass_current_password():
    user = SimpleNamespace(id=uuid4())
    service = SimpleNamespace(update=AsyncMock())
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_user_service] = lambda: service
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.patch("/api/v1/users/me", json={"password": "new-password"})
            assert response.status_code == 400
            service.update.assert_not_awaited()
    finally:
        app.dependency_overrides.clear()


@pytest.mark.anyio
async def test_real_document_parsers():
    import pymupdf
    from docx import Document

    service = FileUploadService(AsyncMock())
    with pymupdf.open() as pdf:
        page = pdf.new_page()
        page.insert_text((72, 72), "ATTACHMENT-PDF-OK")
        content = await service.parse_content(pdf.tobytes(), "pdf")
        assert "ATTACHMENT-PDF-OK" in content
    doc = Document()
    doc.add_paragraph("ATTACHMENT-DOCX-OK")
    buf = io.BytesIO()
    doc.save(buf)
    assert "ATTACHMENT-DOCX-OK" in await service.parse_content(buf.getvalue(), "docx")


@pytest.mark.anyio
@pytest.mark.parametrize(
    "content,mime,name",
    [(b"not a pdf", "application/pdf", "broken.pdf"), (b"\xff\xfe", "text/plain", "invalid.txt")],
)
async def test_unreadable_upload_never_claims_success(content, mime, name):
    service = FileUploadService(AsyncMock())
    with patch("app.services.file_upload.get_file_storage") as storage:
        with pytest.raises(BadRequestError, match="No readable text"):
            await service.upload(
                user_id=uuid4(), file_data=content, filename=name, content_type=mime
            )
        storage.assert_not_called()
