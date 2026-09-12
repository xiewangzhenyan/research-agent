"""Native, account-scoped knowledge storage. No external knowledge service."""

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class KnowledgeBase(Base, TimestampMixin):
    __tablename__ = "knowledge_bases"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text, default="")
    chunking_config: Mapped[dict] = mapped_column(
        JSONB,
        default=lambda: {"chunk_size": 450, "chunk_overlap": 65},
        server_default='{"chunk_size":450,"chunk_overlap":65}',
    )


class KnowledgeDocument(Base, TimestampMixin):
    __tablename__ = "knowledge_documents"
    __table_args__ = (
        UniqueConstraint("knowledge_base_id", "sha256"),
        CheckConstraint("source_kind IN ('file', 'manual', 'faq')", name="knowledge_source_kind"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    knowledge_base_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("knowledge_bases.id", ondelete="CASCADE"), index=True
    )
    filename: Mapped[str] = mapped_column(String(255))
    storage_path: Mapped[str] = mapped_column(Text)
    size: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    error: Mapped[str | None] = mapped_column(Text)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    embedding_model: Mapped[str | None] = mapped_column(String(150))
    job_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), default=uuid.uuid4)
    processing_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    parse_report: Mapped[dict | None] = mapped_column(JSONB(none_as_null=True))
    chunking_config: Mapped[dict | None] = mapped_column(JSONB(none_as_null=True))
    requested_chunking_config: Mapped[dict | None] = mapped_column(JSONB(none_as_null=True))
    source_kind: Mapped[str] = mapped_column(String(16), default="file", server_default="file")
    source_data: Mapped[dict | None] = mapped_column(JSONB(none_as_null=True))
    revision: Mapped[int] = mapped_column(Integer, default=1, server_default="1")

    @property
    def title(self) -> str:
        return (
            (self.source_data or {}).get("title")
            or (self.source_data or {}).get("question")
            or self.filename
        )


class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunks"
    __table_args__ = (UniqueConstraint("document_id", "position"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("knowledge_documents.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(Integer)
    page: Mapped[int | None] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    location: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")
    embedding: Mapped[list[float]] = mapped_column(ARRAY(Float))


class KnowledgeCitation(Base, TimestampMixin):
    """Owned snapshot of the evidence used for one assistant message."""

    __tablename__ = "knowledge_citations"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    message_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("messages.id", ondelete="CASCADE"), index=True
    )
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("knowledge_documents.id", ondelete="SET NULL"), index=True
    )
    source: Mapped[dict] = mapped_column(JSONB)


class KnowledgeRetrievalPreference(Base):
    __tablename__ = "knowledge_retrieval_preferences"
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    config: Mapped[dict] = mapped_column(JSONB)
