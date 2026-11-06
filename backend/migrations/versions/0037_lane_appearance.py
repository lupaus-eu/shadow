"""Lane tint and height (Yearclock V2, P1 ticket 04).

Revision ID: 0037
Revises: 0036
"""

import sqlalchemy as sa
from alembic import op


revision = "0037"
down_revision = "0036"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("lanes", sa.Column("tint", sa.String(length=7), nullable=True))
    op.add_column("lanes", sa.Column("height", sa.String(length=10), server_default="normal", nullable=False))
    op.create_check_constraint("ck_lanes_tint", "lanes", "tint IS NULL OR tint ~ '^#[0-9a-f]{6}$'")
    op.create_check_constraint("ck_lanes_height", "lanes", "height IN ('normal', 'tall')")


def downgrade() -> None:
    op.drop_constraint("ck_lanes_height", "lanes", type_="check")
    op.drop_constraint("ck_lanes_tint", "lanes", type_="check")
    op.drop_column("lanes", "height")
    op.drop_column("lanes", "tint")
