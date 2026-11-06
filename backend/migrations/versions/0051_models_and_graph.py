"""Models and their graph: node types, connection types, nodes, and connections.

A Model is a digital twin of one organisation, owned by an Organization (the paying
account). Every table carries ``organization_id`` and the content-table rules: the
Organization policy, the live-Organization check (0028), and the Support Access check (0027).

Revision ID: 0051
Revises: 0050
"""

import sqlalchemy as sa
from alembic import op


revision = "0051"
down_revision = "0050"
branch_labels = None
depends_on = None

CURRENT_ORGANIZATION = "NULLIF(current_setting('app.current_organization_id', true), '')::uuid"
TABLES = ("models", "node_types", "connection_types", "allowed_connections", "nodes", "connections")


def _organization() -> sa.Column:
    return sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)


def _model() -> sa.Column:
    return sa.Column("model_id", sa.Uuid(), nullable=False, index=True)


def _model_fk() -> sa.ForeignKeyConstraint:
    """The Model must belong to the same Organization as the row (foreign keys ignore row-level security)."""
    return sa.ForeignKeyConstraint(["model_id", "organization_id"], ["models.id", "models.organization_id"], ondelete="CASCADE")


def _created() -> sa.Column:
    return sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)


def _version() -> sa.Column:
    return sa.Column("version", sa.Integer(), server_default="1", nullable=False)


def upgrade() -> None:
    op.create_table(
        "models",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _organization(),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        _version(),
        _created(),
        sa.UniqueConstraint("id", "organization_id", name="uq_models_id_organization"),
        sa.CheckConstraint("length(btrim(name)) > 0", name="ck_models_name"),
    )
    op.execute("CREATE UNIQUE INDEX uq_models_organization_name ON models (organization_id, lower(name))")
    op.create_table(
        "node_types",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _organization(),
        _model(),
        sa.Column("key", sa.String(length=60), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("color", sa.String(length=7), nullable=False),
        sa.Column("shape", sa.String(length=20), server_default="rectangle", nullable=False),
        _version(),
        _model_fk(),
        sa.UniqueConstraint("model_id", "key", name="uq_node_types_model_key"),
        sa.UniqueConstraint("id", "model_id", name="uq_node_types_id_model"),
        sa.CheckConstraint("color ~ '^#[0-9A-Fa-f]{6}$'", name="ck_node_types_color"),
    )
    op.create_table(
        "connection_types",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _organization(),
        _model(),
        sa.Column("key", sa.String(length=60), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("style", sa.String(length=20), server_default="solid", nullable=False),
        sa.Column("source_end", sa.String(length=20), server_default="none", nullable=False),
        sa.Column("target_end", sa.String(length=20), server_default="arrow", nullable=False),
        _version(),
        _model_fk(),
        sa.UniqueConstraint("model_id", "key", name="uq_connection_types_model_key"),
        sa.UniqueConstraint("id", "model_id", name="uq_connection_types_id_model"),
    )
    op.create_table(
        "allowed_connections",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _organization(),
        _model(),
        sa.Column("connection_type_id", sa.Uuid(), nullable=False),
        sa.Column("source_node_type_id", sa.Uuid(), nullable=False),
        sa.Column("target_node_type_id", sa.Uuid(), nullable=False),
        _model_fk(),
        sa.ForeignKeyConstraint(["connection_type_id", "model_id"], ["connection_types.id", "connection_types.model_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_node_type_id", "model_id"], ["node_types.id", "node_types.model_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_node_type_id", "model_id"], ["node_types.id", "node_types.model_id"], ondelete="CASCADE"),
        sa.UniqueConstraint("connection_type_id", "source_node_type_id", "target_node_type_id", name="uq_allowed_connections"),
    )
    op.create_table(
        "nodes",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _organization(),
        _model(),
        sa.Column("node_type_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("x", sa.Float(), server_default="0", nullable=False),
        sa.Column("y", sa.Float(), server_default="0", nullable=False),
        _version(),
        _created(),
        _model_fk(),
        sa.ForeignKeyConstraint(["node_type_id", "model_id"], ["node_types.id", "node_types.model_id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("id", "model_id", name="uq_nodes_id_model"),
        sa.CheckConstraint("length(btrim(name)) > 0", name="ck_nodes_name"),
    )
    op.create_table(
        "connections",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _organization(),
        _model(),
        sa.Column("connection_type_id", sa.Uuid(), nullable=False),
        sa.Column("source_node_id", sa.Uuid(), nullable=False),
        sa.Column("target_node_id", sa.Uuid(), nullable=False),
        _version(),
        _created(),
        _model_fk(),
        sa.ForeignKeyConstraint(["connection_type_id", "model_id"], ["connection_types.id", "connection_types.model_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["source_node_id", "model_id"], ["nodes.id", "nodes.model_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_node_id", "model_id"], ["nodes.id", "nodes.model_id"], ondelete="CASCADE"),
        sa.UniqueConstraint("connection_type_id", "source_node_id", "target_node_id", name="uq_connections_triple"),
        sa.CheckConstraint("source_node_id <> target_node_id", name="ck_connections_no_loop"),
    )
    for table in TABLES:
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO shadow_app")
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY {table}_policy ON {table} USING (organization_id = {CURRENT_ORGANIZATION}) WITH CHECK (organization_id = {CURRENT_ORGANIZATION})")
        op.execute(f"CREATE POLICY {table}_live_organization ON {table} AS RESTRICTIVE USING (app_organization_live(organization_id)) WITH CHECK (app_organization_live(organization_id))")
        op.execute(f"CREATE POLICY {table}_support_select ON {table} AS RESTRICTIVE FOR SELECT USING (app_support_grant_allows(false))")
        op.execute(f"CREATE POLICY {table}_support_insert ON {table} AS RESTRICTIVE FOR INSERT WITH CHECK (app_support_grant_allows(true))")
        op.execute(f"CREATE POLICY {table}_support_update ON {table} AS RESTRICTIVE FOR UPDATE USING (app_support_grant_allows(true)) WITH CHECK (app_support_grant_allows(true))")
        op.execute(f"CREATE POLICY {table}_support_delete ON {table} AS RESTRICTIVE FOR DELETE USING (app_support_grant_allows(true))")


def downgrade() -> None:
    for table in reversed(TABLES):
        op.drop_table(table)
