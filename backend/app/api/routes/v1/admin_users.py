from datetime import timedelta
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Query, Request, status

from app.api.deps import CurrentAdmin, UserSvc
from app.core.security import create_access_token
from app.schemas.user import AdminUserList, ImpersonateResponse, UserRead, UserUpdate

router = APIRouter()


@router.get("", response_model=AdminUserList)
async def list_users(
    _: CurrentAdmin,
    service: UserSvc,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    search: str | None = Query(None),
    sort_by: Literal["email", "full_name", "conversations", "created_at"] = Query(
        "created_at", description="Sort column"
    ),
    sort_dir: Literal["asc", "desc"] = Query("desc", description="Sort direction"),
) -> Any:
    result = await service.admin_list_with_counts(
        skip=skip, limit=limit, search=search, sort_by=sort_by, sort_dir=sort_dir
    )
    return result


@router.get("/{user_id}", response_model=UserRead)
async def get_user(
    user_id: UUID,
    _: CurrentAdmin,
    service: UserSvc,
) -> Any:
    return await service.get_by_id(user_id)


@router.patch("/{user_id}", response_model=UserRead)
async def update_user(
    user_id: UUID,
    user_in: UserUpdate,
    _: CurrentAdmin,
    service: UserSvc,
) -> Any:
    user = await service.update(user_id, user_in)
    return user


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def delete_user(
    user_id: UUID,
    _: CurrentAdmin,
    service: UserSvc,
) -> None:
    await service.get_by_id(user_id)  # raises 404 if not found
    await service.delete(user_id)


@router.post("/{user_id}/impersonate", response_model=ImpersonateResponse)
async def impersonate_user(
    request: Request,
    user_id: UUID,
    admin: CurrentAdmin,
    service: UserSvc,
) -> Any:
    """Issue a short-lived (1h) access token to act as the target user."""
    target = await service.get_by_id(user_id)
    token = create_access_token(
        subject=str(target.id),
        expires_delta=timedelta(hours=1),
    )
    return ImpersonateResponse(
        access_token=token,
        token_type="bearer",
        impersonated_user_id=str(target.id),
        impersonated_by=str(admin.id),
        expires_in=3600,
    )
