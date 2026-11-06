"""Yearclock start month (Yearclock V2, P1 ticket 02).

The month a Yearclock's planning year begins; it sets the default Planning
Window. Existing Yearclocks start in January.

Revision ID: 0035
Revises: 0034
"""

import sqlalchemy as sa
from alembic import op


revision = "0035"
down_revision = "0034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("yearclocks", sa.Column("start_month", sa.SmallInteger(), server_default="1", nullable=False))
    op.create_check_constraint("ck_yearclocks_start_month", "yearclocks", "start_month BETWEEN 1 AND 12")


def downgrade() -> None:
    op.drop_constraint("ck_yearclocks_start_month", "yearclocks", type_="check")
    op.drop_column("yearclocks", "start_month")
