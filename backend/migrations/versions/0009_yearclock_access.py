"""Add per-Yearclock access grants.

Revision ID: 0009
Revises: 0008
"""
from alembic import op
import sqlalchemy as sa

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table("yearclock_access_grants", sa.Column("id", sa.Uuid(), primary_key=True), sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False), sa.Column("yearclock_id", sa.Uuid(), sa.ForeignKey("yearclocks.id", ondelete="CASCADE"), nullable=False), sa.Column("user_account_id", sa.Uuid(), sa.ForeignKey("user_accounts.id", ondelete="CASCADE"), nullable=False), sa.Column("role", sa.String(20), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False), sa.UniqueConstraint("yearclock_id", "user_account_id", name="uq_yearclock_access_grant"), sa.CheckConstraint("role IN ('editor', 'viewer')", name="ck_yearclock_access_grants_role"))
    op.create_index("ix_yearclock_access_grants_organization_id", "yearclock_access_grants", ["organization_id"])
    op.create_index("ix_yearclock_access_grants_yearclock_id", "yearclock_access_grants", ["yearclock_id"])
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON yearclock_access_grants TO yearclock_app")
    op.execute("ALTER TABLE yearclock_access_grants ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE yearclock_access_grants FORCE ROW LEVEL SECURITY")
    op.execute("CREATE POLICY yearclock_access_grants_policy ON yearclock_access_grants USING (organization_id = NULLIF(current_setting('app.current_organization_id', true), '')::uuid) WITH CHECK (organization_id = NULLIF(current_setting('app.current_organization_id', true), '')::uuid)")
def downgrade() -> None:
    op.execute("DROP POLICY yearclock_access_grants_policy ON yearclock_access_grants")
    op.drop_index("ix_yearclock_access_grants_yearclock_id", table_name="yearclock_access_grants")
    op.drop_index("ix_yearclock_access_grants_organization_id", table_name="yearclock_access_grants")
    op.drop_table("yearclock_access_grants")
