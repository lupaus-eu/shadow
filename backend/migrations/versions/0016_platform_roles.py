"""Add Platform User roles.

Revision ID: 0016
Revises: 0015
"""
from alembic import op
import sqlalchemy as sa
revision = "0016"; down_revision = "0015"; branch_labels = None; depends_on = None
def upgrade() -> None:
    op.create_table("platform_roles", sa.Column("id", sa.Uuid(), primary_key=True), sa.Column("user_account_id", sa.Uuid(), sa.ForeignKey("user_accounts.id", ondelete="CASCADE"), nullable=False), sa.Column("role", sa.String(30), nullable=False), sa.UniqueConstraint("user_account_id", "role", name="uq_platform_roles_account_role"), sa.CheckConstraint("role IN ('platform_admin', 'support_agent')", name="ck_platform_roles_role"))
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON platform_roles TO shadow_app")
def downgrade() -> None: op.drop_table("platform_roles")
