"""All queries require an explicit account and project (NULL = default)."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, or_, select

from app.db.models.conversation import Conversation, Message
from app.db.models.memory import (
    MemoryExtractionJob,
    MemoryItem,
    MemoryPreference,
    MemoryProposal,
    MemoryVersion,
)
from app.db.models.user import User


class MemoryRepository:
    def __init__(self, db, user_id, project_id):
        self.db, self.user_id, self.project_id = db, user_id, project_id

    def scope(self, model):
        return (model.user_id == self.user_id, model.project_id == self.project_id)

    async def lock_account(self):
        return await self.db.scalar(select(User).where(User.id == self.user_id).with_for_update())

    async def preference(self):
        return await self.db.scalar(
            select(MemoryPreference)
            .where(*self.scope(MemoryPreference))
            .execution_options(populate_existing=True)
        )

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
                .execution_options(populate_existing=True)
            )
        )

    async def get(self, item_id):
        return await self.db.scalar(
            select(MemoryItem)
            .where(*self.scope(MemoryItem), MemoryItem.id == item_id)
            .execution_options(populate_existing=True)
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

    def active(self):
        return (
            MemoryItem.archived_at.is_(None),
            or_(MemoryItem.expires_on.is_(None), MemoryItem.expires_on >= datetime.now(UTC).date()),
        )

    async def semantic(self, vector, fingerprint):
        similarity = 1 - MemoryItem.embedding.cosine_distance(vector)
        rows = await self.db.execute(
            select(MemoryItem.id, similarity.label("score"))
            .where(
                *self.scope(MemoryItem),
                *self.active(),
                MemoryItem.embedding.is_not(None),
                MemoryItem.embedding_revision == MemoryItem.revision,
                MemoryItem.embedding_model == fingerprint,
                similarity >= 0.45,
            )
            .order_by(similarity.desc(), MemoryItem.id)
            .limit(20)
        )
        return {str(row.id): float(row.score) for row in rows}

    async def versions(self, item_id):
        return list(
            await self.db.scalars(
                select(MemoryVersion)
                .where(MemoryVersion.item_id == item_id)
                .order_by(MemoryVersion.revision.desc())
                .limit(30)
            )
        )

    async def snapshot(self, item):
        from app.schemas.memory import MemoryResponse

        existing = await self.db.get(MemoryVersion, (item.id, item.revision))
        if existing is None:
            self.db.add(
                MemoryVersion(
                    item_id=item.id,
                    revision=item.revision,
                    snapshot=MemoryResponse.model_validate(item).model_dump(
                        mode="json", exclude={"state", "index_status"}
                    ),
                    source_message_id=item.source_message_id,
                    created_at=datetime.now(UTC),
                )
            )
            await self.db.flush()
        await self.db.execute(
            delete(MemoryVersion).where(
                MemoryVersion.item_id == item.id, MemoryVersion.revision <= item.revision - 30
            )
        )

    async def proposals(self):
        return list(
            await self.db.scalars(
                select(MemoryProposal)
                .where(
                    *self.scope(MemoryProposal),
                    MemoryProposal.status == "pending",
                    MemoryProposal.expires_at > datetime.now(UTC),
                )
                .order_by(MemoryProposal.created_at.desc())
                .limit(20)
            )
        )

    async def proposal(self, proposal_id):
        return await self.db.scalar(
            select(MemoryProposal).where(
                *self.scope(MemoryProposal), MemoryProposal.id == proposal_id
            )
        )

    async def jobs(self):
        return list(
            await self.db.scalars(
                select(MemoryExtractionJob)
                .where(*self.scope(MemoryExtractionJob))
                .order_by(MemoryExtractionJob.created_at.desc())
                .limit(10)
            )
        )

    async def daily_jobs(self):
        return await self.db.scalar(
            select(func.count())
            .select_from(MemoryExtractionJob)
            .where(
                MemoryExtractionJob.user_id == self.user_id,
                MemoryExtractionJob.created_at >= datetime.now(UTC) - timedelta(days=1),
            )
        )
