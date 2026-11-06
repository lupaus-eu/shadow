"""Simulations: forecast runs of a Model version and their results.

Revision ID: 0054
Revises: 0053
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB


revision = "0054"
down_revision = "0053"
branch_labels = None
depends_on = None

CURRENT_ORGANIZATION = "NULLIF(current_setting('app.current_organization_id', true), '')::uuid"
TABLES = ("simulations", "simulation_points")


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
        "simulations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("model_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("version_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("method", sa.String(length=20), nullable=False),
        sa.Column("horizon_months", sa.Integer(), nullable=False),
        sa.Column("adjustments", JSONB(), server_default="[]", nullable=False),
        sa.Column("skipped", JSONB(), server_default="{}", nullable=False),
        sa.Column("history_end", sa.Date(), nullable=True),
        sa.Column("created_by_user_account_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["version_id", "model_id"], ["model_versions.id", "model_versions.model_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["model_id", "organization_id"], ["models.id", "models.organization_id"], ondelete="CASCADE"),
        sa.UniqueConstraint("id", "organization_id", name="uq_simulations_id_organization"),
        sa.CheckConstraint("method IN ('linear', 'seasonal', 'holt')", name="ck_simulations_method"),
        sa.CheckConstraint("horizon_months BETWEEN 1 AND 60", name="ck_simulations_horizon"),
        sa.CheckConstraint("length(btrim(name)) > 0", name="ck_simulations_name"),
    )
    op.create_table(
        "simulation_points",
        sa.Column("simulation_id", sa.Uuid(), nullable=False),
        sa.Column("metric_key", sa.String(length=40), nullable=False),
        sa.Column("period", sa.Date(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("lower", sa.Float(), nullable=True),
        sa.Column("upper", sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint("simulation_id", "metric_key", "period"),
        sa.ForeignKeyConstraint(["simulation_id", "organization_id"], ["simulations.id", "simulations.organization_id"], ondelete="CASCADE"),
    )
    for table in TABLES:
        _policies(table)


def downgrade() -> None:
    op.drop_table("simulation_points")
    op.drop_table("simulations")
