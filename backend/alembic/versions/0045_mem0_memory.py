"""Automatic Mem0 memory, preserving canonical facts and their existing versions."""

import sqlalchemy as sa

from alembic import op

revision = "0045_mem0_memory"
down_revision = "0044_conversation_generation"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "memory_items", sa.Column("origin", sa.String(16), nullable=False, server_default="manual")
    )
    op.add_column("memory_items", sa.Column("source_quote", sa.Text(), nullable=True))
    # Preserve the user's master switch. Enabling memory now includes automatic
    # organization; cancel old extraction attempts by invalidating their revision.
    op.execute("UPDATE memory_preferences SET auto_extract = enabled, revision = revision + 1")
    op.execute(
        "UPDATE memory_extraction_jobs SET status = 'cancelled', finished_at = CURRENT_TIMESTAMP WHERE status IN ('queued', 'running')"
    )
    # Legacy candidates are evidence only: never silently promote stale proposals.
    op.execute("UPDATE memory_proposals SET status = 'superseded' WHERE status = 'pending'")


def downgrade():
    # Downgrading must not leave an older worker auto-processing unreviewed jobs.
    op.execute("UPDATE memory_preferences SET auto_extract = false, revision = revision + 1")
    op.execute(
        "UPDATE memory_extraction_jobs SET status = 'cancelled', finished_at = CURRENT_TIMESTAMP WHERE status IN ('queued', 'running')"
    )
    op.drop_column("memory_items", "source_quote")
    op.drop_column("memory_items", "origin")
