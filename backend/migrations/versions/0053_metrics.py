"""Metrics (KPIs) with monthly values and formulas.

A Metric belongs to a Model version. A metric without a formula holds its monthly values;
a metric with a formula is derived from other metrics of the same version by key.

Revision ID: 0053
Revises: 0052
"""

import sqlalchemy as sa
from alembic import op


revision = "0053"
down_revision = "0052"
branch_labels = None
depends_on = None

CURRENT_ORGANIZATION = "NULLIF(current_setting('app.current_organization_id', true), '')::uuid"
TABLES = ("metrics", "metric_values")


def _policies(table: str) -> None:
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO shadow_app")
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY {table}_policy ON {table} USING (organization_id = {CURRENT_ORGANIZATION}) WITH CHECK (organization_id = {CURRENT_ORGANIZATION})")
    op.execute(f"CREATE POLICY {table}_live_organization ON {table} AS RESTRICTIVE USING (app_organization_live(organization_id)) WITH CHECK (app_organization_live(organization_id))")
    op.execute(f"CREATE POLICY {table}_support_select ON {table} AS RESTRICTIVE FOR SELECT USING (app_support_grant_allows(false))")
    op.execute(f"CREATE POLICY {table}_support_insert ON {table} AS RESTRICTIVE FOR INSERT WITH CHECK (app_support_grant_allows(true))")
    op.execute(f"CREATE POLICY {table}_support_update ON {table} AS RESTRICTIVE FOR UPDATE USING (app_support_grant_allows(true)) WITH CHECK (app_support_grant_allows(true))")
    op.execute(f"CREATE POLICY {table}_support_delete ON {table} AS RESTRICTIVE FOR DELETE USING (app_support_grant_allows(true))")


def upgrade() -> None:
    op.create_table(
        "metrics",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("model_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("version_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("node_id", sa.Uuid(), sa.ForeignKey("nodes.id", ondelete="SET NULL"), nullable=True),
        sa.Column("key", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("unit", sa.String(length=20), nullable=True),
        sa.Column("formula", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["version_id", "model_id"], ["model_versions.id", "model_versions.model_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["model_id", "organization_id"], ["models.id", "models.organization_id"], ondelete="CASCADE"),
        sa.UniqueConstraint("version_id", "key", name="uq_metrics_version_key"),
        sa.UniqueConstraint("id", "version_id", name="uq_metrics_id_version"),
        sa.CheckConstraint("key ~ '^[a-z][a-z0-9_]{0,39}$'", name="ck_metrics_key"),
        sa.CheckConstraint("length(btrim(name)) > 0", name="ck_metrics_name"),
    )
    op.create_table(
        "metric_values",
        sa.Column("metric_id", sa.Uuid(), nullable=False),
        sa.Column("period", sa.Date(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("version_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("value", sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint("metric_id", "period"),
        sa.ForeignKeyConstraint(["metric_id", "version_id"], ["metrics.id", "metrics.version_id"], ondelete="CASCADE"),
        sa.CheckConstraint("extract(day from period) = 1", name="ck_metric_values_month_start"),
        sa.CheckConstraint("value = value AND value NOT IN ('Infinity', '-Infinity')", name="ck_metric_values_finite"),
    )
    for table in TABLES:
        _policies(table)


def downgrade() -> None:
    op.drop_table("metric_values")
    op.drop_table("metrics")
