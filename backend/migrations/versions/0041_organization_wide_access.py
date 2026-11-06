"""Organization-wide Access (Yearclock V2, P10a ticket 02).

Revision ID: 0041
Revises: 0040
"""

import sqlalchemy as sa
from alembic import op


revision = "0041"
down_revision = "0040"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("yearclocks", sa.Column("organization_access", sa.String(length=10), server_default="none", nullable=False))
    op.create_check_constraint("ck_yearclocks_organization_access", "yearclocks", "organization_access IN ('none', 'viewer', 'editor')")


def downgrade() -> None:
    op.drop_constraint("ck_yearclocks_organization_access", "yearclocks", type_="check")
    op.drop_column("yearclocks", "organization_access")
