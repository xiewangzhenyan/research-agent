"""All public task reads include account and project scope."""

from sqlalchemy import select

from app.db.models.work_task import WorkTask, WorkTaskConversation


class WorkTaskRepository:
    def __init__(self, db, user_id, project_id=None):
        self.db, self.user_id, self.project_id = db, user_id, project_id

    def scoped(self):
        return select(WorkTask).where(
            WorkTask.user_id == self.user_id, WorkTask.project_id == self.project_id
        )

    async def get(self, task_id, *, lock=False):
        query = self.scoped().where(WorkTask.id == task_id)
        if lock:
            query = query.with_for_update()
        return await self.db.scalar(query)

    async def list(self, conversation_id=None, *, active_only=False):
        query = self.scoped()
        if conversation_id:
            query = query.join(WorkTaskConversation).where(
                WorkTaskConversation.conversation_id == conversation_id
            )
        if active_only:
            query = query.where(WorkTask.status.in_(("active", "paused")))
        return list(
            await self.db.scalars(
                query.order_by(
                    WorkTask.updated_at.desc().nullslast(), WorkTask.created_at.desc(), WorkTask.id
                ).limit(20)
            )
        )
