"""Rebuildable, source-linked context blocks; raw messages remain authoritative."""

from datetime import datetime
from uuid import UUID, uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class ConversationContextJob(Base, TimestampMixin):
    __tablename__ = "conversation_context_jobs"

    conversation_id: Mapped[UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), primary_key=True
    )
    status: Mapped[str] = mapped_column(String(16), default="queued", server_default="queued")
    revision: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    cursor_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cursor_id: Mapped[UUID | None] = mapped_column(nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    configuration: Mapped[dict] = mapped_column(JSONB, default=dict)


class ConversationContextBlock(Base, TimestampMixin):
    __tablename__ = "conversation_context_blocks"
    __table_args__ = (
        Index("conversation_context_scope_idx", "conversation_id", "through_at", "through_id"),
        Index("conversation_context_terms_idx", "terms", postgresql_using="gin"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    conversation_id: Mapped[UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE")
    )
    through_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    through_id: Mapped[UUID] = mapped_column()
    mode: Mapped[str] = mapped_column(String(16))
    notes: Mapped[list] = mapped_column(JSONB, default=list)
    terms: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    usage: Mapped[dict] = mapped_column(JSONB, default=dict)


class ConversationContextSource(Base):
    __tablename__ = "conversation_context_sources"
    __table_args__ = (Index("conversation_context_source_message_idx", "message_id"),)

    block_id: Mapped[UUID] = mapped_column(
        ForeignKey("conversation_context_blocks.id", ondelete="CASCADE"), primary_key=True
    )
    message_id: Mapped[UUID] = mapped_column(
        ForeignKey("messages.id", ondelete="CASCADE"), primary_key=True
    )
    content_hash: Mapped[str] = mapped_column(String(64))
    embedding: Mapped[list[float] | None] = mapped_column(Vector(512), nullable=True)
    embedding_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
