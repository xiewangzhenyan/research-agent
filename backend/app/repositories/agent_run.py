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
            or_(
                earlier.conversation_id == AgentRun.conversation_id,
                and_(
                    earlier.user_id == AgentRun.user_id,
                    earlier.project_id.is_not_distinct_from(AgentRun.project_id),
                    earlier.request["work_task"]["id"].astext
                    == AgentRun.request["work_task"]["id"].astext,
                ),
            ),
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
                        ~blocked,
                        AgentRun.status == "cancelling",
                    )
                )
                .order_by(AgentRun.started_at.asc().nullsfirst(), AgentRun.created_at)
                .limit(100)
            )
        )

    async def has_predecessor(self, run):
        return bool(
            await self.db.scalar(
                select(
                    exists().where(
                        or_(
                            AgentRun.conversation_id == run.conversation_id
                            if run.conversation_id
                            else False,
                            and_(
                                AgentRun.user_id == run.user_id,
                                AgentRun.project_id == run.project_id,
                                AgentRun.request["work_task"]["id"].astext
                                == run.request.get("work_task", {}).get("id"),
                            )
                            if run.request.get("work_task")
                            else False,
                        ),
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
        if run.request.get("work_task"):
            from app.services.work_task import sync_step

            await sync_step(self.db, run, kind, data)
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
