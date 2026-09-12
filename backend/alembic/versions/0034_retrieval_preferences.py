"""Account-scoped retrieval defaults shared by testing and knowledge chat."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

from alembic import op

revision = "0034_retrieval_preferences"
down_revision = "0033_preview_config"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "knowledge_retrieval_preferences",
        sa.Column(
            "user_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("config", pg.JSONB(), nullable=False),
    )


def downgrade():
    op.drop_table("knowledge_retrieval_preferences")
