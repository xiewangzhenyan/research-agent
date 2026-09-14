"""Source-linked rolling conversation context and scoped history indexes."""

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID

from alembic import op

revision = "0046_conversation_context"
down_revision = "0045_mem0_memory"
branch_labels = None
depends_on = None


def timestamps():
    return [
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    ]


def upgrade():
    op.create_table(
        "conversation_context_jobs",
        sa.Column(
            "conversation_id",
            UUID(),
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("status", sa.String(16), nullable=False, server_default="queued"),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("cursor_at", sa.DateTime(timezone=True)),
        sa.Column("cursor_id", UUID()),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("configuration", JSONB(), nullable=False),
        *timestamps(),
    )
    op.create_table(
        "conversation_context_blocks",
        sa.Column("id", UUID(), primary_key=True),
        sa.Column(
            "conversation_id",
            UUID(),
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("through_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("through_id", UUID(), nullable=False),
        sa.Column("mode", sa.String(16), nullable=False),
        sa.Column("notes", JSONB(), nullable=False),
        sa.Column("terms", ARRAY(sa.Text()), nullable=False),
        sa.Column("usage", JSONB(), nullable=False),
        *timestamps(),
    )
    op.create_index(
        "conversation_context_scope_idx",
        "conversation_context_blocks",
        ["conversation_id", "through_at", "through_id"],
    )
    op.create_index(
        "conversation_context_terms_idx",
        "conversation_context_blocks",
        ["terms"],
        postgresql_using="gin",
    )
    op.create_table(
        "conversation_context_sources",
        sa.Column(
            "block_id",
            UUID(),
            sa.ForeignKey("conversation_context_blocks.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "message_id", UUID(), sa.ForeignKey("messages.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("embedding", Vector(512)),
        sa.Column("embedding_model", sa.String(100)),
    )
    op.create_index(
        "conversation_context_source_message_idx", "conversation_context_sources", ["message_id"]
    )
    op.create_index(
        "messages_context_order_idx", "messages", ["conversation_id", "created_at", "id"]
    )
    # Invalidate derived text at the DB boundary, including direct SQL changes.
    # New/streaming messages have no source links and do not reset completed work.
    op.execute("""
    CREATE FUNCTION invalidate_conversation_context() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF EXISTS (SELECT 1 FROM conversation_context_sources WHERE message_id = OLD.id) THEN
        DELETE FROM conversation_context_blocks WHERE conversation_id = OLD.conversation_id;
        UPDATE conversation_context_jobs SET cursor_at = NULL, cursor_id = NULL,
          revision = revision + 1, attempts = 0, status = 'queued', updated_at = now()
          WHERE conversation_id = OLD.conversation_id;
      END IF;
      IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
      RETURN NEW;
    END $$;
    CREATE TRIGGER invalidate_context_on_delete BEFORE DELETE ON messages
      FOR EACH ROW EXECUTE FUNCTION invalidate_conversation_context();
    CREATE TRIGGER invalidate_context_on_edit BEFORE UPDATE OF content, role, conversation_id, created_at ON messages
      FOR EACH ROW WHEN (OLD.content IS DISTINCT FROM NEW.content OR OLD.role IS DISTINCT FROM NEW.role OR OLD.conversation_id IS DISTINCT FROM NEW.conversation_id OR OLD.created_at IS DISTINCT FROM NEW.created_at)
      EXECUTE FUNCTION invalidate_conversation_context();
    """)


def downgrade():
    op.execute(
        "DROP TRIGGER invalidate_context_on_delete ON messages; DROP TRIGGER invalidate_context_on_edit ON messages; DROP FUNCTION invalidate_conversation_context()"
    )
    op.drop_index("messages_context_order_idx", table_name="messages")
    op.drop_table("conversation_context_sources")
    op.drop_table("conversation_context_blocks")
    op.drop_table("conversation_context_jobs")
