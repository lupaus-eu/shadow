"""Analysis summaries and proposals are written by agents through MCP, not by an LLM call.

Revision ID: 0058
Revises: 0057
"""

import sqlalchemy as sa
from alembic import op


revision = "0058"
down_revision = "0057"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # These proposals came from the removed server-side LLM call (ADR-0047).
    op.execute("DELETE FROM recommendations WHERE kind = 'ai'")
    op.alter_column("simulations", "ai_summary", new_column_name="analysis_summary")
    op.alter_column("simulations", "ai_generated_at", new_column_name="analysis_summary_at")
    op.add_column("simulations", sa.Column("analysis_summary_author", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("simulations", "analysis_summary_author")
    op.alter_column("simulations", "analysis_summary_at", new_column_name="ai_generated_at")
    op.alter_column("simulations", "analysis_summary", new_column_name="ai_summary")
