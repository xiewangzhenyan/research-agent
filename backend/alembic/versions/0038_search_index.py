"""Rebuildable pgvector and Chinese term index; preserve the legacy source store."""

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql as pg

from alembic import op

revision = "0038_search_index"
down_revision = "0037_agent_runs"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "knowledge_search_chunks",
        sa.Column(
            "chunk_id",
            sa.Uuid(),
            sa.ForeignKey("knowledge_chunks.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("generation_id", sa.Uuid(), nullable=False),
        sa.Column("model_fingerprint", sa.String(64), nullable=False),
        sa.Column("tokenizer_version", sa.String(100), nullable=False),
        sa.Column("source_hash", sa.String(32), nullable=False),
        sa.Column("embedding", Vector(512), nullable=False),
        sa.Column("terms", pg.JSONB(), nullable=False),
        sa.Column("term_list", pg.ARRAY(sa.String()), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.CheckConstraint("token_count >= 0", name="search_token_count_nonnegative"),
    )
    op.create_index(
        "knowledge_search_terms_gin",
        "knowledge_search_chunks",
        ["term_list"],
        postgresql_using="gin",
    )
    # Even an old worker or maintenance SQL cannot retain a stale index row.
    op.execute("""CREATE FUNCTION invalidate_knowledge_search() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN DELETE FROM knowledge_search_chunks WHERE chunk_id = OLD.id; RETURN NEW; END; $$""")
    op.execute("""CREATE TRIGGER knowledge_search_invalidate BEFORE UPDATE OF content, embedding, document_id
        ON knowledge_chunks FOR EACH ROW WHEN (OLD.content IS DISTINCT FROM NEW.content OR
        OLD.embedding IS DISTINCT FROM NEW.embedding OR OLD.document_id IS DISTINCT FROM NEW.document_id)
        EXECUTE FUNCTION invalidate_knowledge_search()""")


def downgrade():
    op.execute("DROP TRIGGER knowledge_search_invalidate ON knowledge_chunks")
    op.execute("DROP FUNCTION invalidate_knowledge_search()")
    op.drop_table("knowledge_search_chunks")
    # Extension can be shared by other objects; never DROP EXTENSION CASCADE.
