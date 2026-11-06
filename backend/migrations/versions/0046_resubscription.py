"""Resubscription (Yearclock V2, P14 ticket 02; ADR-0032).

An Organization whose subscription has ended can take a new one. The old
subscription ids are kept so late events of an old subscription are
recognised, and the Checkout session of a started resubscription is stored so
only its payment confirmation counts.

Revision ID: 0046
Revises: 0045
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "0046"
down_revision = "0045"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("organizations", sa.Column("previous_subscription_ids", postgresql.ARRAY(sa.String(length=255)), server_default="{}", nullable=False))
    op.add_column("organizations", sa.Column("resubscribe_checkout_session_id", sa.String(length=255)))


def downgrade() -> None:
    op.drop_column("organizations", "resubscribe_checkout_session_id")
    op.drop_column("organizations", "previous_subscription_ids")
