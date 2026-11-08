"""Model timeline tables: lines, events, changes and node positions (ADR-0048).

A Model has one Base line and any number of Scenarios (``model_lines``). A line holds dated
events (``timeline_events``) and an event holds ordered changes (``event_changes``). Node
positions are stored per line and node (``node_positions``). Nothing reads these tables yet;
the version tables stay until the data is migrated.

Revision ID: 0060
Revises: 0059
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "0060"
down_revision = "0059"
branch_labels = None
depends_on = None

CURRENT_ORGANIZATION = "NULLIF(current_setting('app.current_organization_id', true), '')::uuid"
TABLES = ("model_lines", "timeline_events", "event_changes", "node_positions")
OPERATIONS = (
    "add_node", "remove_node", "update_node",
    "add_connection", "remove_connection", "reroute_connection", "change_connection_type",
)


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
    op.create_table(
        "model_lines",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("model_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("kind", sa.String(length=10), nullable=False),
        sa.Column("parent_line_id", sa.Uuid(), nullable=True),
        sa.Column("branch_event_id", sa.Uuid(), nullable=True),
        sa.Column("start_changed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_account_id", sa.Uuid(), nullable=True),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["model_id", "organization_id"], ["models.id", "models.organization_id"], ondelete="CASCADE"),
        sa.UniqueConstraint("id", "model_id", name="uq_model_lines_id_model"),
        sa.CheckConstraint("length(btrim(name)) > 0", name="ck_model_lines_name"),
        sa.CheckConstraint(
            "(kind = 'base' AND parent_line_id IS NULL AND branch_event_id IS NULL) "
            "OR (kind = 'scenario' AND parent_line_id IS NOT NULL AND branch_event_id IS NOT NULL)",
            name="ck_model_lines_kind",
        ),
    )
    op.create_foreign_key(
        "fk_model_lines_parent", "model_lines", "model_lines", ["parent_line_id", "model_id"], ["id", "model_id"], ondelete="RESTRICT",
    )
    op.execute("CREATE UNIQUE INDEX uq_model_lines_name ON model_lines (model_id, lower(name))")
    op.execute("CREATE UNIQUE INDEX uq_model_lines_base ON model_lines (model_id) WHERE kind = 'base'")

    op.create_table(
        "timeline_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("model_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("line_id", sa.Uuid(), nullable=False),
        sa.Column("occurred_on", sa.Date(), nullable=False),
        # Entry order: events on one date keep the order they were entered in.
        sa.Column("seq", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_by_user_account_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["line_id", "model_id"], ["model_lines.id", "model_lines.model_id"], ondelete="CASCADE"),
        sa.UniqueConstraint("id", "line_id", name="uq_timeline_events_id_line"),
        sa.CheckConstraint("length(btrim(title)) > 0", name="ck_timeline_events_title"),
    )
    op.create_index("ix_timeline_events_line_order", "timeline_events", ["line_id", "occurred_on", "seq"])
    # A branch point is an event of the parent line; the event cannot be deleted while a line branches from it.
    op.create_foreign_key(
        "fk_model_lines_branch_event", "model_lines", "timeline_events", ["branch_event_id", "parent_line_id"], ["id", "line_id"], ondelete="RESTRICT",
    )

    op.create_table(
        "event_changes",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("event_id", sa.Uuid(), sa.ForeignKey("timeline_events.id", ondelete="CASCADE"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("op", sa.String(length=30), nullable=False),
        sa.Column("element_id", sa.Uuid(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.UniqueConstraint("event_id", "position", name="uq_event_changes_event_position"),
        sa.CheckConstraint("op IN (" + ", ".join(f"'{name}'" for name in OPERATIONS) + ")", name="ck_event_changes_op"),
        sa.CheckConstraint("position >= 0", name="ck_event_changes_position"),
    )

    op.create_table(
        "node_positions",
        sa.Column("line_id", sa.Uuid(), nullable=False),
        sa.Column("node_id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("model_id", sa.Uuid(), nullable=False),
        sa.Column("x", sa.Float(), nullable=False),
        sa.Column("y", sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint("line_id", "node_id"),
        sa.ForeignKeyConstraint(["line_id", "model_id"], ["model_lines.id", "model_lines.model_id"], ondelete="CASCADE"),
    )
    for table in TABLES:
        _policies(table)


def downgrade() -> None:
    op.drop_table("node_positions")
    op.drop_table("event_changes")
    op.drop_constraint("fk_model_lines_branch_event", "model_lines", type_="foreignkey")
    op.drop_table("timeline_events")
    op.drop_table("model_lines")
