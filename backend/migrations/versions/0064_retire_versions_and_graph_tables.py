"""Retire the version tables: drop ``nodes``, ``connections`` and ``model_versions`` (ADR-0048, ADR-0050).

Nothing reads them any more: the graph of a line is the replay of its events, metrics, metric values and
simulations belong to a line (0062), ``metrics.node_id`` holds an element id without a foreign key to ``nodes``
(0063), and the version routes are gone. No other table references these three, so dropping them also drops
their indexes, constraints and row-level security policies. The old ``version_id`` and ``origin_node_id``
columns lived on these tables and go with them.

Downgrade recreates the three tables with their 0051/0052 structure, grants and policies. The timeline is the
source: ``model_versions`` is refilled from the lines (one version per line, with the line's id, name and
description; the Base line is the baseline; a Scenario's base version is its parent line) so the older
migrations still find a version for every line and keep their metrics and simulations, but ``nodes`` and
``connections`` come back **empty**. No graph is rebuilt from the events, planned-event dates and the history
are not in those tables, and a node tied to a metric loses that tie when 0063 is downgraded further.

Revision ID: 0064
Revises: 0063
"""

import sqlalchemy as sa
from alembic import op


revision = "0064"
down_revision = "0063"
branch_labels = None
depends_on = None

CURRENT_ORGANIZATION = "NULLIF(current_setting('app.current_organization_id', true), '')::uuid"
OLD_TABLES = ("nodes", "connections", "model_versions")


def _policies(table: str) -> None:
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO shadow_app")
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY {table}_policy ON {table} USING (organization_id = {CURRENT_ORGANIZATION}) WITH CHECK (organization_id = {CURRENT_ORGANIZATION})")
    op.execute(f"CREATE POLICY {table}_live_organization ON {table} AS RESTRICTIVE USING (app_organization_live(organization_id)) WITH CHECK (app_organization_live(organization_id))")
    op.execute(f"CREATE POLICY {table}_support_select ON {table} AS RESTRICTIVE FOR SELECT USING (app_support_grant_allows(false))")
    op.execute(f"CREATE POLICY {table}_support_insert ON {table} AS RESTRICTIVE FOR INSERT WITH CHECK (app_support_grant_allows(true))")
    op.execute(f"CREATE POLICY {table}_support_update ON {table} AS RESTRICTIVE FOR UPDATE USING (app_support_grant_allows(true)) WITH CHECK (app_support_grant_allows(true))")
    op.execute(f"CREATE POLICY {table}_support_delete ON {table} AS RESTRICTIVE FOR DELETE USING (app_support_grant_allows(true))")


def upgrade() -> None:
    op.drop_table("connections")
    op.drop_table("nodes")
    op.drop_table("model_versions")


def downgrade() -> None:
    organization = lambda: sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)  # noqa: E731
    model_fk = lambda: sa.ForeignKeyConstraint(["model_id", "organization_id"], ["models.id", "models.organization_id"], ondelete="CASCADE")  # noqa: E731
    created = lambda: sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)  # noqa: E731
    version = lambda: sa.Column("version", sa.Integer(), server_default="1", nullable=False)  # noqa: E731

    op.create_table(
        "model_versions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        organization(),
        sa.Column("model_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_baseline", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("base_version_id", sa.Uuid(), nullable=True),
        version(),
        created(),
        model_fk(),
        sa.UniqueConstraint("id", "model_id", name="uq_model_versions_id_model"),
        sa.CheckConstraint("length(btrim(name)) > 0", name="ck_model_versions_name"),
    )
    op.execute("CREATE UNIQUE INDEX uq_model_versions_name ON model_versions (model_id, lower(name))")
    op.execute("CREATE UNIQUE INDEX uq_model_versions_baseline ON model_versions (model_id) WHERE is_baseline")
    op.execute(
        "INSERT INTO model_versions (id, organization_id, model_id, name, description, is_baseline, base_version_id, version, created_at) "
        "SELECT id, organization_id, model_id, name, description, kind = 'base', parent_line_id, version, created_at FROM model_lines"
    )
    op.create_table(
        "nodes",
        sa.Column("id", sa.Uuid(), primary_key=True),
        organization(),
        sa.Column("model_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("version_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("origin_node_id", sa.Uuid(), nullable=True),
        sa.Column("node_type_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("x", sa.Float(), server_default="0", nullable=False),
        sa.Column("y", sa.Float(), server_default="0", nullable=False),
        version(),
        created(),
        model_fk(),
        sa.ForeignKeyConstraint(["node_type_id", "model_id"], ["node_types.id", "node_types.model_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["version_id", "model_id"], ["model_versions.id", "model_versions.model_id"], ondelete="CASCADE", name="fk_nodes_version"),
        sa.UniqueConstraint("id", "model_id", name="uq_nodes_id_model"),
        sa.UniqueConstraint("id", "version_id", name="uq_nodes_id_version"),
        sa.CheckConstraint("length(btrim(name)) > 0", name="ck_nodes_name"),
    )
    op.create_table(
        "connections",
        sa.Column("id", sa.Uuid(), primary_key=True),
        organization(),
        sa.Column("model_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("version_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("connection_type_id", sa.Uuid(), nullable=False),
        sa.Column("source_node_id", sa.Uuid(), nullable=False),
        sa.Column("target_node_id", sa.Uuid(), nullable=False),
        version(),
        created(),
        model_fk(),
        sa.ForeignKeyConstraint(["connection_type_id", "model_id"], ["connection_types.id", "connection_types.model_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["source_node_id", "model_id"], ["nodes.id", "nodes.model_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_node_id", "model_id"], ["nodes.id", "nodes.model_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["version_id", "model_id"], ["model_versions.id", "model_versions.model_id"], ondelete="CASCADE", name="fk_connections_version"),
        sa.ForeignKeyConstraint(["source_node_id", "version_id"], ["nodes.id", "nodes.version_id"], ondelete="CASCADE", name="fk_connections_source_version"),
        sa.ForeignKeyConstraint(["target_node_id", "version_id"], ["nodes.id", "nodes.version_id"], ondelete="CASCADE", name="fk_connections_target_version"),
        sa.UniqueConstraint("connection_type_id", "source_node_id", "target_node_id", name="uq_connections_triple"),
        sa.CheckConstraint("source_node_id <> target_node_id", name="ck_connections_no_loop"),
    )
    for table in OLD_TABLES:
        _policies(table)
