"""Reviewable extraction, expiry, versions and local semantic memory indexing."""

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "0042_memory_lifecycle"
down_revision = "0041_project_memory"
branch_labels = None
depends_on = None


def upgrade():
    for column in [
        sa.Column("auto_extract", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("semantic_recall", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("extraction_model", sa.String(100), nullable=True),
    ]:
        op.add_column("memory_preferences", column)
    for column in [
        sa.Column("expires_on", sa.Date(), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("embedding", Vector(512), nullable=True),
        sa.Column("embedding_revision", sa.Integer(), nullable=True),
        sa.Column("embedding_model", sa.String(100), nullable=True),
        sa.Column("index_attempts", sa.Integer(), nullable=False, server_default="0"),
    ]:
        op.add_column("memory_items", column)
    op.create_table(
        "memory_versions",
        sa.Column(
            "item_id",
            sa.Uuid(),
            sa.ForeignKey("memory_items.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("revision", sa.Integer(), primary_key=True),
        sa.Column("snapshot", JSONB(), nullable=False),
        sa.Column(
            "source_message_id",
            sa.Uuid(),
            sa.ForeignKey("messages.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "memory_versions_source_message_id_idx", "memory_versions", ["source_message_id"]
    )
    for table in ("memory_proposals", "memory_extraction_jobs"):
        common = [
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column(
                "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
            ),
            sa.Column("project_id", sa.Uuid(), nullable=True),
            sa.Column(
                "source_message_id",
                sa.Uuid(),
                sa.ForeignKey("messages.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("status", sa.String(16), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(
                ["project_id", "user_id"],
                ["projects.id", "projects.user_id"],
                deferrable=True,
                initially="DEFERRED",
            ),
        ]
        fields = (
            [
                sa.Column(
                    "target_id",
                    sa.Uuid(),
                    sa.ForeignKey("memory_items.id", ondelete="CASCADE"),
                    nullable=True,
                ),
                sa.Column("target_revision", sa.Integer(), nullable=True),
                sa.Column("action", sa.String(12), nullable=False),
                sa.Column("payload", JSONB(), nullable=False),
                sa.Column("reason", sa.String(500), nullable=False),
                sa.Column("quote", sa.Text(), nullable=False),
                sa.Column("content_hash", sa.String(64), nullable=False),
                sa.Column("revision", sa.Integer(), nullable=False),
                sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            ]
            if table == "memory_proposals"
            else [
                sa.Column("settings_revision", sa.Integer(), nullable=False),
                sa.Column("configuration", JSONB(), nullable=False),
                sa.Column("attempts", sa.Integer(), nullable=False),
                sa.Column("result_count", sa.Integer(), nullable=False),
                sa.Column("error", sa.String(160), nullable=True),
                sa.Column("usage", JSONB(), nullable=True),
                sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
                sa.UniqueConstraint("source_message_id"),
            ]
        )
        op.create_table(table, *common, *fields)
    op.create_index(
        "memory_proposals_scope_idx", "memory_proposals", ["user_id", "project_id", "status"]
    )
    op.create_index(
        "memory_proposals_source_message_id_idx", "memory_proposals", ["source_message_id"]
    )
    op.create_index("memory_proposals_target_id_idx", "memory_proposals", ["target_id"])
    op.create_index(
        "memory_extraction_jobs_dispatch_idx", "memory_extraction_jobs", ["status", "created_at"]
    )
    op.create_index(
        "memory_extraction_jobs_scope_idx", "memory_extraction_jobs", ["user_id", "project_id"]
    )


def downgrade():
    op.drop_table("memory_extraction_jobs")
    op.drop_table("memory_proposals")
    op.drop_table("memory_versions")
    for name in (
        "expires_on",
        "archived_at",
        "embedding",
        "embedding_revision",
        "embedding_model",
        "index_attempts",
    ):
        op.drop_column("memory_items", name)
    for name in ("auto_extract", "semantic_recall", "extraction_model"):
        op.drop_column("memory_preferences", name)
