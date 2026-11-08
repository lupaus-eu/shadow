"""Metrics, metric values and simulations belong to a line: ``line_id`` required, ``version_id`` dropped.

Migration 0061 added a nullable ``line_id`` beside ``version_id`` (a line has the id of the version it
came from). The old routes kept writing only ``version_id``, so rows written after 0061 may lack a
``line_id``. This migration first fills it from ``version_id`` wherever a line with that id exists,
then removes what still has no line: rows of versions forked by the old fork route after 0061 (they
have no line), together with those versions and their graphs. Development databases only; nothing is
released. Afterwards ``line_id`` is ``NOT NULL`` and ``version_id`` is gone from ``metrics``,
``metric_values`` and ``simulations`` with the constraints that used it (the foreign keys to
``model_versions``, ``uq_metrics_version_key`` and ``uq_metrics_id_version``). ``metrics.node_id`` still
references ``nodes.id``; ticket 08 remaps it to element ids before ``nodes`` is dropped.

From now on the old fork route creates the Scenario line (same id as the new version) and copies the
metrics line by line, and deleting a version deletes its line.

Downgrade restores ``version_id`` from ``line_id`` (a line that has no version, that is a Scenario created
after this migration through the timeline routes, has no row to point to: its metrics, values and
simulations are deleted), makes ``line_id`` nullable again and recreates the old constraints.

Revision ID: 0062
Revises: 0061
"""

import sqlalchemy as sa
from alembic import op


revision = "0062"
down_revision = "0061"
branch_labels = None
depends_on = None

LINE_TABLES = ("metrics", "simulations")


def upgrade() -> None:
    # Rows written by the old routes after 0061: they belong to the line of the same id.
    for table in ("metrics", "simulations"):
        op.execute(f"UPDATE {table} SET line_id = version_id WHERE line_id IS NULL AND EXISTS (SELECT 1 FROM model_lines l WHERE l.id = {table}.version_id AND l.model_id = {table}.model_id)")
    op.execute("UPDATE metric_values SET line_id = version_id WHERE line_id IS NULL AND EXISTS (SELECT 1 FROM metrics m WHERE m.id = metric_values.metric_id AND m.line_id = metric_values.version_id)")
    # What is left has no line: versions forked after 0061 and their data (nodes, connections, metrics, simulations).
    op.execute("DELETE FROM metric_values WHERE line_id IS NULL")
    op.execute("DELETE FROM metrics WHERE line_id IS NULL")
    op.execute("DELETE FROM simulations WHERE line_id IS NULL")
    op.execute("DELETE FROM model_versions v WHERE NOT v.is_baseline AND NOT EXISTS (SELECT 1 FROM model_lines l WHERE l.id = v.id)")

    op.drop_constraint("metric_values_metric_id_version_id_fkey", "metric_values", type_="foreignkey")
    op.drop_constraint("metrics_version_id_model_id_fkey", "metrics", type_="foreignkey")
    op.drop_constraint("simulations_version_id_model_id_fkey", "simulations", type_="foreignkey")
    op.drop_constraint("uq_metrics_version_key", "metrics", type_="unique")
    op.drop_constraint("uq_metrics_id_version", "metrics", type_="unique")
    for table in (*LINE_TABLES, "metric_values"):
        op.alter_column(table, "line_id", nullable=False)
        op.drop_index(f"ix_{table}_version_id", table_name=table)
        op.drop_column(table, "version_id")


def downgrade() -> None:
    # A line without a version cannot be represented in the old schema.
    op.execute("DELETE FROM metric_values WHERE line_id NOT IN (SELECT id FROM model_versions)")
    op.execute("DELETE FROM metrics WHERE line_id NOT IN (SELECT id FROM model_versions)")
    op.execute("DELETE FROM simulations WHERE line_id NOT IN (SELECT id FROM model_versions)")
    for table in (*LINE_TABLES, "metric_values"):
        op.add_column(table, sa.Column("version_id", sa.Uuid(), nullable=True))
        op.execute(f"UPDATE {table} SET version_id = line_id")
        op.alter_column(table, "version_id", nullable=False)
        op.alter_column(table, "line_id", nullable=True)
        op.create_index(f"ix_{table}_version_id", table, ["version_id"])
    op.create_unique_constraint("uq_metrics_version_key", "metrics", ["version_id", "key"])
    op.create_unique_constraint("uq_metrics_id_version", "metrics", ["id", "version_id"])
    op.create_foreign_key("metrics_version_id_model_id_fkey", "metrics", "model_versions", ["version_id", "model_id"], ["id", "model_id"], ondelete="CASCADE")
    op.create_foreign_key("simulations_version_id_model_id_fkey", "simulations", "model_versions", ["version_id", "model_id"], ["id", "model_id"], ondelete="CASCADE")
    op.create_foreign_key("metric_values_metric_id_version_id_fkey", "metric_values", "metrics", ["metric_id", "version_id"], ["id", "version_id"], ondelete="CASCADE")
