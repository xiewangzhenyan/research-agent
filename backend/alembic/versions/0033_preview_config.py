"""Pin confirmed preview settings independently of actual completed index snapshots."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

from alembic import op

revision = "0033_preview_config"
down_revision = "0032_chunking_config"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "knowledge_documents",
        sa.Column("requested_chunking_config", pg.JSONB(none_as_null=True), nullable=True),
    )


def downgrade():
    op.drop_column("knowledge_documents", "requested_chunking_config")
