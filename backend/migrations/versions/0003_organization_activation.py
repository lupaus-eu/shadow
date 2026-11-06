"""Add paid Organization activation.

Revision ID: 0003
Revises: 0002
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "organizations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("time_zone", sa.String(length=100), nullable=False),
        sa.Column("default_locale", sa.String(length=2), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column(
            "created_by_user_account_id",
            sa.Uuid(),
            sa.ForeignKey("user_accounts.id"),
            nullable=False,
        ),
        sa.Column("billing_name", sa.String(length=200), nullable=False),
        sa.Column("billing_email", sa.String(length=320), nullable=False),
        sa.Column("purchased_seats", sa.Integer(), nullable=False),
        sa.Column(
            "stripe_checkout_session_id",
            sa.String(length=255),
            nullable=True,
            unique=True,
        ),
        sa.Column(
            "stripe_customer_id",
            sa.String(length=255),
            nullable=True,
            unique=True,
        ),
        sa.Column(
            "stripe_subscription_id",
            sa.String(length=255),
            nullable=True,
            unique=True,
        ),
        sa.Column(
            "pending_activation_expires_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('pending_activation', 'active', 'expired')",
            name="ck_organizations_status",
        ),
        sa.CheckConstraint(
            "default_locale IN ('en', 'fi')",
            name="ck_organizations_default_locale",
        ),
        sa.CheckConstraint(
            "purchased_seats >= 1",
            name="ck_organizations_purchased_seats",
        ),
    )
    op.create_index(
        "ix_organizations_created_by_user_account_id",
        "organizations",
        ["created_by_user_account_id"],
    )
    op.create_table(
        "organization_memberships",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "organization_id",
            sa.Uuid(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_account_id",
            sa.Uuid(),
            sa.ForeignKey("user_accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "role IN ('owner', 'admin')",
            name="ck_organization_memberships_role",
        ),
        sa.UniqueConstraint(
            "organization_id",
            "user_account_id",
            name="uq_organization_memberships_account",
        ),
    )
    op.create_index(
        "ix_organization_memberships_organization_id",
        "organization_memberships",
        ["organization_id"],
    )
    op.create_index(
        "ix_organization_memberships_user_account_id",
        "organization_memberships",
        ["user_account_id"],
    )
    op.create_table(
        "yearclocks",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "organization_id",
            sa.Uuid(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("display_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "organization_id",
            "id",
            name="uq_yearclocks_organization_id_id",
        ),
    )
    op.create_index(
        "ix_yearclocks_organization_id",
        "yearclocks",
        ["organization_id"],
    )
    op.create_table(
        "lanes",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "organization_id",
            sa.Uuid(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "yearclock_id",
            sa.Uuid(),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("display_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "yearclock_id"],
            ["yearclocks.organization_id", "yearclocks.id"],
            ondelete="CASCADE",
            name="fk_lanes_yearclock_organization",
        ),
    )
    op.create_index("ix_lanes_organization_id", "lanes", ["organization_id"])
    op.create_index("ix_lanes_yearclock_id", "lanes", ["yearclock_id"])
    op.create_table(
        "stripe_webhook_events",
        sa.Column("event_id", sa.String(length=255), primary_key=True),
        sa.Column(
            "organization_id",
            sa.Uuid(),
            sa.ForeignKey("organizations.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("event_type", sa.String(length=120), nullable=False),
        sa.Column("outcome", sa.String(length=40), nullable=False),
        sa.Column(
            "processed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_stripe_webhook_events_organization_id",
        "stripe_webhook_events",
        ["organization_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_stripe_webhook_events_organization_id",
        table_name="stripe_webhook_events",
    )
    op.drop_table("stripe_webhook_events")
    op.drop_index("ix_lanes_yearclock_id", table_name="lanes")
    op.drop_index("ix_lanes_organization_id", table_name="lanes")
    op.drop_table("lanes")
    op.drop_index("ix_yearclocks_organization_id", table_name="yearclocks")
    op.drop_table("yearclocks")
    op.drop_index(
        "ix_organization_memberships_user_account_id",
        table_name="organization_memberships",
    )
    op.drop_index(
        "ix_organization_memberships_organization_id",
        table_name="organization_memberships",
    )
    op.drop_table("organization_memberships")
    op.drop_index(
        "ix_organizations_created_by_user_account_id",
        table_name="organizations",
    )
    op.drop_table("organizations")
