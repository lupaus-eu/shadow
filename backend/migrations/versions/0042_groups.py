"""Groups (Yearclock V2, P10a ticket 03).

Flat, named sets of memberships that can receive Yearclock access. Members
cascade with their Group and their membership. Both tables follow the
Organization RLS set; Support Access never reads them.

Revision ID: 0042
Revises: 0041
"""

import sqlalchemy as sa
from alembic import op


revision = "0042"
down_revision = "0041"
branch_labels = None
depends_on = None

CURRENT_ORGANIZATION = "NULLIF(current_setting('app.current_organization_id', true), '')::uuid"


def _policies(table: str) -> None:
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO yearclock_app")
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY {table}_policy ON {table} USING (organization_id = {CURRENT_ORGANIZATION}) WITH CHECK (organization_id = {CURRENT_ORGANIZATION})")
    op.execute(f"CREATE POLICY {table}_live_organization ON {table} AS RESTRICTIVE USING (app_organization_live(organization_id)) WITH CHECK (app_organization_live(organization_id))")
    op.execute(f"CREATE POLICY {table}_no_support ON {table} AS RESTRICTIVE USING (NULLIF(current_setting('app.current_support_access_id', true), '') IS NULL)")


def upgrade() -> None:
    op.create_table(
        "member_groups",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("length(btrim(name)) > 0", name="ck_member_groups_name"),
    )
    op.execute("CREATE UNIQUE INDEX uq_member_groups_organization_name ON member_groups (organization_id, lower(name))")
    op.create_table(
        "member_group_members",
        sa.Column("group_id", sa.Uuid(), sa.ForeignKey("member_groups.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("membership_id", sa.Uuid(), sa.ForeignKey("organization_memberships.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
    )
    op.create_index("ix_member_group_members_membership", "member_group_members", ["membership_id"])
    _policies("member_groups")
    _policies("member_group_members")


def downgrade() -> None:
    op.drop_table("member_group_members")
    op.drop_table("member_groups")
