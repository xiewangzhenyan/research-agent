"""Authentication routes."""

import logging
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from fastapi.security import OAuth2PasswordRequestForm

from app.api.deps import CurrentUser, UserSvc
from app.core.exceptions import AuthenticationError
from app.core.security import (
    create_access_token,
    create_refresh_token,
    verify_token,
)
from app.schemas.token import RefreshTokenRequest, Token
from app.schemas.user import PasswordChange, UserCreate, UserRead

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "/login",
    response_model=Token,
)
async def login(
    request: Request,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    user_service: UserSvc,
) -> Any:
    """OAuth2 password login, returns access and refresh tokens."""
    user = await user_service.authenticate(form_data.username, form_data.password)
    access_token = create_access_token(subject=str(user.id))
    refresh_token = create_refresh_token(subject=str(user.id))
    return Token(access_token=access_token, refresh_token=refresh_token)


@router.post(
    "/register",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
)
async def register(
    user_in: UserCreate,
    user_service: UserSvc,
) -> Any:
    """Register a new user."""
    user = await user_service.register(user_in)
    return user


@router.post("/refresh", response_model=Token)
async def refresh_token(
    request: Request,
    body: RefreshTokenRequest,
    user_service: UserSvc,
) -> Any:
    """Exchange a refresh token for a new access token."""

    # No DB-backed sessions — validate the refresh JWT directly.
    payload = verify_token(body.refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise AuthenticationError(message="Invalid or expired refresh token")
    subject = payload.get("sub")
    if not subject:
        raise AuthenticationError(message="Invalid refresh token")
    try:
        user_id = UUID(str(subject))
    except ValueError as exc:
        raise AuthenticationError(message="Invalid refresh token") from exc
    user = await user_service.get_by_id(user_id)
    if not user.is_active:
        raise AuthenticationError(message="User account is disabled")

    access_token = create_access_token(subject=str(user.id))
    new_refresh_token = create_refresh_token(subject=str(user.id))
    return Token(access_token=access_token, refresh_token=new_refresh_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def logout(
    body: RefreshTokenRequest,
) -> None:
    """No-op without session tracking. Clients drop their JWTs locally."""
    return None


@router.get("/me", response_model=UserRead)
async def get_current_user_info(current_user: CurrentUser) -> Any:
    """Get current authenticated user information."""
    return current_user


@router.post("/password/change", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    body: PasswordChange, current_user: CurrentUser, user_service: UserSvc
) -> None:
    """Change the signed-in user's password after verifying their current one."""
    await user_service.change_password(current_user.id, body.current_password, body.new_password)
