"""Group grants (Yearclock V2, P10a ticket 04).

A Group's Editor or Viewer access to one Yearclock. Grants cascade with the
Yearclock and the Group and follow the Organization RLS set; Support Access
never reads them.

Revision ID: 0043
Revises: 0042
"""

import sqlalchemy as sa
from alembic import op


revision = "0043"
down_revision = "0042"
branch_labels = None
depends_on = None

CURRENT_ORGANIZATION = "NULLIF(current_setting('app.current_organization_id', true), '')::uuid"


def upgrade() -> None:
    op.create_table(
        "yearclock_group_grants",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("yearclock_id", sa.Uuid(), sa.ForeignKey("yearclocks.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("group_id", sa.Uuid(), sa.ForeignKey("member_groups.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("role", sa.String(length=10), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("role IN ('editor', 'viewer')", name="ck_yearclock_group_grants_role"),
        sa.UniqueConstraint("yearclock_id", "group_id", name="uq_yearclock_group_grants"),
    )
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON yearclock_group_grants TO shadow_app")
    op.execute("ALTER TABLE yearclock_group_grants ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE yearclock_group_grants FORCE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY yearclock_group_grants_policy ON yearclock_group_grants USING (organization_id = {CURRENT_ORGANIZATION}) WITH CHECK (organization_id = {CURRENT_ORGANIZATION})")
    op.execute("CREATE POLICY yearclock_group_grants_live_organization ON yearclock_group_grants AS RESTRICTIVE USING (app_organization_live(organization_id)) WITH CHECK (app_organization_live(organization_id))")
    op.execute("CREATE POLICY yearclock_group_grants_no_support ON yearclock_group_grants AS RESTRICTIVE USING (NULLIF(current_setting('app.current_support_access_id', true), '') IS NULL)")


def downgrade() -> None:
    op.drop_table("yearclock_group_grants")
