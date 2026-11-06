"""Invitation Groups (Yearclock V2, P10a ticket 05).

The Groups an invited person joins when accepting. Rows cascade with the
Invitation and the Group, so a Group deleted in the meantime is skipped.

Revision ID: 0044
Revises: 0043
"""

import sqlalchemy as sa
from alembic import op


revision = "0044"
down_revision = "0043"
branch_labels = None
depends_on = None

CURRENT_ORGANIZATION = "NULLIF(current_setting('app.current_organization_id', true), '')::uuid"


def upgrade() -> None:
    op.create_table(
        "invitation_groups",
        sa.Column("invitation_id", sa.Uuid(), sa.ForeignKey("organization_invitations.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("group_id", sa.Uuid(), sa.ForeignKey("member_groups.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
    )
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON invitation_groups TO shadow_app")
    op.execute("ALTER TABLE invitation_groups ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE invitation_groups FORCE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY invitation_groups_policy ON invitation_groups USING (organization_id = {CURRENT_ORGANIZATION}) WITH CHECK (organization_id = {CURRENT_ORGANIZATION})")
    op.execute("CREATE POLICY invitation_groups_live_organization ON invitation_groups AS RESTRICTIVE USING (app_organization_live(organization_id)) WITH CHECK (app_organization_live(organization_id))")
    op.execute("CREATE POLICY invitation_groups_no_support ON invitation_groups AS RESTRICTIVE USING (NULLIF(current_setting('app.current_support_access_id', true), '') IS NULL)")


def downgrade() -> None:
    op.drop_table("invitation_groups")
