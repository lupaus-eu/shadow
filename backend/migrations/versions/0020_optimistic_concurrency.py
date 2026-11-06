"""Add versions to mutable access and membership records.

Revision ID: 0020
Revises: 0019
"""

import sqlalchemy as sa
from alembic import op


revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("organization_invitations", "organization_memberships", "yearclock_access_grants"):
        op.add_column(table, sa.Column("version", sa.Integer(), server_default="1", nullable=False))


def downgrade() -> None:
    for table in ("yearclock_access_grants", "organization_memberships", "organization_invitations"):
        op.drop_column(table, "version")
