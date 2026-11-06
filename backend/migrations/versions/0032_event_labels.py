"""Labels on Events (Yearclock V2, P2 ticket 03).

Assignments cascade away with their Event or Label and follow the
content-table RLS set (Organization, live Organization, Support Access).

Revision ID: 0032
Revises: 0031
"""

import sqlalchemy as sa
from alembic import op


revision = "0032"
down_revision = "0031"
branch_labels = None
depends_on = None

CURRENT_ORGANIZATION = "NULLIF(current_setting('app.current_organization_id', true), '')::uuid"


def upgrade() -> None:
    op.create_table(
        "event_labels",
        sa.Column("event_id", sa.Uuid(), sa.ForeignKey("events.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("label_id", sa.Uuid(), sa.ForeignKey("labels.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
    )
    op.create_index("ix_event_labels_label_id", "event_labels", ["label_id"])
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON event_labels TO yearclock_app")
    op.execute("ALTER TABLE event_labels ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE event_labels FORCE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY event_labels_policy ON event_labels USING (organization_id = {CURRENT_ORGANIZATION}) WITH CHECK (organization_id = {CURRENT_ORGANIZATION})")
    op.execute("CREATE POLICY event_labels_live_organization ON event_labels AS RESTRICTIVE USING (app_organization_live(organization_id)) WITH CHECK (app_organization_live(organization_id))")
    op.execute("CREATE POLICY event_labels_support_select ON event_labels AS RESTRICTIVE FOR SELECT USING (app_support_grant_allows(false))")
    op.execute("CREATE POLICY event_labels_support_insert ON event_labels AS RESTRICTIVE FOR INSERT WITH CHECK (app_support_grant_allows(true))")
    op.execute("CREATE POLICY event_labels_support_update ON event_labels AS RESTRICTIVE FOR UPDATE USING (app_support_grant_allows(true)) WITH CHECK (app_support_grant_allows(true))")
    op.execute("CREATE POLICY event_labels_support_delete ON event_labels AS RESTRICTIVE FOR DELETE USING (app_support_grant_allows(true))")


def downgrade() -> None:
    op.drop_table("event_labels")
