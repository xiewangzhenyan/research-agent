"""Human-confirmed, project-scoped memory; no implicit extraction from chat."""

from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
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
