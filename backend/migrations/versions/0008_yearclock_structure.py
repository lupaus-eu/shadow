"""Add Yearclock and Lane lifecycle versions.

Revision ID: 0008
Revises: 0007
"""
from alembic import op
import sqlalchemy as sa

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column("yearclocks", sa.Column("version", sa.Integer(), server_default="1", nullable=False))
    op.add_column("yearclocks", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("lanes", sa.Column("version", sa.Integer(), server_default="1", nullable=False))

def downgrade() -> None:
    op.drop_column("lanes", "version")
    op.drop_column("yearclocks", "archived_at")
    op.drop_column("yearclocks", "version")
