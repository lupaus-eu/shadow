"""Add recoverable Organization deletion state.

Revision ID: 0018
Revises: 0017
"""
from alembic import op
import sqlalchemy as sa
revision = "0018"; down_revision = "0017"; branch_labels = None; depends_on = None
def upgrade() -> None: op.add_column("organizations", sa.Column("deletion_requested_at", sa.DateTime(timezone=True)))
def downgrade() -> None: op.drop_column("organizations", "deletion_requested_at")
