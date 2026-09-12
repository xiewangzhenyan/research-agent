"""Keep the actual generation parameters with each answer."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

from alembic import op

revision = "0036_effective_model_config"
down_revision = "0035_authored_knowledge"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("messages", sa.Column("effective_config", pg.JSONB(), nullable=True))


def downgrade():
    op.drop_column("messages", "effective_config")
