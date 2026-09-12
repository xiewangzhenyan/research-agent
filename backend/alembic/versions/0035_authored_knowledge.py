"""Editable native knowledge and FAQ, with optimistic content revisions."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

from alembic import op

revision = "0035_authored_knowledge"
down_revision = "0034_retrieval_preferences"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "knowledge_documents",
        sa.Column("source_kind", sa.String(16), nullable=False, server_default="file"),
    )
    op.add_column("knowledge_documents", sa.Column("source_data", pg.JSONB(), nullable=True))
    op.add_column(
        "knowledge_documents",
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
    )
    op.create_check_constraint(
        "knowledge_source_kind", "knowledge_documents", "source_kind IN ('file', 'manual', 'faq')"
    )


def downgrade():
    # Never discard user-authored sources as a side effect of rolling back schema.
    op.execute("LOCK TABLE knowledge_documents IN ACCESS EXCLUSIVE MODE")
    if op.get_bind().scalar(
        sa.text("SELECT count(*) FROM knowledge_documents WHERE source_kind <> 'file'")
    ):
        raise RuntimeError(
            "Cannot downgrade while authored knowledge exists; keep this schema and use a compatible application version"
        )
    op.drop_constraint("knowledge_source_kind", "knowledge_documents", type_="check")
    op.drop_column("knowledge_documents", "revision")
    op.drop_column("knowledge_documents", "source_data")
    op.drop_column("knowledge_documents", "source_kind")
