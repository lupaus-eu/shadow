"""Store field-level Occurrence overrides and Series segments.

``series_occurrences.overrides`` maps each explicitly overridden field to its
value; a missing key means the field inherits from its Series. It replaces the
separate title and start-date override columns.

``event_series.effective_from`` is the first Series Date a segment owns. A
successor created by "This and future" keeps the original anchor
(``starts_on``) and starts owning dates from the split point.

Revision ID: 0022
Revises: 0021
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("series_occurrences", sa.Column("overrides", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False))
    op.execute(
        """
        UPDATE series_occurrences SET overrides =
            (CASE WHEN overridden_title IS NOT NULL THEN jsonb_build_object('title', overridden_title) ELSE '{}'::jsonb END)
            || (CASE WHEN overridden_starts_on IS NOT NULL THEN jsonb_build_object('starts_on', to_char(overridden_starts_on, 'YYYY-MM-DD')) ELSE '{}'::jsonb END)
        """
    )
    op.drop_column("series_occurrences", "overridden_title")
    op.drop_column("series_occurrences", "overridden_starts_on")
    op.add_column("event_series", sa.Column("effective_from", sa.Date(), nullable=True))
    op.execute("UPDATE event_series SET effective_from = starts_on")
    op.alter_column("event_series", "effective_from", nullable=False)
    op.add_column("event_series", sa.Column("version", sa.Integer(), server_default="1", nullable=False))


def downgrade() -> None:
    op.drop_column("event_series", "version")
    op.drop_column("event_series", "effective_from")
    op.add_column("series_occurrences", sa.Column("overridden_starts_on", sa.Date()))
    op.add_column("series_occurrences", sa.Column("overridden_title", sa.String(200)))
    op.execute(
        """
        UPDATE series_occurrences SET
            overridden_title = overrides->>'title',
            overridden_starts_on = (overrides->>'starts_on')::date
        """
    )
    op.drop_column("series_occurrences", "overrides")
