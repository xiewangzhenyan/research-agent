"""Long-lived work state. Runs/checkpoints may expire independently."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class WorkTask(Base, TimestampMixin):
    __tablename__ = "work_tasks"
    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "user_id"], ["projects.id", "projects.user_id"], ondelete="CASCADE"
        ),
        Index("work_tasks_scope_idx", "user_id", "project_id", "updated_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    project_id: Mapped[UUID | None] = mapped_column(nullable=True)
    title: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(16), default="active")
    revision: Mapped[int] = mapped_column(Integer, default=1)
    event_seq: Mapped[int] = mapped_column(Integer, default=0)


class WorkTaskRevision(Base):
    __tablename__ = "work_task_revisions"
    task_id: Mapped[UUID] = mapped_column(
        ForeignKey("work_tasks.id", ondelete="CASCADE"), primary_key=True
    )
    revision: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_message_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("messages.id", ondelete="SET NULL"), nullable=True
    )
    source_hash: Mapped[str] = mapped_column(String(64))
    replaces: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class WorkTaskConversation(Base):
    __tablename__ = "work_task_conversations"
    task_id: Mapped[UUID] = mapped_column(
        ForeignKey("work_tasks.id", ondelete="CASCADE"), primary_key=True
    )
    conversation_id: Mapped[UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), primary_key=True
    )


class WorkStep(Base, TimestampMixin):
    __tablename__ = "work_steps"
    __table_args__ = (Index("work_steps_task_idx", "task_id", "created_at"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    task_id: Mapped[UUID] = mapped_column(ForeignKey("work_tasks.id", ondelete="CASCADE"))
    revision: Mapped[int] = mapped_column(Integer)
    run_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="SET NULL"), unique=True, nullable=True
    )
    action: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(24), default="queued")
    phase: Mapped[str] = mapped_column(String(160), default="等待执行")
    result_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)


class WorkTaskEvent(Base):
    __tablename__ = "work_task_events"
    __table_args__ = (UniqueConstraint("task_id", "operation_id"),)
    task_id: Mapped[UUID] = mapped_column(
        ForeignKey("work_tasks.id", ondelete="CASCADE"), primary_key=True
    )
    seq: Mapped[int] = mapped_column(Integer, primary_key=True)
    operation_id: Mapped[UUID] = mapped_column()
    request_hash: Mapped[str] = mapped_column(String(64))
    revision: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(24))
    data: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
