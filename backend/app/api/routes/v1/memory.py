"""Automatic project memory with user management. Headers cannot grant account access."""

from uuid import UUID

from fastapi import APIRouter, Query, Response

from app.api.deps import CurrentUser, DBSession
from app.api.project_deps import CurrentProject
from app.schemas.memory import (
    MemoryCreate,
    MemoryPreferenceWrite,
    MemoryPreview,
    MemoryProposalAccept,
    MemoryResponse,
    MemoryRevisionWrite,
    MemoryUpdate,
)
from app.services.memory import MemoryService

router = APIRouter(prefix="/memory", tags=["memory"])


@router.get("/{item_id}/source")
async def source(item_id: UUID, db: DBSession, user: CurrentUser, project_id: CurrentProject):
    return await MemoryService(db, user.id, project_id=project_id).source(item_id)


@router.get("")
async def list_memories(db: DBSession, user: CurrentUser, project_id: CurrentProject):
    return await MemoryService(db, user.id, project_id=project_id).list()


@router.put("/settings")
async def configure(
    data: MemoryPreferenceWrite, db: DBSession, user: CurrentUser, project_id: CurrentProject
):
    return await MemoryService(db, user.id, project_id=project_id).configure(data)


@router.post("/preview")
async def preview(
    data: MemoryPreview, db: DBSession, user: CurrentUser, project_id: CurrentProject
):
    return await MemoryService(db, user.id, project_id=project_id).recall(data.query)


@router.post("", response_model=MemoryResponse, status_code=201)
async def create(data: MemoryCreate, db: DBSession, user: CurrentUser, project_id: CurrentProject):
    return await MemoryService(db, user.id, project_id=project_id).save(data)


@router.put("/{item_id}", response_model=MemoryResponse)
async def update(
    item_id: UUID, data: MemoryUpdate, db: DBSession, user: CurrentUser, project_id: CurrentProject
):
    return await MemoryService(db, user.id, project_id=project_id).save(data, item_id)


@router.delete("/{item_id}", status_code=204)
async def delete(
    item_id: UUID,
    db: DBSession,
    user: CurrentUser,
    project_id: CurrentProject,
    revision: int = Query(ge=1),
):
    await MemoryService(db, user.id, project_id=project_id).delete(item_id, revision)
    return Response(status_code=204)


@router.post("/reindex")
async def reindex(db: DBSession, user: CurrentUser, project_id: CurrentProject):
    return await MemoryService(db, user.id, project_id=project_id).reindex()


@router.post("/{item_id}/archive", response_model=MemoryResponse)
async def archive(
    item_id: UUID,
    data: MemoryRevisionWrite,
    db: DBSession,
    user: CurrentUser,
    project_id: CurrentProject,
):
    return await MemoryService(db, user.id, project_id=project_id).archive(
        item_id, data.revision, True
    )


@router.post("/{item_id}/restore", response_model=MemoryResponse)
async def restore(
    item_id: UUID,
    data: MemoryRevisionWrite,
    db: DBSession,
    user: CurrentUser,
    project_id: CurrentProject,
):
    return await MemoryService(db, user.id, project_id=project_id).archive(
        item_id, data.revision, False
    )


@router.get("/{item_id}/history")
async def history(item_id: UUID, db: DBSession, user: CurrentUser, project_id: CurrentProject):
    return await MemoryService(db, user.id, project_id=project_id).history(item_id)


@router.post("/proposals/{proposal_id}/accept")
async def accept(
    proposal_id: UUID,
    data: MemoryProposalAccept,
    db: DBSession,
    user: CurrentUser,
    project_id: CurrentProject,
):
    return await MemoryService(db, user.id, project_id=project_id).decide(
        proposal_id, data.revision, data
    )


@router.post("/proposals/{proposal_id}/reject")
async def reject(
    proposal_id: UUID,
    data: MemoryRevisionWrite,
    db: DBSession,
    user: CurrentUser,
    project_id: CurrentProject,
):
    return await MemoryService(db, user.id, project_id=project_id).decide(
        proposal_id, data.revision
    )


@router.post("/jobs/{job_id}/retry")
async def retry(job_id: UUID, db: DBSession, user: CurrentUser, project_id: CurrentProject):
    return await MemoryService(db, user.id, project_id=project_id).retry(job_id)
