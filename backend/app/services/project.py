"""Explicit project authorization; NULL identifies the legacy default workspace."""

from uuid import UUID

from sqlalchemy import func, select

from app.core.exceptions import NotFoundError, RateLimitError
from app.db.models.knowledge import KnowledgeBase
from app.db.models.project import Project
from app.db.models.user import User
from app.schemas.project import ProjectResponse
from app.services.knowledge import KnowledgeService


class ProjectService:
    def __init__(self, db, user_id):
        self.db, self.user_id = db, user_id

    async def get(self, project_id):
        project = await self.db.scalar(
            select(Project).where(Project.id == project_id, Project.user_id == self.user_id)
        )
        if project is None:
            raise NotFoundError(message="项目不存在或无权访问")
        return project

    async def validate(self, project_id):
        if project_id is not None:
            await self.get(project_id)

    async def live_base_ids(self):
        return {
            str(v)
            for v in await self.db.scalars(
                select(KnowledgeBase.id).where(KnowledgeBase.user_id == self.user_id)
            )
        }

    async def defaults(self, project_id):
        if project_id is None:
            return []
        project = await self.get(project_id)
        live = await self.live_base_ids()
        return [v for v in project.knowledge_base_ids if v in live]

    async def list(self):
        projects = await self.db.scalars(
            select(Project)
            .where(Project.user_id == self.user_id)
            .order_by(Project.created_at, Project.id)
        )
        live = await self.live_base_ids()
        return [
            ProjectResponse.model_validate(p).model_copy(
                update={"knowledge_base_ids": [UUID(v) for v in p.knowledge_base_ids if v in live]}
            )
            for p in projects
        ]

    async def save(self, data, project_id=None):
        # Serialize project creation and bound account resource use.
        await self.db.scalar(select(User).where(User.id == self.user_id).with_for_update())
        await KnowledgeService(self.db, self.user_id).validate_scope(data.knowledge_base_ids, None)
        if project_id is None:
            count = await self.db.scalar(
                select(func.count()).select_from(Project).where(Project.user_id == self.user_id)
            )
            if count >= 50:
                raise RateLimitError(message="每个账号最多创建 50 个项目")
            project = Project(user_id=self.user_id)
            self.db.add(project)
        else:
            project = await self.get(project_id)
        project.name, project.description = data.name, data.description.strip()
        project.knowledge_base_ids = list(dict.fromkeys(str(v) for v in data.knowledge_base_ids))
        await self.db.flush()
        await self.db.refresh(project)
        return project
