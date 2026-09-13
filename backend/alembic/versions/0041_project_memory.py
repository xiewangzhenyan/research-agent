"""Opt-in, human-confirmed memory per account and project."""

import sqlalchemy as sa

from alembic import op

revision = "0041_project_memory"
down_revision = "0040_project_spaces"
branch_labels = None
depends_on = None


def upgrade():
    for table in ("memory_preferences", "memory_items"):
        common = [
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column(
                "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
            ),
            sa.Column("project_id", sa.Uuid(), nullable=True),
            sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
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
                sa.Column("enabled", sa.Boolean(), nullable=False, server_default="false"),
                sa.UniqueConstraint("user_id", "project_id", postgresql_nulls_not_distinct=True),
            ]
            if table == "memory_preferences"
            else [
                sa.Column("title", sa.String(80), nullable=False),
                sa.Column("content", sa.Text(), nullable=False),
                sa.Column("kind", sa.String(20), nullable=False),
                sa.Column("pinned", sa.Boolean(), nullable=False, server_default="false"),
                sa.Column("content_hash", sa.String(64), nullable=False),
                sa.Column(
                    "source_message_id",
                    sa.Uuid(),
                    sa.ForeignKey("messages.id", ondelete="CASCADE"),
                    nullable=True,
                ),
                sa.UniqueConstraint(
                    "user_id", "project_id", "content_hash", postgresql_nulls_not_distinct=True
                ),
                sa.CheckConstraint(
                    "char_length(content) BETWEEN 1 AND 1200", name="bounded_memory_content"
                ),
            ]
        )
        op.create_table(table, *common, *fields)
    op.create_index("memory_items_scope_idx", "memory_items", ["user_id", "project_id"])
    op.create_index("memory_items_source_idx", "memory_items", ["source_message_id"])


def downgrade():
    op.drop_table("memory_items")
    op.drop_table("memory_preferences")
