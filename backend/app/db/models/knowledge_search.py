"""Rebuildable shadow index. Original chunks and citations remain authoritative."""

from uuid import UUID

from pgvector.sqlalchemy import Vector
from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class KnowledgeSearchChunk(Base):
    __tablename__ = "knowledge_search_chunks"
    chunk_id: Mapped[UUID] = mapped_column(
        ForeignKey("knowledge_chunks.id", ondelete="CASCADE"), primary_key=True
    )
    generation_id: Mapped[UUID]
    model_fingerprint: Mapped[str] = mapped_column(String(64))
    tokenizer_version: Mapped[str] = mapped_column(String(100))
    source_hash: Mapped[str] = mapped_column(String(32))
    embedding: Mapped[list[float]] = mapped_column(Vector(512))
    terms: Mapped[dict] = mapped_column(JSONB)
    term_list: Mapped[list[str]] = mapped_column(ARRAY(String))
    token_count: Mapped[int] = mapped_column(Integer)
