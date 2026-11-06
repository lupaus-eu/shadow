"""Enroll Platform Users and separate platform sign-in.

``platform_enrollments`` lets an operator pre-authorize a verified email for
platform roles; the first platform sign-in with that email creates the
Platform User account. ``oidc_login_attempts.audience`` records whether a
sign-in is for the customer application or the operator console.

Revision ID: 0026
Revises: 0025
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("oidc_login_attempts", sa.Column("audience", sa.String(20), server_default="customer", nullable=False))
    op.create_check_constraint("ck_oidc_login_attempts_audience", "oidc_login_attempts", "audience IN ('customer', 'platform')")
    op.create_table(
        "platform_enrollments",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("roles", postgresql.ARRAY(sa.String(30)), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True)),
        sa.Column("user_account_id", sa.Uuid(), sa.ForeignKey("user_accounts.id", ondelete="SET NULL")),
        sa.CheckConstraint("roles <@ ARRAY['platform_admin', 'support_agent']::varchar[] AND cardinality(roles) > 0", name="ck_platform_enrollments_roles"),
    )
    op.create_index("ix_platform_enrollments_email", "platform_enrollments", ["email"])
    op.execute("GRANT SELECT, INSERT, UPDATE ON platform_enrollments TO shadow_app")


def downgrade() -> None:
    op.drop_table("platform_enrollments")
    op.drop_constraint("ck_oidc_login_attempts_audience", "oidc_login_attempts", type_="check")
    op.drop_column("oidc_login_attempts", "audience")
