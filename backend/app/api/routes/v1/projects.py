"""Manage account project spaces and reusable knowledge defaults."""

from uuid import UUID

from fastapi import APIRouter

from app.api.deps import CurrentUser, DBSession
from app.schemas.project import ProjectResponse, ProjectWrite
from app.services.project import ProjectService

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("", response_model=list[ProjectResponse])
async def list_projects(db: DBSession, user: CurrentUser):
    return await ProjectService(db, user.id).list()


@router.post("", response_model=ProjectResponse, status_code=201)
async def create_project(data: ProjectWrite, db: DBSession, user: CurrentUser):
    return await ProjectService(db, user.id).save(data)


@router.put("/{project_id}", response_model=ProjectResponse)
async def update_project(project_id: UUID, data: ProjectWrite, db: DBSession, user: CurrentUser):
    return await ProjectService(db, user.id).save(data, project_id)
