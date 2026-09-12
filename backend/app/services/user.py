import contextlib
import logging
from uuid import UUID

from fastapi_pagination import Page
from fastapi_pagination.ext.sqlalchemy import paginate
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AlreadyExistsError, AuthenticationError, BadRequestError, NotFoundError
from app.core.security import (
    get_password_hash,
    verify_password,
)
from app.db.models.user import User, UserRole
from app.repositories import user_repo
from app.schemas.conversation_share import AdminUserList, AdminUserRead
from app.schemas.user import UserCreate, UserRead, UserUpdate
from app.services.file_storage import get_file_storage

logger = logging.getLogger(__name__)


class UserService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _is_first_user(self) -> bool:
        count = (await self.db.execute(select(func.count()).select_from(User))).scalar_one()
        return count == 0

    async def get_by_id(self, user_id: UUID) -> User:
        user = await user_repo.get_by_id(self.db, user_id)
        if not user:
            raise NotFoundError(
                message="User not found",
                details={"user_id": user_id},
            )
        return user

    async def get_by_email(self, email: str) -> User | None:
        return await user_repo.get_by_email(self.db, email)

    async def get_multi(
        self,
        *,
        skip: int = 0,
        limit: int = 100,
    ) -> list[User]:
        return await user_repo.get_multi(self.db, skip=skip, limit=limit)

    async def list_paginated(self) -> Page[UserRead]:
        return await paginate(self.db, user_repo.list_query())

    async def delete_non_admins(self) -> int:
        return await user_repo.delete_non_admins(self.db)

    async def has_any(self) -> bool:
        return await user_repo.has_any(self.db)

    async def admin_list_with_counts(
        self,
        *,
        skip: int = 0,
        limit: int = 50,
        search: str | None = None,
        sort_by: str = "created_at",
        sort_dir: str = "desc",
    ) -> AdminUserList:
        rows, total = await user_repo.admin_list_with_counts(
            self.db,
            skip=skip,
            limit=limit,
            search=search,
            sort_by=sort_by,
            sort_dir=sort_dir,
        )
        items = [
            AdminUserRead(
                id=user.id,
                email=user.email,
                full_name=user.full_name,
                role=user.role,
                is_active=user.is_active,
                is_app_admin=getattr(user, "is_app_admin", False),
                conversation_count=conv_count,
                created_at=user.created_at,
            )
            for user, conv_count in rows
        ]
        return AdminUserList(items=items, total=total)

    async def register(self, user_in: UserCreate) -> User:
        """Create a local password account.

        The first user to register is auto-promoted to app-admin — no separate
        CLI step needed. That convenience is a land-grab on a public
        deployment, so the window matters: whoever registers first owns the
        app. Set ``FIRST_ADMIN_EMAIL`` (or run ``cmd create-app-admin``) and
        register before exposing the API publicly.
        """
        existing = await user_repo.get_by_email(self.db, user_in.email)
        if existing:
            raise AlreadyExistsError(
                message="Email already registered",
                details={"email": user_in.email},
            )

        is_first_user = await self._is_first_user()

        hashed_password = get_password_hash(user_in.password)
        user = await user_repo.create(
            self.db,
            email=user_in.email,
            hashed_password=hashed_password,
            full_name=user_in.full_name,
            role=UserRole.ADMIN.value if is_first_user else UserRole.USER.value,
            is_app_admin=is_first_user,
        )
        return user

    async def authenticate(self, email: str, password: str) -> User:
        user = await user_repo.get_by_email(self.db, email)
        if (
            not user
            or not user.hashed_password
            or not verify_password(password, user.hashed_password)
        ):
            raise AuthenticationError(message="Invalid email or password")
        if not user.is_active:
            raise AuthenticationError(message="User account is disabled")
        return user

    async def update(self, user_id: UUID, user_in: UserUpdate) -> User:
        user = await self.get_by_id(user_id)

        update_data = user_in.model_dump(exclude_unset=True)
        if "password" in update_data:
            update_data["hashed_password"] = get_password_hash(update_data.pop("password"))

        return await user_repo.update(self.db, db_user=user, update_data=update_data)

    async def change_password(self, user_id: UUID, current_password: str, new_password: str) -> None:
        user = await self.get_by_id(user_id)
        if not user.hashed_password or not verify_password(current_password, user.hashed_password):
            raise BadRequestError(message="Current password is incorrect")
        await user_repo.update(
            self.db, db_user=user, update_data={"hashed_password": get_password_hash(new_password)}
        )

    async def update_avatar(
        self, user_id: UUID, file_data: bytes, filename: str, content_type: str
    ) -> User:
        ALLOWED_AVATAR_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
        if content_type not in ALLOWED_AVATAR_TYPES:
            raise ValueError("Only JPEG, PNG, WebP, and GIF images are allowed")
        if len(file_data) > 2 * 1024 * 1024:
            raise ValueError("Avatar image too large. Maximum 2MB.")

        storage = get_file_storage()

        user = await self.get_by_id(user_id)
        if user.avatar_url:
            with contextlib.suppress(Exception):
                await storage.delete(user.avatar_url)

        storage_path = await storage.save(f"avatars/{user_id}", filename, file_data)
        return await user_repo.update(
            self.db, db_user=user, update_data={"avatar_url": storage_path}
        )

    def get_avatar_path(self, avatar_url: str) -> str | None:
        full_path = get_file_storage().get_full_path(avatar_url)
        return str(full_path) if full_path is not None else None

    async def delete(self, user_id: UUID) -> User:
        user = await user_repo.delete(self.db, user_id)
        if not user:
            raise NotFoundError(
                message="User not found",
                details={"user_id": user_id},
            )
        return user
