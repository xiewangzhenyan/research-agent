"""Bearer-authenticated background task API; execution never belongs to HTTP."""

from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser
from app.db.session import get_db_session
from app.schemas.agent_run import (
    AgentRunCreate,
    AgentRunEventResponse,
    AgentRunResponse,
    AgentRunResume,
)
from app.services.agent_run import AgentRunService
from app.services.run_artifact import RunArtifactService
from app.services.tool_policy import tool_catalog

router = APIRouter(prefix="/runs", tags=["tasks"])


@router.get("/tools")
async def tools(user: CurrentUser):
    return await tool_catalog(user)


@router.post("", response_model=AgentRunResponse, status_code=201)
async def create(
    data: AgentRunCreate, user: CurrentUser, db: AsyncSession = Depends(get_db_session)
):
    return await AgentRunService(db, user.id).create(data)


@router.get("", response_model=list[AgentRunResponse])
async def list_runs(
    user: CurrentUser,
    offset: int = Query(default=0, ge=0, le=100000),
    db: AsyncSession = Depends(get_db_session),
):
    return await AgentRunService(db, user.id).repo.list(user.id, offset)


@router.get("/{run_id}", response_model=AgentRunResponse)
async def get(run_id: UUID, user: CurrentUser, db: AsyncSession = Depends(get_db_session)):
    return await AgentRunService(db, user.id).get(run_id)


@router.get("/{run_id}/events", response_model=list[AgentRunEventResponse])
async def events(
    run_id: UUID,
    user: CurrentUser,
    after: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db_session),
):
    service = AgentRunService(db, user.id)
    await service.get(run_id)
    return await service.repo.events(run_id, after)


@router.post("/{run_id}/cancel", response_model=AgentRunResponse)
async def cancel(run_id: UUID, user: CurrentUser, db: AsyncSession = Depends(get_db_session)):
    return await AgentRunService(db, user.id).cancel(run_id)


@router.post("/{run_id}/resume", response_model=AgentRunResponse)
async def resume(
    run_id: UUID,
    data: AgentRunResume,
    user: CurrentUser,
    db: AsyncSession = Depends(get_db_session),
):
    return await AgentRunService(db, user.id).resume(run_id, data)


@router.get("/{run_id}/artifacts")
async def artifacts(run_id: UUID, user: CurrentUser, db: AsyncSession = Depends(get_db_session)):
    return await RunArtifactService(db, user.id).list(run_id)


@router.get("/{run_id}/artifacts/{artifact_id}")
async def download_artifact(
    run_id: UUID, artifact_id: UUID, user: CurrentUser, db: AsyncSession = Depends(get_db_session)
):
    item = await RunArtifactService(db, user.id).get(run_id, artifact_id)
    return Response(
        item.content,
        media_type=item.mime_type,
        headers={
            "Content-Disposition": "attachment; filename*=UTF-8''" + quote(item.name, safe=""),
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'; sandbox",
        },
    )


@router.delete("/{run_id}/artifacts/{artifact_id}", status_code=204)
async def delete_artifact(
    run_id: UUID, artifact_id: UUID, user: CurrentUser, db: AsyncSession = Depends(get_db_session)
):
    await RunArtifactService(db, user.id).delete(run_id, artifact_id)
    return Response(status_code=204)
