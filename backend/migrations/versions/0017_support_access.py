"""Add customer-approved Support Access.

Revision ID: 0017
Revises: 0016
"""
from alembic import op
import sqlalchemy as sa
revision = "0017"; down_revision = "0016"; branch_labels = None; depends_on = None
def upgrade() -> None:
    op.create_table("support_access_requests", sa.Column("id", sa.Uuid(), primary_key=True), sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False), sa.Column("requested_by_user_account_id", sa.Uuid(), sa.ForeignKey("user_accounts.id"), nullable=False), sa.Column("case_reference", sa.String(200), nullable=False), sa.Column("scope", sa.String(20), nullable=False), sa.Column("status", sa.String(20), nullable=False), sa.Column("expires_at", sa.DateTime(timezone=True)), sa.Column("approved_by_user_account_id", sa.Uuid()))
    op.execute("GRANT SELECT, INSERT, UPDATE ON support_access_requests TO yearclock_app")
def downgrade() -> None: op.drop_table("support_access_requests")
