"""Add recurring Occurrence override state.

Revision ID: 0013
Revises: 0012
"""
from alembic import op
import sqlalchemy as sa
revision = "0013"; down_revision = "0012"; branch_labels = None; depends_on = None
def upgrade() -> None:
    op.add_column("series_occurrences", sa.Column("skipped", sa.Boolean(), server_default="false", nullable=False))
    op.add_column("series_occurrences", sa.Column("overridden_starts_on", sa.Date()))
    op.add_column("series_occurrences", sa.Column("overridden_title", sa.String(200)))
def downgrade() -> None:
    op.drop_column("series_occurrences", "overridden_title"); op.drop_column("series_occurrences", "overridden_starts_on"); op.drop_column("series_occurrences", "skipped")
