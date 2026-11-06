"""Drop the Yearclock product tables; the platform base keeps only platform tables.

Revision ID: 0050
Revises: 0049
"""

from collections.abc import Sequence

from alembic import op


revision: str = "0050"
down_revision: str | None = "0049"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DOMAIN_TABLES = (
    "event_revisions",
    "series_occurrences",
    "event_labels",
    "series_labels",
    "events",
    "event_series",
    "labels",
    "categories",
    "yearclock_visits",
    "yearclock_group_grants",
    "yearclock_access_grants",
    "invitation_groups",
    "member_group_members",
    "member_groups",
    "lanes",
    "yearclocks",
)


def upgrade() -> None:
    for table in DOMAIN_TABLES:
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")


def downgrade() -> None:
    raise NotImplementedError(
        "The Yearclock product tables are not restored; recreate the database from the base migrations of the product"
    )
