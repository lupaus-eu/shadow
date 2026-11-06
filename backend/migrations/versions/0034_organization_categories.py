"""Organization Categories (Yearclock V2, P2 ticket 05).

A Category with no Yearclock belongs to the whole Organization. Existing rows
keep their Yearclock. Organization Category names are unique per Organization,
ignoring case; Yearclock Categories keep V1 behaviour.

Revision ID: 0034
Revises: 0033
"""

import sqlalchemy as sa
from alembic import op


revision = "0034"
down_revision = "0033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("categories", "yearclock_id", existing_type=sa.Uuid(), nullable=True)
    op.execute("CREATE UNIQUE INDEX uq_categories_organization_name ON categories (organization_id, lower(name)) WHERE yearclock_id IS NULL")


def downgrade() -> None:
    op.execute("DROP INDEX uq_categories_organization_name")
    op.execute("DELETE FROM categories WHERE yearclock_id IS NULL")
    op.alter_column("categories", "yearclock_id", existing_type=sa.Uuid(), nullable=False)
