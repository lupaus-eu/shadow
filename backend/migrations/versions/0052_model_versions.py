"""Model versions: a baseline per Model and forked versions with their own graph.

A Version holds a complete graph (nodes and connections). The baseline is the Model's
current state; other versions are forked from a base version and record where each node
came from (``origin_node_id``), so the changes against the base can be listed.

Revision ID: 0052
Revises: 0051
"""

import sqlalchemy as sa
from alembic import op


revision = "0052"
down_revision = "0051"
branch_labels = None
depends_on = None

CURRENT_ORGANIZATION = "NULLIF(current_setting('app.current_organization_id', true), '')::uuid"


def upgrade() -> None:
    op.create_table(
        "model_versions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("model_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_baseline", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("base_version_id", sa.Uuid(), nullable=True),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["model_id", "organization_id"], ["models.id", "models.organization_id"], ondelete="CASCADE"),
        sa.UniqueConstraint("id", "model_id", name="uq_model_versions_id_model"),
        sa.CheckConstraint("length(btrim(name)) > 0", name="ck_model_versions_name"),
    )
    op.execute("CREATE UNIQUE INDEX uq_model_versions_name ON model_versions (model_id, lower(name))")
    op.execute("CREATE UNIQUE INDEX uq_model_versions_baseline ON model_versions (model_id) WHERE is_baseline")
    op.execute(
        "INSERT INTO model_versions (id, organization_id, model_id, name, is_baseline) "
        "SELECT gen_random_uuid(), organization_id, id, 'Baseline', true FROM models"
    )
    for table in ("nodes", "connections"):
        op.add_column(table, sa.Column("version_id", sa.Uuid(), nullable=True))
        op.execute(f"UPDATE {table} SET version_id = (SELECT v.id FROM model_versions v WHERE v.model_id = {table}.model_id AND v.is_baseline)")
        op.alter_column(table, "version_id", nullable=False)
        op.create_index(f"ix_{table}_version_id", table, ["version_id"])
        op.create_foreign_key(f"fk_{table}_version", table, "model_versions", ["version_id", "model_id"], ["id", "model_id"], ondelete="CASCADE")
    op.add_column("nodes", sa.Column("origin_node_id", sa.Uuid(), nullable=True))
    op.create_unique_constraint("uq_nodes_id_version", "nodes", ["id", "version_id"])
    # A connection joins two nodes of its own version.
    op.create_foreign_key("fk_connections_source_version", "connections", "nodes", ["source_node_id", "version_id"], ["id", "version_id"], ondelete="CASCADE")
    op.create_foreign_key("fk_connections_target_version", "connections", "nodes", ["target_node_id", "version_id"], ["id", "version_id"], ondelete="CASCADE")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON model_versions TO shadow_app")
    table = "model_versions"
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY {table}_policy ON {table} USING (organization_id = {CURRENT_ORGANIZATION}) WITH CHECK (organization_id = {CURRENT_ORGANIZATION})")
    op.execute(f"CREATE POLICY {table}_live_organization ON {table} AS RESTRICTIVE USING (app_organization_live(organization_id)) WITH CHECK (app_organization_live(organization_id))")
    op.execute(f"CREATE POLICY {table}_support_select ON {table} AS RESTRICTIVE FOR SELECT USING (app_support_grant_allows(false))")
    op.execute(f"CREATE POLICY {table}_support_insert ON {table} AS RESTRICTIVE FOR INSERT WITH CHECK (app_support_grant_allows(true))")
    op.execute(f"CREATE POLICY {table}_support_update ON {table} AS RESTRICTIVE FOR UPDATE USING (app_support_grant_allows(true)) WITH CHECK (app_support_grant_allows(true))")
    op.execute(f"CREATE POLICY {table}_support_delete ON {table} AS RESTRICTIVE FOR DELETE USING (app_support_grant_allows(true))")


def downgrade() -> None:
    op.drop_constraint("fk_connections_target_version", "connections", type_="foreignkey")
    op.drop_constraint("fk_connections_source_version", "connections", type_="foreignkey")
    op.drop_column("nodes", "origin_node_id")
    for table in ("connections", "nodes"):
        op.drop_column(table, "version_id")
    op.drop_table("model_versions")
