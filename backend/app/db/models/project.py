"""Account-owned workspaces. Knowledge bases remain independent account assets."""

from uuid import UUID, uuid4

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class Project(Base, TimestampMixin):
    __tablename__ = "projects"
    __table_args__ = (UniqueConstraint("id", "user_id", name="projects_id_user_key"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    description: Mapped[str] = mapped_column(String(500), default="", server_default="")
    knowledge_base_ids: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default="[]")
