"""Bounded, account-owned sandbox artifacts."""

import sqlalchemy as sa

from alembic import op

revision = "0039_run_artifacts"
down_revision = "0038_search_index"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "run_artifacts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "run_id", sa.Uuid(), sa.ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("execution_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("mime_type", sa.String(80), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "size >= 0 AND size <= 2097152 AND octet_length(content) = size", name="bounded_content"
        ),
    )
    for field in ("run_id", "user_id", "execution_id"):
        op.create_index(f"run_artifacts_{field}_idx", "run_artifacts", [field])


def downgrade():
    op.drop_table("run_artifacts")
