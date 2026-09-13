"""Project-scoped confirmed memories and separately consented extraction candidates."""

from datetime import date, datetime
from uuid import UUID, uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class MemoryPreference(Base, TimestampMixin):
    __tablename__ = "memory_preferences"
    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "user_id"],
            ["projects.id", "projects.user_id"],
            deferrable=True,
            initially="DEFERRED",
        ),
        UniqueConstraint("user_id", "project_id", postgresql_nulls_not_distinct=True),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    project_id: Mapped[UUID | None] = mapped_column(nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    revision: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    auto_extract: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    semantic_recall: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    extraction_model: Mapped[str | None] = mapped_column(String(100), nullable=True)


class MemoryItem(Base, TimestampMixin):
    __tablename__ = "memory_items"
    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "user_id"],
            ["projects.id", "projects.user_id"],
            deferrable=True,
            initially="DEFERRED",
        ),
        UniqueConstraint(
            "user_id", "project_id", "content_hash", postgresql_nulls_not_distinct=True
        ),
        Index("memory_items_scope_idx", "user_id", "project_id"),
        Index("memory_items_source_idx", "source_message_id"),
        CheckConstraint("char_length(content) BETWEEN 1 AND 1200", name="bounded_memory_content"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    project_id: Mapped[UUID | None] = mapped_column(nullable=True)
    title: Mapped[str] = mapped_column(String(80))
    content: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(20))
    pinned: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    content_hash: Mapped[str] = mapped_column(String(64))
    revision: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    # Deleting a source conversation also removes notes derived from its messages.
    source_message_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("messages.id", ondelete="CASCADE"), nullable=True
    )

    expires_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(512), nullable=True)
    embedding_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    embedding_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    index_attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")


class MemoryVersion(Base):
    __tablename__ = "memory_versions"
    item_id: Mapped[UUID] = mapped_column(
        ForeignKey("memory_items.id", ondelete="CASCADE"), primary_key=True
    )
    revision: Mapped[int] = mapped_column(Integer, primary_key=True)
    snapshot: Mapped[dict] = mapped_column(JSONB)
    source_message_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("messages.id", ondelete="CASCADE"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class MemoryProposal(Base, TimestampMixin):
    __tablename__ = "memory_proposals"
    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "user_id"],
            ["projects.id", "projects.user_id"],
            deferrable=True,
            initially="DEFERRED",
        ),
        Index("memory_proposals_scope_idx", "user_id", "project_id", "status"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    project_id: Mapped[UUID | None] = mapped_column(nullable=True)
    source_message_id: Mapped[UUID] = mapped_column(
        ForeignKey("messages.id", ondelete="CASCADE"), index=True
    )
    target_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("memory_items.id", ondelete="CASCADE"), nullable=True, index=True
    )
    target_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    action: Mapped[str] = mapped_column(String(12))
    payload: Mapped[dict] = mapped_column(JSONB)
    reason: Mapped[str] = mapped_column(String(500))
    quote: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default="pending")
    revision: Mapped[int] = mapped_column(Integer, default=1)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class MemoryExtractionJob(Base, TimestampMixin):
    __tablename__ = "memory_extraction_jobs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "user_id"],
            ["projects.id", "projects.user_id"],
            deferrable=True,
            initially="DEFERRED",
        ),
        Index("memory_extraction_jobs_dispatch_idx", "status", "created_at"),
        Index("memory_extraction_jobs_scope_idx", "user_id", "project_id"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    project_id: Mapped[UUID | None] = mapped_column(nullable=True)
    source_message_id: Mapped[UUID] = mapped_column(
        ForeignKey("messages.id", ondelete="CASCADE"), unique=True
    )
    settings_revision: Mapped[int] = mapped_column(Integer)
    configuration: Mapped[dict] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(16), default="queued")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    result_count: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(String(160), nullable=True)
    usage: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
