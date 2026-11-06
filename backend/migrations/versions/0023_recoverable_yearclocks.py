"""Make Yearclock deletion recoverable.

Revision ID: 0023
Revises: 0022
"""

import sqlalchemy as sa
from alembic import op


revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("yearclocks", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_yearclocks_deleted_at", "yearclocks", ["deleted_at"])
    op.create_index("ix_events_deleted_at", "events", ["deleted_at"])


def downgrade() -> None:
    op.drop_index("ix_events_deleted_at", table_name="events")
    op.drop_index("ix_yearclocks_deleted_at", table_name="yearclocks")
    op.drop_column("yearclocks", "deleted_at")
