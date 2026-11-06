"""Permit Owner invitations.

Revision ID: 0007
Revises: 0006
"""
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.drop_constraint("ck_organization_invitations_role", "organization_invitations", type_="check")
    op.create_check_constraint("ck_organization_invitations_role", "organization_invitations", "role IN ('owner', 'admin')")

def downgrade() -> None:
    op.drop_constraint("ck_organization_invitations_role", "organization_invitations", type_="check")
    op.execute("DELETE FROM organization_invitations WHERE role = 'owner'")
    op.create_check_constraint("ck_organization_invitations_role", "organization_invitations", "role = 'admin'")
