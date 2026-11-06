"""Add Yearclock Categories.

Revision ID: 0011
Revises: 0010
"""
from alembic import op
import sqlalchemy as sa
revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None
def upgrade() -> None:
    op.create_table("categories", sa.Column("id", sa.Uuid(), primary_key=True), sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False), sa.Column("yearclock_id", sa.Uuid(), sa.ForeignKey("yearclocks.id", ondelete="CASCADE"), nullable=False), sa.Column("name", sa.String(120), nullable=False), sa.Column("color", sa.String(7)), sa.Column("display_order", sa.Integer(), server_default="0", nullable=False), sa.Column("version", sa.Integer(), server_default="1", nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.add_column("events", sa.Column("category_id", sa.Uuid(), sa.ForeignKey("categories.id", ondelete="SET NULL"), nullable=True))
    for column in ("organization_id", "yearclock_id"): op.create_index(f"ix_categories_{column}", "categories", [column])
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON categories TO yearclock_app")
    op.execute("ALTER TABLE categories ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE categories FORCE ROW LEVEL SECURITY")
    op.execute("CREATE POLICY categories_policy ON categories USING (organization_id = NULLIF(current_setting('app.current_organization_id', true), '')::uuid) WITH CHECK (organization_id = NULLIF(current_setting('app.current_organization_id', true), '')::uuid)")
def downgrade() -> None:
    op.execute("DROP POLICY categories_policy ON categories")
    op.drop_column("events", "category_id")
    op.drop_table("categories")
