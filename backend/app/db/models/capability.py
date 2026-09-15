"""User-managed capability assets, immutable skill versions and scoped bindings."""

from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class CapabilityAsset(Base, TimestampMixin):
    __tablename__ = "capability_assets"
    __table_args__ = (
        UniqueConstraint("id", "owner_id", name="capability_asset_owner_key"),
        ForeignKeyConstraint(
            ["project_id", "owner_id"], ["projects.id", "projects.user_id"], ondelete="CASCADE"
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[UUID | None] = mapped_column(nullable=True)
    kind: Mapped[str] = mapped_column(String(10))
    scope: Mapped[str] = mapped_column(String(10), default="personal")
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(String(1200), default="")
    tags: Mapped[list] = mapped_column(JSONB, default=list)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    config: Mapped[dict] = mapped_column(JSONB, default=dict)
    secret: Mapped[str | None] = mapped_column(Text, nullable=True)
    catalog: Mapped[dict] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(30), default="untested")
    status_message: Mapped[str] = mapped_column(String(400), default="")
    tested_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    published_version: Mapped[int | None] = mapped_column(Integer, nullable=True)


class SkillVersion(Base, TimestampMixin):
    __tablename__ = "skill_versions"
    __table_args__ = (UniqueConstraint("asset_id", "number", name="skill_version_number_key"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    asset_id: Mapped[UUID] = mapped_column(
        ForeignKey("capability_assets.id", ondelete="CASCADE"), index=True
    )
    number: Mapped[int] = mapped_column(Integer)
    manifest: Mapped[dict] = mapped_column(JSONB)
    # Content-addressed package files, never an executable path supplied by a user.
    files: Mapped[dict] = mapped_column(JSONB)
    digest: Mapped[str] = mapped_column(String(64))


class CapabilityBinding(Base, TimestampMixin):
    __tablename__ = "capability_bindings"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "context_key", "agent_key", "asset_id", name="capability_binding_key"
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    context_key: Mapped[str] = mapped_column(String(40))
    agent_key: Mapped[str] = mapped_column(String(40), default="assistant")
    asset_id: Mapped[UUID] = mapped_column(
        ForeignKey("capability_assets.id", ondelete="CASCADE"), index=True
    )


class CapabilityAudit(Base):
    __tablename__ = "capability_audit"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    asset_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("capability_assets.id", ondelete="SET NULL"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(40))
    revision: Mapped[int] = mapped_column(Integer)
    # No tool arguments, raw headers, URLs or environment values in audit records.
    timestamp: Mapped[str] = mapped_column(String(40))


class CapabilityInvocation(Base, TimestampMixin):
    """At-most-once dispatch per run/arguments; uncertain calls are never retried."""

    __tablename__ = "capability_invocations"
    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="CASCADE"), primary_key=True
    )
    fingerprint: Mapped[str] = mapped_column(String(64), primary_key=True)
    status: Mapped[str] = mapped_column(String(20), default="dispatching")
    result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
