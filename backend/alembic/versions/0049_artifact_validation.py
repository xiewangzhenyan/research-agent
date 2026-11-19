"""Persist byte-bound structural checks without backfilling acceptance."""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "0049_artifact_validation"
down_revision = "0048_capability_assets"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "run_artifacts", sa.Column("validation", JSONB(), nullable=False, server_default="{}")
    )


def downgrade():
    op.drop_column("run_artifacts", "validation")
