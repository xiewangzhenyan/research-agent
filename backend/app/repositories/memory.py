"""All queries require an explicit account and project (NULL = default)."""

from sqlalchemy import func, select

from app.db.models.conversation import Conversation, Message
from app.db.models.memory import MemoryItem, MemoryPreference
from app.db.models.user import User


class MemoryRepository:
    def __init__(self, db, user_id, project_id):
        self.db, self.user_id, self.project_id = db, user_id, project_id

    def scope(self, model):
        return (model.user_id == self.user_id, model.project_id == self.project_id)

    async def lock_account(self):
        return await self.db.scalar(select(User).where(User.id == self.user_id).with_for_update())

    async def preference(self):
        return await self.db.scalar(select(MemoryPreference).where(*self.scope(MemoryPreference)))

    async def list(self):
        return list(
            await self.db.scalars(
                select(MemoryItem)
                .where(*self.scope(MemoryItem))
                .order_by(
                    MemoryItem.pinned.desc(),
                    func.coalesce(MemoryItem.updated_at, MemoryItem.created_at).desc(),
                    MemoryItem.id,
                )
                .limit(100)
            )
        )

    async def get(self, item_id):
        return await self.db.scalar(
            select(MemoryItem).where(*self.scope(MemoryItem), MemoryItem.id == item_id)
        )

    async def duplicate(self, content_hash, exclude_id=None):
        query = select(MemoryItem.id).where(
            *self.scope(MemoryItem), MemoryItem.content_hash == content_hash
        )
        if exclude_id is not None:
            query = query.where(MemoryItem.id != exclude_id)
        return await self.db.scalar(query)

    async def counts(self):
        scope = await self.db.scalar(
            select(func.count()).select_from(MemoryItem).where(*self.scope(MemoryItem))
        )
        account = await self.db.scalar(
            select(func.count()).select_from(MemoryItem).where(MemoryItem.user_id == self.user_id)
        )
        return scope, account

    async def source(self, message_id):
        return await self.db.scalar(
            select(Message)
            .join(Conversation)
            .where(
                Message.id == message_id,
                Conversation.user_id == self.user_id,
                Conversation.project_id == self.project_id,
                Message.role.in_(("user", "assistant")),
            )
        )

    async def save(self, item):
        self.db.add(item)
        await self.db.flush()
        await self.db.refresh(item)
        return item

    async def delete(self, item):
        await self.db.delete(item)
        await self.db.flush()
