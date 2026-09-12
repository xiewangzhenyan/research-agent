"""Artifact reads always include account and task scope."""

from sqlalchemy import func, select
from sqlalchemy.orm import undefer

from app.db.models.run_artifact import RunArtifact


class RunArtifactRepository:
    def __init__(self, db):
        self.db = db

    async def list(self, run_id, user_id):
        return list(
            await self.db.scalars(
                select(RunArtifact)
                .where(RunArtifact.run_id == run_id, RunArtifact.user_id == user_id)
                .order_by(RunArtifact.created_at, RunArtifact.id)
                .limit(200)
            )
        )

    async def get(self, artifact_id, run_id, user_id):
        return await self.db.scalar(
            select(RunArtifact)
            .options(undefer(RunArtifact.content))
            .where(
                RunArtifact.id == artifact_id,
                RunArtifact.run_id == run_id,
                RunArtifact.user_id == user_id,
            )
        )

    async def bytes_used(self, user_id, run_id=None):
        query = select(func.coalesce(func.sum(RunArtifact.size), 0)).where(
            RunArtifact.user_id == user_id
        )
        if run_id is not None:
            query = query.where(RunArtifact.run_id == run_id)
        return await self.db.scalar(query)

    async def add_all(self, items):
        self.db.add_all(items)
        await self.db.flush()

    async def delete(self, item):
        await self.db.delete(item)
        await self.db.flush()
