"""Add all-day Events.

Revision ID: 0010
Revises: 0009
"""
from alembic import op
import sqlalchemy as sa

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table("events", sa.Column("id", sa.Uuid(), primary_key=True), sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False), sa.Column("yearclock_id", sa.Uuid(), sa.ForeignKey("yearclocks.id", ondelete="CASCADE"), nullable=False), sa.Column("lane_id", sa.Uuid(), sa.ForeignKey("lanes.id", ondelete="RESTRICT"), nullable=False), sa.Column("title", sa.String(200), nullable=False), sa.Column("description", sa.Text()), sa.Column("external_url", sa.String(2048)), sa.Column("starts_on", sa.Date(), nullable=False), sa.Column("ends_on", sa.Date()), sa.Column("version", sa.Integer(), server_default="1", nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False), sa.CheckConstraint("ends_on IS NULL OR ends_on >= starts_on", name="ck_events_date_range"))
    for column in ("organization_id", "yearclock_id", "starts_on", "ends_on"): op.create_index(f"ix_events_{column}", "events", [column])
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON events TO shadow_app")
    op.execute("ALTER TABLE events ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE events FORCE ROW LEVEL SECURITY")
    op.execute("CREATE POLICY events_policy ON events USING (organization_id = NULLIF(current_setting('app.current_organization_id', true), '')::uuid) WITH CHECK (organization_id = NULLIF(current_setting('app.current_organization_id', true), '')::uuid)")
def downgrade() -> None:
    op.execute("DROP POLICY events_policy ON events")
    op.drop_table("events")
