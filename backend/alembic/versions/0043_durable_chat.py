"""Attach durable executions to conversation turns.

Revision ID: 0043_durable_chat
Revises: 0042_memory_lifecycle
"""

import sqlalchemy as sa

from alembic import op

revision = "0043_durable_chat"
down_revision = "0042_memory_lifecycle"
branch_labels = None
depends_on = None


def upgrade():
    for name, target in (
        ("conversation_id", "conversations"),
        ("user_message_id", "messages"),
        ("assistant_message_id", "messages"),
    ):
        op.add_column("agent_runs", sa.Column(name, sa.Uuid(), nullable=True))
        op.create_foreign_key(
            f"agent_runs_{name}_fk", "agent_runs", target, [name], ["id"], ondelete="CASCADE"
        )
    op.create_index("ix_agent_runs_conversation_id", "agent_runs", ["conversation_id"])
    for name in ("user_message_id", "assistant_message_id"):
        op.create_unique_constraint(f"agent_runs_{name}_key", "agent_runs", [name])


def downgrade():
    for name in ("assistant_message_id", "user_message_id", "conversation_id"):
        op.drop_column("agent_runs", name)
