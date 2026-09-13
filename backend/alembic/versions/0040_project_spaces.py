"""Project isolation for conversations and tasks; KB ownership stays account-wide."""

import sqlalchemy as sa

from alembic import op

revision = "0040_project_spaces"
down_revision = "0039_run_artifacts"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "projects",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("description", sa.String(500), nullable=False, server_default=""),
        sa.Column(
            "knowledge_base_ids",
            sa.dialects.postgresql.JSONB(),
            nullable=False,
            server_default="[]",
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("id", "user_id", name="projects_id_user_key"),
    )
    op.create_index("ix_projects_user_id", "projects", ["user_id"])
    for table in ("conversations", "agent_runs"):
        op.add_column(table, sa.Column("project_id", sa.Uuid(), nullable=True))
        op.create_foreign_key(
            f"{table}_project_owner_fk",
            table,
            "projects",
            ["project_id", "user_id"],
            ["id", "user_id"],
            deferrable=True,
            initially="DEFERRED",
        )
        op.create_index(f"{table}_project_user_idx", table, ["user_id", "project_id"])


def downgrade():
    # Refuse to collapse named namespaces into the default namespace silently.
    connection = op.get_bind()
    for table in ("conversations", "agent_runs"):
        if connection.execute(
            sa.text(f"SELECT 1 FROM {table} WHERE project_id IS NOT NULL LIMIT 1")
        ).first():
            raise RuntimeError("Move or export project resources before downgrading")
    for table in ("agent_runs", "conversations"):
        op.drop_index(f"{table}_project_user_idx", table)
        op.drop_constraint(f"{table}_project_owner_fk", table, type_="foreignkey")
        op.drop_column(table, "project_id")
    op.drop_table("projects")
