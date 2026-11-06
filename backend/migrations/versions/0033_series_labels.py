"""Labels on recurring Series (Yearclock V2, P2 ticket 04).

Every Series segment carries its own set. Rows cascade away with the Series
or the Label and follow the content-table RLS set (Organization, live
Organization, Support Access). Occurrence overrides keep their Labels in
``series_occurrences.overrides["label_ids"]``.

Revision ID: 0033
Revises: 0032
"""

import sqlalchemy as sa
from alembic import op


revision = "0033"
down_revision = "0032"
branch_labels = None
depends_on = None

CURRENT_ORGANIZATION = "NULLIF(current_setting('app.current_organization_id', true), '')::uuid"


def upgrade() -> None:
    op.create_table(
        "series_labels",
        sa.Column("series_id", sa.Uuid(), sa.ForeignKey("event_series.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("label_id", sa.Uuid(), sa.ForeignKey("labels.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
    )
    op.create_index("ix_series_labels_label_id", "series_labels", ["label_id"])
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON series_labels TO yearclock_app")
    op.execute("ALTER TABLE series_labels ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE series_labels FORCE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY series_labels_policy ON series_labels USING (organization_id = {CURRENT_ORGANIZATION}) WITH CHECK (organization_id = {CURRENT_ORGANIZATION})")
    op.execute("CREATE POLICY series_labels_live_organization ON series_labels AS RESTRICTIVE USING (app_organization_live(organization_id)) WITH CHECK (app_organization_live(organization_id))")
    op.execute("CREATE POLICY series_labels_support_select ON series_labels AS RESTRICTIVE FOR SELECT USING (app_support_grant_allows(false))")
    op.execute("CREATE POLICY series_labels_support_insert ON series_labels AS RESTRICTIVE FOR INSERT WITH CHECK (app_support_grant_allows(true))")
    op.execute("CREATE POLICY series_labels_support_update ON series_labels AS RESTRICTIVE FOR UPDATE USING (app_support_grant_allows(true)) WITH CHECK (app_support_grant_allows(true))")
    op.execute("CREATE POLICY series_labels_support_delete ON series_labels AS RESTRICTIVE FOR DELETE USING (app_support_grant_allows(true))")


def downgrade() -> None:
    op.drop_table("series_labels")
