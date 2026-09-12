"""Durable account-owned background tasks (checkpoint setup is a separate command)."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

from alembic import op

revision = "0037_agent_runs"
down_revision = "0036_effective_model_config"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "agent_runs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("idempotency_key", sa.Uuid(), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("request", pg.JSONB(), nullable=False),
        sa.Column("effective_config", pg.JSONB(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("event_seq", sa.Integer(), nullable=False),
        sa.Column("result", pg.JSONB(), nullable=True),
        sa.Column("pending_input", pg.JSONB(), nullable=True),
        sa.Column("resume_input", pg.JSONB(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("user_id", "idempotency_key"),
    )
    op.create_index("agent_runs_user_id_idx", "agent_runs", ["user_id"])
    op.create_index("agent_runs_dispatch_idx", "agent_runs", ["status", "created_at"])
    op.create_table(
        "agent_run_events",
        sa.Column(
            "run_id",
            sa.Uuid(),
            sa.ForeignKey("agent_runs.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("seq", sa.Integer(), primary_key=True),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("data", pg.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade():
    op.drop_table("agent_run_events")
    op.drop_table("agent_runs")
