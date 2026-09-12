"""Account-owned generated files; bytes are never embedded in task events."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, LargeBinary, String, func
from sqlalchemy.orm import Mapped, deferred, mapped_column

from app.db.base import Base


class RunArtifact(Base):
    __tablename__ = "run_artifacts"
    __table_args__ = (
        CheckConstraint(
            "size >= 0 AND size <= 2097152 AND octet_length(content) = size", name="bounded_content"
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    execution_id: Mapped[UUID] = mapped_column(index=True)
    name: Mapped[str] = mapped_column(String(120))
    mime_type: Mapped[str] = mapped_column(String(80))
    size: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    content: Mapped[bytes] = deferred(mapped_column(LargeBinary))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
