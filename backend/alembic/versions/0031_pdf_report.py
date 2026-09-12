"""Store generation-specific PDF text extraction coverage."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

from alembic import op

revision = "0031_pdf_report"
down_revision = "0030_literature_scope"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "knowledge_documents", sa.Column("parse_report", pg.JSONB(none_as_null=True), nullable=True)
    )


def downgrade():
    op.drop_column("knowledge_documents", "parse_report")
