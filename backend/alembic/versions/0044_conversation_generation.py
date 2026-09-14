"""Persist requested generation overrides on each conversation."""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "0044_conversation_generation"
down_revision = "0043_durable_chat"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "conversations",
        sa.Column("generation_options", JSONB(), nullable=False, server_default="{}"),
    )


def downgrade():
    op.drop_column("conversations", "generation_options")
