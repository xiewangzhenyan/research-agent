"""Conversation knowledge settings, locations and owned citations."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

from alembic import op

revision = "0029_reliable_knowledge"
down_revision = "0028_native_knowledge"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "conversations",
        sa.Column("active_knowledge_base_ids", pg.JSONB(), nullable=False, server_default="[]"),
    )
    op.add_column(
        "conversations",
        sa.Column("knowledge_strict", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "knowledge_chunks", sa.Column("location", pg.JSONB(), nullable=False, server_default="{}")
    )
    op.create_table(
        "knowledge_citations",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "message_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("messages.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "document_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("knowledge_documents.id", ondelete="SET NULL"),
        ),
        sa.Column("source", pg.JSONB(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
    )
    for column in ["user_id", "message_id", "document_id"]:
        op.create_index(f"ix_knowledge_citations_{column}", "knowledge_citations", [column])


def downgrade():
    op.drop_table("knowledge_citations")
    op.drop_column("knowledge_chunks", "location")
    op.drop_column("conversations", "knowledge_strict")
    op.drop_column("conversations", "active_knowledge_base_ids")
