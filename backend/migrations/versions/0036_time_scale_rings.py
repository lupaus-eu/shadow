"""Optional week and quarter rings (Yearclock V2, P1 ticket 03).

Revision ID: 0036
Revises: 0035
"""

import sqlalchemy as sa
from alembic import op


revision = "0036"
down_revision = "0035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("yearclocks", sa.Column("show_week_ring", sa.Boolean(), server_default=sa.false(), nullable=False))
    op.add_column("yearclocks", sa.Column("show_quarter_ring", sa.Boolean(), server_default=sa.false(), nullable=False))


def downgrade() -> None:
    op.drop_column("yearclocks", "show_quarter_ring")
    op.drop_column("yearclocks", "show_week_ring")
