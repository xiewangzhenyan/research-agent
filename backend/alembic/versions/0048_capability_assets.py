"""MCP/Skill assets, immutable versions and account/project bindings."""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

revision = "0048_capability_assets"
down_revision = "0047_work_tasks"
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
        "capability_assets",
        sa.Column("id", UUID(), primary_key=True),
        sa.Column(
            "owner_id", UUID(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("project_id", UUID()),
        sa.Column("kind", sa.String(10), nullable=False),
        sa.Column("scope", sa.String(10), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.String(1200), nullable=False),
        sa.Column("tags", JSONB(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("config", JSONB(), nullable=False),
        sa.Column("secret", sa.Text()),
        sa.Column("catalog", JSONB(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("status_message", sa.String(400), nullable=False),
        sa.Column("tested_at", sa.String(40)),
        sa.Column("published_version", sa.Integer()),
        sa.UniqueConstraint("id", "owner_id", name="capability_asset_owner_key"),
        sa.ForeignKeyConstraint(
            ["project_id", "owner_id"], ["projects.id", "projects.user_id"], ondelete="CASCADE"
        ),
        *timestamps(),
    )
    op.create_index("capability_assets_owner_id_idx", "capability_assets", ["owner_id"])
    op.create_table(
        "skill_versions",
        sa.Column("id", UUID(), primary_key=True),
        sa.Column(
            "asset_id",
            UUID(),
            sa.ForeignKey("capability_assets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("manifest", JSONB(), nullable=False),
        sa.Column("files", JSONB(), nullable=False),
        sa.Column("digest", sa.String(64), nullable=False),
        sa.UniqueConstraint("asset_id", "number", name="skill_version_number_key"),
        *timestamps(),
    )
    op.create_index("skill_versions_asset_id_idx", "skill_versions", ["asset_id"])
    op.create_table(
        "capability_bindings",
        sa.Column("id", UUID(), primary_key=True),
        sa.Column("user_id", UUID(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("context_key", sa.String(40), nullable=False),
        sa.Column("agent_key", sa.String(40), nullable=False),
        sa.Column(
            "asset_id",
            UUID(),
            sa.ForeignKey("capability_assets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "user_id", "context_key", "agent_key", "asset_id", name="capability_binding_key"
        ),
        *timestamps(),
    )
    op.create_index("capability_bindings_user_id_idx", "capability_bindings", ["user_id"])
    op.create_index("capability_bindings_asset_id_idx", "capability_bindings", ["asset_id"])
    op.create_table(
        "capability_audit",
        sa.Column("id", UUID(), primary_key=True),
        sa.Column("user_id", UUID(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("asset_id", UUID(), sa.ForeignKey("capability_assets.id", ondelete="SET NULL")),
        sa.Column("action", sa.String(40), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("timestamp", sa.String(40), nullable=False),
    )
    op.create_index("capability_audit_user_id_idx", "capability_audit", ["user_id"])
    op.create_table(
        "capability_invocations",
        sa.Column(
            "run_id", UUID(), sa.ForeignKey("agent_runs.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column("fingerprint", sa.String(64), primary_key=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("result", JSONB()),
        *timestamps(),
    )


def downgrade():
    for table in (
        "capability_invocations",
        "capability_audit",
        "capability_bindings",
        "skill_versions",
        "capability_assets",
    ):
        op.drop_table(table)
