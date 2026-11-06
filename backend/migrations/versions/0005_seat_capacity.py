"""Add prepaid Organization seat capacity changes.

Revision ID: 0005
Revises: 0004
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CURRENT_ORGANIZATION = (
    "NULLIF(current_setting('app.current_organization_id', true), '')::uuid"
)


def upgrade() -> None:
    op.add_column(
        "organizations",
        sa.Column(
            "reserved_seats",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
    )
    op.add_column(
        "organizations",
        sa.Column(
            "seat_version",
            sa.Integer(),
            server_default="1",
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "ck_organizations_reserved_seats",
        "organizations",
        "reserved_seats >= 0",
    )
    op.create_check_constraint(
        "ck_organizations_seat_version",
        "organizations",
        "seat_version >= 1",
    )
    op.create_table(
        "organization_seat_changes",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "organization_id",
            sa.Uuid(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "requested_by_user_account_id",
            sa.Uuid(),
            sa.ForeignKey("user_accounts.id"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("from_quantity", sa.Integer(), nullable=False),
        sa.Column("target_quantity", sa.Integer(), nullable=False),
        sa.Column("stripe_reference", sa.String(length=255), nullable=True),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "kind IN ('increase', 'decrease')",
            name="ck_organization_seat_changes_kind",
        ),
        sa.CheckConstraint(
            "status IN ('pending_payment', 'scheduled', 'applied', 'failed')",
            name="ck_organization_seat_changes_status",
        ),
        sa.CheckConstraint(
            "from_quantity >= 1 AND target_quantity >= 1",
            name="ck_organization_seat_changes_quantities",
        ),
    )
    op.create_index(
        "ix_organization_seat_changes_organization_id",
        "organization_seat_changes",
        ["organization_id"],
    )
    op.create_index(
        "uq_organization_seat_changes_open",
        "organization_seat_changes",
        ["organization_id"],
        unique=True,
        postgresql_where=sa.text(
            "status IN ('pending_payment', 'scheduled')"
        ),
    )
    op.create_table(
        "organization_seat_previews",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "organization_id",
            sa.Uuid(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("seat_version", sa.Integer(), nullable=False),
        sa.Column("from_quantity", sa.Integer(), nullable=False),
        sa.Column("target_quantity", sa.Integer(), nullable=False),
        sa.Column("amount_due", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column(
            "proration_date",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "seat_version >= 1 AND from_quantity >= 1 "
            "AND target_quantity > from_quantity",
            name="ck_organization_seat_previews_values",
        ),
        sa.CheckConstraint(
            "amount_due >= 0",
            name="ck_organization_seat_previews_amount",
        ),
    )
    op.create_index(
        "ix_organization_seat_previews_organization_id",
        "organization_seat_previews",
        ["organization_id"],
    )
    op.execute(
        """
        GRANT SELECT, INSERT, UPDATE
        ON TABLE organization_seat_changes, organization_seat_previews
        TO shadow_app
        """
    )
    for table_name in (
        "organization_seat_changes",
        "organization_seat_previews",
    ):
        op.execute(f"ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table_name} FORCE ROW LEVEL SECURITY")
        for operation in ("SELECT", "INSERT", "UPDATE"):
            using = (
                f"USING (organization_id = {CURRENT_ORGANIZATION})"
                if operation in ("SELECT", "UPDATE")
                else ""
            )
            check = (
                f"WITH CHECK (organization_id = {CURRENT_ORGANIZATION})"
                if operation in ("INSERT", "UPDATE")
                else ""
            )
            op.execute(
                f"""
                CREATE POLICY {table_name}_{operation.lower()}
                ON {table_name}
                FOR {operation}
                {using}
                {check}
                """
            )


def downgrade() -> None:
    for table_name in (
        "organization_seat_previews",
        "organization_seat_changes",
    ):
        for operation in ("select", "insert", "update"):
            op.execute(
                f"DROP POLICY {table_name}_{operation} ON {table_name}"
            )
        op.execute(f"ALTER TABLE {table_name} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table_name} DISABLE ROW LEVEL SECURITY")
    op.drop_index(
        "ix_organization_seat_previews_organization_id",
        table_name="organization_seat_previews",
    )
    op.drop_table("organization_seat_previews")
    op.drop_index(
        "uq_organization_seat_changes_open",
        table_name="organization_seat_changes",
    )
    op.drop_index(
        "ix_organization_seat_changes_organization_id",
        table_name="organization_seat_changes",
    )
    op.drop_table("organization_seat_changes")
    op.drop_constraint(
        "ck_organizations_seat_version",
        "organizations",
        type_="check",
    )
    op.drop_constraint(
        "ck_organizations_reserved_seats",
        "organizations",
        type_="check",
    )
    op.drop_column("organizations", "seat_version")
    op.drop_column("organizations", "reserved_seats")
