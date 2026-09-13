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


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(project_id: UUID, db: DBSession, user: CurrentUser):
    service = ProjectService(db, user.id)
    project = await service.get(project_id)
    return ProjectResponse.model_validate(project).model_copy(
        update={"knowledge_base_ids": [UUID(v) for v in await service.defaults(project_id)]}
    )
