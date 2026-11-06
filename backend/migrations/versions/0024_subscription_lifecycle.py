"""Project Stripe renewal and cancellation state onto Organizations.

Revision ID: 0024
Revises: 0023
"""

import sqlalchemy as sa
from alembic import op


revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("organizations", sa.Column("cancel_at_period_end", sa.Boolean(), server_default="false", nullable=False))
    op.add_column("organizations", sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True))
    op.add_column("organizations", sa.Column("subscription_event_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("organizations", "subscription_event_at")
    op.drop_column("organizations", "current_period_end")
    op.drop_column("organizations", "cancel_at_period_end")
