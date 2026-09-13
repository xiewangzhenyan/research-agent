"""Task persistence. Row locks serialize sequence allocation and account limits."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.db.models.agent_run import AgentRun, AgentRunEvent
from app.db.models.user import User

ACTIVE = ("queued", "running", "waiting_input", "cancelling")
TERMINAL = ("completed", "failed", "cancelled")


class AgentRunRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def account_lock(self, user_id: UUID):
        return await self.db.scalar(select(User).where(User.id == user_id).with_for_update())

    async def get(self, run_id, user_id=None, *, lock=False):
        query = select(AgentRun).where(AgentRun.id == run_id)
        if user_id is not None:
            query = query.where(AgentRun.user_id == user_id)
        if lock:
            query = query.with_for_update()
        return await self.db.scalar(query)

    async def by_key(self, user_id, key):
        return await self.db.scalar(
            select(AgentRun).where(AgentRun.user_id == user_id, AgentRun.idempotency_key == key)
        )

    async def active_count(self, user_id):
        return await self.db.scalar(
            select(func.count())
            .select_from(AgentRun)
            .where(AgentRun.user_id == user_id, AgentRun.status.in_(ACTIVE))
        )

    async def list(self, user_id, offset=0, *, project_id=None):
        return list(
            await self.db.scalars(
                select(AgentRun)
                .where(AgentRun.user_id == user_id, AgentRun.project_id == project_id)
                .order_by(AgentRun.created_at.desc(), AgentRun.id)
                .offset(offset)
                .limit(50)
            )
        )

    async def candidates(self):
        earlier = aliased(AgentRun)
        # Keep turns in one conversation ordered, including across workers and
        # while a previous turn is waiting for human input. Other chats can run.
        blocked = exists().where(
            earlier.conversation_id == AgentRun.conversation_id,
            earlier.status.in_(ACTIVE),
            or_(
                earlier.created_at < AgentRun.created_at,
                and_(earlier.created_at == AgentRun.created_at, earlier.id < AgentRun.id),
            ),
        )
        return list(
            await self.db.scalars(
                select(AgentRun.id)
                .where(AgentRun.status.in_(("queued", "running", "cancelling")))
                .where(
                    or_(
                        AgentRun.conversation_id.is_(None),
                        ~blocked,
                        AgentRun.status == "cancelling",
                    )
                )
                .order_by(AgentRun.started_at.asc().nullsfirst(), AgentRun.created_at)
                .limit(100)
            )
        )

    async def has_predecessor(self, run):
        if run.conversation_id is None:
            return False
        return bool(
            await self.db.scalar(
                select(
                    exists().where(
                        AgentRun.conversation_id == run.conversation_id,
                        AgentRun.status.in_(ACTIVE),
                        or_(
                            AgentRun.created_at < run.created_at,
                            and_(AgentRun.created_at == run.created_at, AgentRun.id < run.id),
                        ),
                    )
                )
            )
        )

    async def add(self, run):
        self.db.add(run)
        await self.db.flush()
        return run

    async def event(self, run, kind, data):
        run.event_seq += 1
        event = AgentRunEvent(
            run_id=run.id, seq=run.event_seq, kind=kind, data=data, created_at=datetime.now(UTC)
        )
        self.db.add(event)
        await self.db.flush()
        return event

    async def events(self, run_id, after):
        return list(
            await self.db.scalars(
                select(AgentRunEvent)
                .where(AgentRunEvent.run_id == run_id, AgentRunEvent.seq > after)
                .order_by(AgentRunEvent.seq)
                .limit(100)
            )
        )
