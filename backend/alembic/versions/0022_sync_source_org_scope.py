"""sync_source: add organization_id, make collection_name nullable

Revision ID: 0022
Revises: 0021_create_items
Create Date: 2026-06-21

SyncSource is now org-scoped. collection_name is nullable so an integration
can be created at org level before being assigned to a specific knowledge base.
"""

revision = "0022"
down_revision = "0018_user_slash_commands"
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
