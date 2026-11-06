"""Establish the application foundation.

Revision ID: 0001
Revises:
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "audit_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("actor_user_account_id", sa.Uuid(), nullable=True),
        sa.Column("organization_id", sa.Uuid(), nullable=True),
        sa.Column("support_access_id", sa.Uuid(), nullable=True),
        sa.Column("action", sa.String(length=120), nullable=False),
        sa.Column("target_type", sa.String(length=120), nullable=False),
        sa.Column("target_id", sa.Uuid(), nullable=False),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("request_id", sa.String(length=120), nullable=False),
        sa.Column(
            "change_summary",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_audit_events_organization_id",
        "audit_events",
        ["organization_id"],
    )
    op.execute(
        """
        CREATE FUNCTION reject_audit_event_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RAISE EXCEPTION 'audit events are append-only';
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER audit_events_append_only
        BEFORE UPDATE OR DELETE ON audit_events
        FOR EACH ROW EXECUTE FUNCTION reject_audit_event_mutation()
        """
    )
    for table_name, type_column in (
        ("outbox_messages", "topic"),
        ("background_jobs", "job_type"),
    ):
        op.create_table(
            table_name,
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("organization_id", sa.Uuid(), nullable=True),
            sa.Column(type_column, sa.String(length=120), nullable=False),
            sa.Column(
                "payload",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
            ),
            sa.Column(
                "idempotency_key",
                sa.String(length=200),
                nullable=False,
                unique=True,
            ),
            sa.Column(
                "status",
                sa.String(length=20),
                server_default="pending",
                nullable=False,
            ),
            sa.Column(
                "attempts",
                sa.Integer(),
                server_default="0",
                nullable=False,
            ),
            sa.Column(
                "available_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_error", sa.Text(), nullable=True),
            sa.CheckConstraint(
                "status IN ('pending', 'processing', 'completed', 'failed')",
                name=f"ck_{table_name}_status",
            ),
        )
        op.create_index(
            f"ix_{table_name}_organization_id",
            table_name,
            ["organization_id"],
        )
        op.create_index(
            f"ix_{table_name}_claimable",
            table_name,
            ["status", "available_at"],
        )


def downgrade() -> None:
    for table_name in ("background_jobs", "outbox_messages"):
        op.drop_index(f"ix_{table_name}_claimable", table_name=table_name)
        op.drop_index(f"ix_{table_name}_organization_id", table_name=table_name)
        op.drop_table(table_name)
    op.execute("DROP TRIGGER audit_events_append_only ON audit_events")
    op.execute("DROP FUNCTION reject_audit_event_mutation()")
    op.drop_index("ix_audit_events_organization_id", table_name="audit_events")
    op.drop_table("audit_events")
