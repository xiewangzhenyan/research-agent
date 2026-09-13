"""Consent, ownership, optimistic edits and bounded recall for project memory."""

import hashlib

from app.core.exceptions import AlreadyExistsError, NotFoundError, RateLimitError
from app.db.models.memory import MemoryItem, MemoryPreference
from app.repositories.memory import MemoryRepository
from app.schemas.memory import MemoryResponse
from app.services.memory_recall import select_memories
from app.services.project import ProjectService


class MemoryService:
    def __init__(self, db, user_id, *, project_id=None):
        self.db, self.user_id, self.project_id = db, user_id, project_id
        self.repo = MemoryRepository(db, user_id, project_id)

    async def authorize(self):
        await ProjectService(self.db, self.user_id).validate(self.project_id)

    async def settings(self):
        await self.authorize()
        pref = await self.repo.preference()
        return {
            "enabled": pref.enabled if pref else False,
            "revision": pref.revision if pref else 0,
        }

    async def configure(self, data):
        await self.authorize()
        await self.repo.lock_account()
        pref = await self.repo.preference()
        if data.revision != (pref.revision if pref else 0):
            raise AlreadyExistsError(message="记忆设置已更新，请刷新后重试")
        if pref is None:
            pref = MemoryPreference(user_id=self.user_id, project_id=self.project_id, revision=0)
        pref.enabled = data.enabled
        pref.revision += 1
        await self.repo.save(pref)
        return {"enabled": pref.enabled, "revision": pref.revision}

    async def list(self):
        settings = await self.settings()
        return {
            **settings,
            "items": [MemoryResponse.model_validate(item) for item in await self.repo.list()],
            "limit": 100,
        }

    async def get(self, item_id):
        await self.authorize()
        item = await self.repo.get(item_id)
        if item is None:
            raise NotFoundError(message="当前项目中不存在此记忆")
        return item

    async def save(self, data, item_id=None):
        await self.authorize()
        await self.repo.lock_account()
        item = await self.get(item_id) if item_id else None
        if item is not None and item.revision != data.revision:
            raise AlreadyExistsError(message="这条记忆已被修改，请刷新后重新编辑")
        if data.source_message_id and not await self.repo.source(data.source_message_id):
            raise NotFoundError(message="来源消息不存在或不属于当前项目")
        if item is not None and data.source_message_id != item.source_message_id:
            raise AlreadyExistsError(message="编辑记忆时不能更换来源")
        content_hash = hashlib.sha256(" ".join(data.content.split()).encode()).hexdigest()
        if await self.repo.duplicate(content_hash, item_id):
            raise AlreadyExistsError(message="当前项目已保存相同内容，无需重复添加")
        if item is None:
            project_count, account_count = await self.repo.counts()
            if project_count >= 100 or account_count >= 500:
                raise RateLimitError(
                    message="记忆数量已达上限(每项目 100 条、每账号 500 条)，请整理后添加"
                )
            item = MemoryItem(user_id=self.user_id, project_id=self.project_id, revision=0)
        for key in ("title", "content", "kind", "pinned", "source_message_id"):
            setattr(item, key, getattr(data, key))
        item.content_hash = content_hash
        item.revision += 1
        return await self.repo.save(item)

    async def delete(self, item_id, revision):
        await self.authorize()
        await self.repo.lock_account()
        item = await self.get(item_id)
        if item.revision != revision:
            raise AlreadyExistsError(message="这条记忆已更新，请刷新后再删除")
        await self.repo.delete(item)

    async def source(self, item_id):
        item = await self.get(item_id)
        message = await self.repo.source(item.source_message_id) if item.source_message_id else None
        if message is None:
            raise NotFoundError(message="原始消息已删除或不可访问")
        return {"conversation_id": str(message.conversation_id)}

    async def recall(self, query, *, strict_knowledge=False):
        if strict_knowledge:
            return {"status": "strict_knowledge", "items": [], "omitted": 0, "estimated_tokens": 0}
        settings = await self.settings()
        if not settings["enabled"]:
            return {"status": "disabled", "items": [], "omitted": 0, "estimated_tokens": 0}
        return select_memories(query, await self.repo.list())
