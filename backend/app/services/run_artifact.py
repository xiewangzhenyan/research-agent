# ruff: noqa: RUF001
"""Atomic artifact persistence fenced by worker attempt and account quota."""

from uuid import UUID, uuid5

from app.core.exceptions import AlreadyExistsError, NotFoundError, RateLimitError
from app.db.models.run_artifact import RunArtifact
from app.repositories.agent_run import AgentRunRepository
from app.repositories.run_artifact import RunArtifactRepository


def metadata(item):
    return {
        key: str(getattr(item, key))
        if key in {"id", "run_id", "execution_id"}
        else getattr(item, key)
        for key in ("id", "run_id", "execution_id", "name", "mime_type", "size", "sha256")
    }


class RunArtifactService:
    def __init__(self, db, user_id, *, project_id=None):
        self.db, self.user_id = db, user_id
        self.project_id = project_id
        self.runs, self.repo = AgentRunRepository(db), RunArtifactRepository(db)

    async def owned_run(self, run_id, lock=False):
        run = await self.runs.get(run_id, self.user_id, lock=lock)
        if run is None or run.project_id != self.project_id:
            raise NotFoundError(message="任务不存在或无权访问")
        return run

    async def list(self, run_id):
        await self.owned_run(run_id)
        return [metadata(item) for item in await self.repo.list(run_id, self.user_id)]

    async def get(self, run_id, artifact_id):
        await self.owned_run(run_id)
        item = await self.repo.get(artifact_id, run_id, self.user_id)
        if item is None:
            raise NotFoundError(message="文件不存在或已删除")
        return item

    async def delete(self, run_id, artifact_id):
        await self.runs.account_lock(self.user_id)
        run = await self.owned_run(run_id, lock=True)
        if run.status not in {"completed", "failed", "cancelled"}:
            raise AlreadyExistsError(message="任务结束后可删除产物")
        await self.repo.delete(await self.get(run_id, artifact_id))

    async def save(self, run_id, attempt, execution_id, files):
        await self.runs.account_lock(self.user_id)
        run = await self.owned_run(run_id, lock=True)
        if run.status != "running" or run.attempt != attempt:
            raise AlreadyExistsError(message="任务执行权已失效，未保存产物")
        execution_id = UUID(str(execution_id))
        existing = {item.id: item for item in await self.repo.list(run_id, self.user_id)}
        items, new = [], []
        for file in files:
            key = uuid5(execution_id, file["name"] + ":" + file["sha256"])
            item = existing.get(key)
            if item is None:
                item = RunArtifact(
                    id=key, run_id=run_id, user_id=self.user_id, execution_id=execution_id, **file
                )
                new.append(item)
            items.append(item)
        added = sum(item.size for item in new)
        if (
            len(existing) + len(new) > 200
            or await self.repo.bytes_used(self.user_id, run_id) + added > 20 * 1024**2
            or await self.repo.bytes_used(self.user_id) + added > 100 * 1024**2
        ):
            raise RateLimitError(
                message="产物空间已满（每任务 20 MiB、每账号 100 MiB），请删除旧产物"
            )
        await self.repo.add_all(new)
        return [metadata(item) for item in items]
