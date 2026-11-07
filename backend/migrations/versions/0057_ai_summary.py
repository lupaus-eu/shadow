"""A simulation may hold an AI-written summary of its analysis.

Revision ID: 0057
Revises: 0056
"""

import sqlalchemy as sa
from alembic import op


revision = "0057"
down_revision = "0056"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("simulations", sa.Column("ai_summary", sa.Text(), nullable=True))
    op.add_column("simulations", sa.Column("ai_generated_at", sa.DateTime(timezone=True), nullable=True))
