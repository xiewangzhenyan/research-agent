"""Native knowledge bases, documents and vector chunks."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

from alembic import op

revision = "0028_native_knowledge"
down_revision = "0027_user_magic_link_epoch"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "knowledge_bases",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
    )
    op.create_index("knowledge_bases_user_id_idx", "knowledge_bases", ["user_id"])
    op.create_table(
        "knowledge_documents",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "knowledge_base_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("knowledge_bases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("storage_path", sa.Text(), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("error", sa.Text()),
        sa.Column("chunk_count", sa.Integer(), nullable=False),
        sa.Column("embedding_model", sa.String(150)),
        sa.Column("job_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("processing_started_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("knowledge_base_id", "sha256"),
    )
    op.create_index(
        "knowledge_documents_knowledge_base_id_idx", "knowledge_documents", ["knowledge_base_id"]
    )
    op.create_index("knowledge_documents_status_idx", "knowledge_documents", ["status"])
    op.create_table(
        "knowledge_chunks",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "document_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("knowledge_documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("page", sa.Integer()),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding", pg.ARRAY(sa.Float()), nullable=False),
        sa.UniqueConstraint("document_id", "position"),
    )
    op.create_index("knowledge_chunks_document_id_idx", "knowledge_chunks", ["document_id"])


def downgrade():
    op.drop_table("knowledge_chunks")
    op.drop_table("knowledge_documents")
    op.drop_table("knowledge_bases")
