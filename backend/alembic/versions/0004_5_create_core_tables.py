"""create core tables (conversations, messages, chat_files, sessions, rag, channels)

Revision ID: 0004_5_core_tables
Revises: 0004_audit_log
Create Date: 2026-08-08T03:15:01.983441+00:00

Creates the core conversational, RAG, channel, and session tables that
later migrations modify (0005, 0006, 0007, 0009). Splits feature-flagged
groups so the schema only contains what was selected at generation time.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

from alembic import op

revision = "0004_5_core_tables"
down_revision = "0004_audit_log"
branch_labels = None
depends_on = None


def _id_col() -> sa.Column:
    return sa.Column(
        "id",
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )


def _user_fk(*, nullable: bool, ondelete: str = "CASCADE") -> sa.Column:
    return sa.Column(
        "user_id",
        PG_UUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete=ondelete),
        nullable=nullable,
    )


_UUID = PG_UUID(as_uuid=True)
_JSONB = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.create_table(
        "conversations",
        _id_col(),
        _user_fk(nullable=True),
        sa.Column("title", sa.String(255), nullable=True),
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_conversations_user_id", "conversations", ["user_id"])

    op.create_table(
        "messages",
        _id_col(),
        sa.Column(
            "conversation_id",
            _UUID,
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("model_name", sa.String(100), nullable=True),
        sa.Column("tokens_used", sa.Integer(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_messages_conversation_id", "messages", ["conversation_id"])

    op.create_table(
        "tool_calls",
        _id_col(),
        sa.Column(
            "message_id", _UUID, sa.ForeignKey("messages.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("tool_call_id", sa.String(100), nullable=False),
        sa.Column("tool_name", sa.String(100), nullable=False),
        sa.Column("args", _JSONB, nullable=False),
        sa.Column("result", sa.Text(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
    )
    op.create_index("ix_tool_calls_message_id", "tool_calls", ["message_id"])

    op.create_table(
        "chat_files",
        _id_col(),
        _user_fk(nullable=False),
        sa.Column(
            "message_id", _UUID, sa.ForeignKey("messages.id", ondelete="CASCADE"), nullable=True
        ),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("mime_type", sa.String(100), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("storage_path", sa.String(500), nullable=False),
        sa.Column("file_type", sa.String(20), nullable=False),
        sa.Column("parsed_content", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_chat_files_user_id", "chat_files", ["user_id"])

    op.create_table(
        "conversation_shares",
        _id_col(),
        sa.Column(
            "conversation_id",
            _UUID,
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "shared_by", _UUID, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "shared_with", _UUID, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True
        ),
        sa.Column("share_token", sa.String(64), nullable=True, unique=True),
        sa.Column("permission", sa.String(10), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("conversation_id", "shared_with", name="uq_share_conv_user"),
    )
    op.create_index(
        "ix_conversation_shares_conversation_id", "conversation_shares", ["conversation_id"]
    )
    op.create_index("ix_conversation_shares_shared_with", "conversation_shares", ["shared_with"])

    op.create_table(
        "message_ratings",
        _id_col(),
        sa.Column(
            "message_id", _UUID, sa.ForeignKey("messages.id", ondelete="CASCADE"), nullable=False
        ),
        _user_fk(nullable=False),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("rating IN (1, -1)", name="message_ratings_ck_rating_value_check"),
        sa.UniqueConstraint("message_id", "user_id", name="uq_message_user_rating"),
    )
    op.create_index("ix_message_ratings_message_id", "message_ratings", ["message_id"])
    op.create_index("ix_message_ratings_user_id", "message_ratings", ["user_id"])


def downgrade() -> None:
    op.drop_table("message_ratings")
    op.drop_table("conversation_shares")
    op.drop_table("chat_files")
    op.drop_table("tool_calls")
    op.drop_table("messages")
    op.drop_table("conversations")
