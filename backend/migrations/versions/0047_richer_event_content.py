"""Richer Event content (Yearclock V2, P11 tickets 01-03; ADR-0033).

Events and Series gain a location, a list of titled links (replacing the single
link), a description format, and an optional start and end time. Each existing
link becomes a one-link list titled with its host name, and Occurrence
overrides keyed ``external_url`` are rewritten to ``links``. Old Event Revision
snapshots keep their ``external_url`` key; readers map it to ``links``.

Revision ID: 0047
Revises: 0046
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "0047"
down_revision = "0046"
branch_labels = None
depends_on = None

HOST = "COALESCE(substring({url} from '^https?://([^/:?#]+)'), {url})"


def upgrade() -> None:
    for table in ("events", "event_series"):
        op.add_column(table, sa.Column("location", sa.String(length=200)))
        op.add_column(table, sa.Column("links", postgresql.JSONB(), server_default="[]", nullable=False))
        op.add_column(table, sa.Column("description_format", sa.String(length=10), server_default="plain", nullable=False))
        op.add_column(table, sa.Column("starts_at", sa.Time()))
        op.add_column(table, sa.Column("ends_at", sa.Time()))
        op.create_check_constraint(f"ck_{table}_description_format", table, "description_format IN ('plain', 'markdown')")
        op.create_check_constraint(f"ck_{table}_links_list", table, "jsonb_typeof(links) = 'array'")
        op.create_check_constraint(f"ck_{table}_end_time_needs_start", table, "ends_at IS NULL OR starts_at IS NOT NULL")
        op.execute(f"UPDATE {table} SET links = jsonb_build_array(jsonb_build_object('title', left({HOST.format(url='external_url')}, 100), 'url', external_url)) WHERE external_url IS NOT NULL AND external_url <> ''")
        op.drop_column(table, "external_url")
    op.execute(
        f"""
        UPDATE series_occurrences SET overrides = (overrides - 'external_url') || jsonb_build_object('links',
            CASE WHEN jsonb_typeof(overrides->'external_url') <> 'string' OR overrides->>'external_url' = '' THEN '[]'::jsonb
            ELSE jsonb_build_array(jsonb_build_object('title', left({HOST.format(url="(overrides->>'external_url')")}, 100), 'url', overrides->>'external_url')) END)
        WHERE overrides ? 'external_url'
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE series_occurrences SET overrides = (overrides - 'links') || jsonb_build_object('external_url',
            CASE WHEN jsonb_array_length(overrides->'links') = 0 THEN 'null'::jsonb ELSE to_jsonb(overrides->'links'->0->>'url') END)
        WHERE overrides ? 'links'
        """
    )
    for table in ("events", "event_series"):
        op.add_column(table, sa.Column("external_url", sa.String(length=2048)))
        op.execute(f"UPDATE {table} SET external_url = links->0->>'url' WHERE jsonb_array_length(links) > 0")
        for constraint in ("end_time_needs_start", "links_list", "description_format"):
            op.drop_constraint(f"ck_{table}_{constraint}", table, type_="check")
        for column in ("ends_at", "starts_at", "description_format", "links", "location"):
            op.drop_column(table, column)
