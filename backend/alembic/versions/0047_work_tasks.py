"""Source-backed work goals, revision fences and durable execution ledger."""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

revision = "0047_work_tasks"
down_revision = "0046_conversation_context"
branch_labels = None
depends_on = None


def timestamps():
    return [
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
    ]


def upgrade():
    op.create_table(
        "work_tasks",
        sa.Column("id", UUID(), primary_key=True),
        sa.Column("user_id", UUID(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", UUID()),
        sa.Column("title", sa.String(80), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("event_seq", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(
            ["project_id", "user_id"], ["projects.id", "projects.user_id"], ondelete="CASCADE"
        ),
        sa.CheckConstraint("revision > 0 AND event_seq >= 0", name="work_tasks_version_valid"),
        sa.CheckConstraint(
            "status IN ('active', 'paused', 'cancelled', 'completed')",
            name="work_tasks_status_valid",
        ),
        *timestamps(),
    )
    op.create_index("work_tasks_scope_idx", "work_tasks", ["user_id", "project_id", "updated_at"])
    op.create_table(
        "work_task_revisions",
        sa.Column(
            "task_id", UUID(), sa.ForeignKey("work_tasks.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column("revision", sa.Integer(), primary_key=True),
        sa.Column("source_message_id", UUID(), sa.ForeignKey("messages.id", ondelete="SET NULL")),
        sa.Column("source_hash", sa.String(64), nullable=False),
        sa.Column("replaces", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "work_task_conversations",
        sa.Column(
            "task_id", UUID(), sa.ForeignKey("work_tasks.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column(
            "conversation_id",
            UUID(),
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )
    op.create_table(
        "work_steps",
        sa.Column("id", UUID(), primary_key=True),
        sa.Column(
            "task_id", UUID(), sa.ForeignKey("work_tasks.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column(
            "run_id", UUID(), sa.ForeignKey("agent_runs.id", ondelete="SET NULL"), unique=True
        ),
        sa.Column("action", sa.String(16), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="queued"),
        sa.Column("phase", sa.String(160), nullable=False, server_default="等待执行"),
        sa.Column("result_hash", sa.String(64)),
        *timestamps(),
    )
    op.create_index("work_steps_task_idx", "work_steps", ["task_id", "created_at"])
    op.create_table(
        "work_task_events",
        sa.Column(
            "task_id", UUID(), sa.ForeignKey("work_tasks.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column("seq", sa.Integer(), primary_key=True),
        sa.Column("operation_id", UUID(), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("data", JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("task_id", "operation_id"),
    )
    # Default projects use NULL. IS NOT DISTINCT FROM also checks that scope.
    op.execute("""
    CREATE FUNCTION check_work_task_scope() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE owner_id uuid; project uuid; valid boolean;
    BEGIN
      SELECT user_id, project_id INTO owner_id, project FROM work_tasks WHERE id=NEW.task_id;
      IF TG_TABLE_NAME = 'work_task_conversations' THEN
        SELECT EXISTS(SELECT 1 FROM conversations WHERE id=NEW.conversation_id
          AND user_id=owner_id AND project_id IS NOT DISTINCT FROM project) INTO valid;
      ELSIF TG_TABLE_NAME = 'work_steps' THEN
        IF NEW.run_id IS NULL THEN RETURN NEW; END IF;
        SELECT EXISTS(SELECT 1 FROM agent_runs WHERE id=NEW.run_id
          AND user_id=owner_id AND project_id IS NOT DISTINCT FROM project) INTO valid;
      ELSE
        IF NEW.source_message_id IS NULL THEN RETURN NEW; END IF;
        SELECT EXISTS(SELECT 1 FROM messages m JOIN conversations c ON c.id=m.conversation_id
          WHERE m.id=NEW.source_message_id AND m.role='user'
          AND c.user_id=owner_id AND c.project_id IS NOT DISTINCT FROM project) INTO valid;
      END IF;
      IF NOT valid THEN RAISE EXCEPTION 'work task scope mismatch' USING ERRCODE='23514'; END IF;
      RETURN NEW;
    END $$;
    """)
    for table in ("work_task_conversations", "work_steps", "work_task_revisions"):
        op.execute(
            f"CREATE TRIGGER {table}_scope BEFORE INSERT OR UPDATE ON {table} FOR EACH ROW EXECUTE FUNCTION check_work_task_scope()"
        )


def downgrade():
    for table in ("work_task_conversations", "work_steps", "work_task_revisions"):
        op.execute(f"DROP TRIGGER IF EXISTS {table}_scope ON {table}")
    op.execute("DROP FUNCTION IF EXISTS check_work_task_scope()")
    for table in (
        "work_task_events",
        "work_steps",
        "work_task_conversations",
        "work_task_revisions",
        "work_tasks",
    ):
        op.drop_table(table)
