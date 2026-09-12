"""Per-base processing settings and document index configuration snapshots."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

from alembic import op

revision = "0032_chunking_config"
down_revision = "0031_pdf_report"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "knowledge_bases",
        sa.Column(
            "chunking_config",
            pg.JSONB(),
            nullable=False,
            server_default='{"chunk_size": 450, "chunk_overlap": 65}',
        ),
    )
    op.add_column(
        "knowledge_documents",
        sa.Column("chunking_config", pg.JSONB(none_as_null=True), nullable=True),
    )
    # All earlier releases used these fixed values for ready documents.
    op.execute(
        "UPDATE knowledge_documents SET chunking_config = '{\"chunk_size\": 450,\"chunk_overlap\": 65}'::jsonb WHERE status = 'ready'"
    )


def downgrade():
    op.drop_column("knowledge_documents", "chunking_config")
    op.drop_column("knowledge_bases", "chunking_config")
