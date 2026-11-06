"""Add recurring Event Series and persisted Occurrences.

Revision ID: 0012
Revises: 0011
"""
from alembic import op
import sqlalchemy as sa
revision = "0012"; down_revision = "0011"; branch_labels = None; depends_on = None
def upgrade() -> None:
    op.create_table("event_series", sa.Column("id", sa.Uuid(), primary_key=True), sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False), sa.Column("yearclock_id", sa.Uuid(), sa.ForeignKey("yearclocks.id", ondelete="CASCADE"), nullable=False), sa.Column("lane_id", sa.Uuid(), sa.ForeignKey("lanes.id", ondelete="RESTRICT"), nullable=False), sa.Column("category_id", sa.Uuid(), sa.ForeignKey("categories.id", ondelete="SET NULL")), sa.Column("title", sa.String(200), nullable=False), sa.Column("description", sa.Text()), sa.Column("external_url", sa.String(2048)), sa.Column("starts_on", sa.Date(), nullable=False), sa.Column("frequency", sa.String(10), nullable=False), sa.Column("interval", sa.Integer(), server_default="1", nullable=False), sa.Column("until", sa.Date()), sa.Column("occurrence_count", sa.Integer()), sa.Column("last_day", sa.Boolean(), server_default="false", nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.create_table("series_occurrences", sa.Column("id", sa.Uuid(), primary_key=True), sa.Column("series_id", sa.Uuid(), sa.ForeignKey("event_series.id", ondelete="CASCADE"), nullable=False), sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False), sa.Column("series_date", sa.Date(), nullable=False), sa.Column("event_id", sa.Uuid(), sa.ForeignKey("events.id", ondelete="CASCADE"), nullable=False, unique=True), sa.UniqueConstraint("series_id", "series_date", name="uq_series_occurrences_series_date"))
    for table in ("event_series", "series_occurrences"):
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO shadow_app"); op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"); op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY"); op.execute(f"CREATE POLICY {table}_policy ON {table} USING (organization_id = NULLIF(current_setting('app.current_organization_id', true), '')::uuid) WITH CHECK (organization_id = NULLIF(current_setting('app.current_organization_id', true), '')::uuid)")
def downgrade() -> None:
    op.drop_table("series_occurrences"); op.drop_table("event_series")
