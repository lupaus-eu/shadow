"""Previous Visit (Yearclock V2, P4 ticket 04).

Each visit moves the last visit time into ``previous_visited_at``, which sets
which changes by others are marked as new to that user.

Revision ID: 0040
Revises: 0039
"""

import sqlalchemy as sa
from alembic import op


revision = "0040"
down_revision = "0039"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("yearclock_visits", sa.Column("previous_visited_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("yearclock_visits", "previous_visited_at")
