"""add users.magic_link_epoch — skipped (enable_email=false)

Revision ID: 0027_user_magic_link_epoch

No-op placeholder so the revision chain stays linear when email (and therefore
magic-link sign-in) is disabled.
"""

revision = "0027_user_magic_link_epoch"
# MCP is disabled in this deployment, so its optional 0026 revision is not
# generated. Keep the no-op placeholder attached to the last retained head.
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
