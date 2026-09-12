"""Persist optional document scope; null retains whole-base retrieval."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

from alembic import op

revision = "0030_literature_scope"
down_revision = "0029_reliable_knowledge"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "conversations",
        sa.Column("active_knowledge_document_ids", pg.JSONB(none_as_null=True), nullable=True),
    )


def downgrade():
    op.drop_column("conversations", "active_knowledge_document_ids")
