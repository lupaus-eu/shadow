"""Add subscription access projection.

Revision ID: 0015
Revises: 0014
"""
from alembic import op
import sqlalchemy as sa
revision = "0015"; down_revision = "0014"; branch_labels = None; depends_on = None
def upgrade() -> None:
    op.add_column("organizations", sa.Column("subscription_access_state", sa.String(30), server_default="active", nullable=False))
    op.add_column("organizations", sa.Column("grace_expires_at", sa.DateTime(timezone=True)))
def downgrade() -> None:
    op.drop_column("organizations", "grace_expires_at"); op.drop_column("organizations", "subscription_access_state")
