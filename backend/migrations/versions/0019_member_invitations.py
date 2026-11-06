"""Permit Organization User invitations.

Revision ID: 0019
Revises: 0018
"""

from alembic import op


revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(
        "ck_organization_memberships_role",
        "organization_memberships",
        type_="check",
    )
    op.create_check_constraint(
        "ck_organization_memberships_role",
        "organization_memberships",
        "role IN ('owner', 'admin', 'member')",
    )
    op.drop_constraint(
        "ck_organization_invitations_role",
        "organization_invitations",
        type_="check",
    )
    op.create_check_constraint(
        "ck_organization_invitations_role",
        "organization_invitations",
        "role IN ('owner', 'admin', 'member')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_organization_memberships_role",
        "organization_memberships",
        type_="check",
    )
    op.execute("DELETE FROM organization_memberships WHERE role = 'member'")
    op.create_check_constraint(
        "ck_organization_memberships_role",
        "organization_memberships",
        "role IN ('owner', 'admin')",
    )
    op.drop_constraint(
        "ck_organization_invitations_role",
        "organization_invitations",
        type_="check",
    )
    op.execute("DELETE FROM organization_invitations WHERE role = 'member'")
    op.create_check_constraint(
        "ck_organization_invitations_role",
        "organization_invitations",
        "role IN ('owner', 'admin')",
    )
