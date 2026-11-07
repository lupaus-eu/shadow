"""A content-free record of every MCP tool call (ADR-0047).

One row per call: who (the person and the agent program), where, which tool, whether it
read or wrote, the outcome and how long it took. No arguments and no results. The table is
append-only for the application except that the retention job may delete successful read
calls. Writes keep their own Audit Events as well.

Revision ID: 0059
Revises: 0058
"""

import sqlalchemy as sa
from alembic import op


revision = "0059"
down_revision = "0058"
branch_labels = None
depends_on = None

CURRENT_ORGANIZATION = "NULLIF(current_setting('app.current_organization_id', true), '')::uuid"
CLEANUP_SCOPE = "current_setting('app.worker_scope', true) = 'mcp_read_log'"


def upgrade() -> None:
    op.create_table(
        "mcp_calls",
        sa.Column("id", sa.Uuid(), primary_key=True),
        # Null when the call named no Organization or the person is not a member of it.
        sa.Column("organization_id", sa.Uuid(), nullable=True),
        sa.Column("user_account_id", sa.Uuid(), nullable=False),
        sa.Column("mcp_client", sa.String(length=200), nullable=False),
        sa.Column("tool", sa.String(length=80), nullable=False),
        sa.Column("kind", sa.String(length=5), nullable=False),
        sa.Column("outcome", sa.String(length=7), nullable=False),
        sa.Column("reason", sa.String(length=40), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("kind IN ('read', 'write')", name="ck_mcp_calls_kind"),
        sa.CheckConstraint("outcome IN ('ok', 'refused', 'error')", name="ck_mcp_calls_outcome"),
    )
    op.create_index("ix_mcp_calls_organization_occurred", "mcp_calls", ["organization_id", sa.text("occurred_at DESC")])
    op.execute("GRANT SELECT, INSERT, DELETE ON mcp_calls TO shadow_app")
    op.execute("ALTER TABLE mcp_calls ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE mcp_calls FORCE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY mcp_calls_select ON mcp_calls FOR SELECT USING (organization_id = {CURRENT_ORGANIZATION})")
    op.execute(f"CREATE POLICY mcp_calls_insert ON mcp_calls FOR INSERT WITH CHECK (organization_id IS NOT DISTINCT FROM {CURRENT_ORGANIZATION})")
    op.execute(f"CREATE POLICY mcp_calls_cleanup ON mcp_calls FOR DELETE USING (organization_id = {CURRENT_ORGANIZATION} AND {CLEANUP_SCOPE} AND kind = 'read' AND outcome = 'ok')")
    op.execute("CREATE POLICY mcp_calls_support_select ON mcp_calls AS RESTRICTIVE FOR SELECT USING (app_support_grant_allows(false))")


def downgrade() -> None:
    op.drop_table("mcp_calls")
