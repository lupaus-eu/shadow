"""Organization-wide Labels (Yearclock V2, P2 ticket 02).

Labels belong to an Organization and are unique by name ignoring case. They
follow the content-table rules: the Organization policy, the live-Organization
check (migration 0028), and the Support Access check (migration 0027).

Revision ID: 0031
Revises: 0030
"""

import sqlalchemy as sa
from alembic import op


revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None

CURRENT_ORGANIZATION = "NULLIF(current_setting('app.current_organization_id', true), '')::uuid"


def upgrade() -> None:
    op.create_table(
        "labels",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("name", sa.String(length=60), nullable=False),
        sa.Column("color", sa.String(length=7), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("color ~ '^#[0-9a-f]{6}$'", name="ck_labels_color"),
        sa.CheckConstraint("length(btrim(name)) > 0", name="ck_labels_name"),
    )
    op.execute("CREATE UNIQUE INDEX uq_labels_organization_name ON labels (organization_id, lower(name))")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON labels TO shadow_app")
    op.execute("ALTER TABLE labels ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE labels FORCE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY labels_policy ON labels USING (organization_id = {CURRENT_ORGANIZATION}) WITH CHECK (organization_id = {CURRENT_ORGANIZATION})")
    op.execute("CREATE POLICY labels_live_organization ON labels AS RESTRICTIVE USING (app_organization_live(organization_id)) WITH CHECK (app_organization_live(organization_id))")
    op.execute("CREATE POLICY labels_support_select ON labels AS RESTRICTIVE FOR SELECT USING (app_support_grant_allows(false))")
    op.execute("CREATE POLICY labels_support_insert ON labels AS RESTRICTIVE FOR INSERT WITH CHECK (app_support_grant_allows(true))")
    op.execute("CREATE POLICY labels_support_update ON labels AS RESTRICTIVE FOR UPDATE USING (app_support_grant_allows(true)) WITH CHECK (app_support_grant_allows(true))")
    op.execute("CREATE POLICY labels_support_delete ON labels AS RESTRICTIVE FOR DELETE USING (app_support_grant_allows(true))")


def downgrade() -> None:
    op.drop_table("labels")
