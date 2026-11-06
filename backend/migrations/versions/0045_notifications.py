"""Notifications and notification settings (Yearclock V2, P8 ticket 02; ADR-0031).

A notification holds a type and parameters, never Event content, and is read
only by its recipient. Reads and changes follow the Organization policy plus
"the recipient is the request's user"; the code that creates a notification
for someone else, and the worker that deletes old ones, switch on a
transaction-local flag (``app.notification_write``) or the worker scope
``notifications`` for the duration of that one statement. Support Access never
reads either table.

Revision ID: 0045
Revises: 0044
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "0045"
down_revision = "0044"
branch_labels = None
depends_on = None

ORGANIZATION = "NULLIF(current_setting('app.current_organization_id', true), '')::uuid"
USER = "NULLIF(current_setting('app.current_user_account_id', true), '')::uuid"
ELEVATED = "(current_setting('app.notification_write', true) = '1' OR current_setting('app.worker_scope', true) = 'notifications')"


def _policies(table: str, owner_column: str) -> None:
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO shadow_app")
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    own = f"organization_id = {ORGANIZATION} AND ({owner_column} = {USER} OR {ELEVATED})"
    op.execute(f"CREATE POLICY {table}_policy ON {table} USING ({own}) WITH CHECK (organization_id = {ORGANIZATION})")
    op.execute(f"CREATE POLICY {table}_live_organization ON {table} AS RESTRICTIVE USING (app_organization_live(organization_id)) WITH CHECK (app_organization_live(organization_id))")
    op.execute(f"CREATE POLICY {table}_no_support ON {table} AS RESTRICTIVE USING (NULLIF(current_setting('app.current_support_access_id', true), '') IS NULL)")


def upgrade() -> None:
    op.create_table(
        "notifications",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("recipient_user_id", sa.Uuid(), sa.ForeignKey("user_accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("type", sa.String(length=60), nullable=False),
        sa.Column("params", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("dedupe_key", sa.String(length=120)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_notifications_recipient", "notifications", ["recipient_user_id", "organization_id", sa.text("created_at DESC")])
    op.create_index("ix_notifications_created_at", "notifications", ["created_at"])
    op.execute("CREATE UNIQUE INDEX uq_notifications_unread_dedupe ON notifications (recipient_user_id, organization_id, dedupe_key) WHERE read_at IS NULL AND dedupe_key IS NOT NULL")
    op.create_table(
        "notification_preferences",
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("user_accounts.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("settings", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("summary_frequency", sa.String(length=10), server_default="off", nullable=False),
        sa.Column("summary_yearclock_ids", postgresql.ARRAY(sa.Uuid())),
        sa.Column("summary_sent_on", sa.Date()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("summary_frequency IN ('off', 'daily', 'weekly')", name="ck_notification_preferences_frequency"),
    )
    _policies("notifications", "recipient_user_id")
    _policies("notification_preferences", "user_id")


def downgrade() -> None:
    op.drop_table("notification_preferences")
    op.drop_table("notifications")
