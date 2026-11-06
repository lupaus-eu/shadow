"""Add Organization Invitations and email delivery metadata.

Revision ID: 0006
Revises: 0005
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CURRENT_USER = "NULLIF(current_setting('app.current_user_account_id', true), '')::uuid"
CURRENT_ORGANIZATION = "NULLIF(current_setting('app.current_organization_id', true), '')::uuid"
CURRENT_INVITATION_TOKEN_HASH = "NULLIF(current_setting('app.current_invitation_token_hash', true), '')"


def upgrade() -> None:
    op.create_table(
        "organization_invitations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("invited_by_user_account_id", sa.Uuid(), sa.ForeignKey("user_accounts.id"), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False, unique=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_by_user_account_id", sa.Uuid(), nullable=True),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("role = 'admin'", name="ck_organization_invitations_role"),
        sa.CheckConstraint("status IN ('pending', 'accepted', 'revoked', 'superseded', 'expired')", name="ck_organization_invitations_status"),
    )
    op.create_index("ix_organization_invitations_organization_id", "organization_invitations", ["organization_id"])
    op.create_index("ix_organization_invitations_invited_by_user_account_id", "organization_invitations", ["invited_by_user_account_id"])
    op.add_column("outbox_messages", sa.Column("provider_message_id", sa.String(length=255), nullable=True))
    op.execute("GRANT SELECT, INSERT, UPDATE ON TABLE organization_invitations TO yearclock_app")
    op.execute("ALTER TABLE organization_invitations ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE organization_invitations FORCE ROW LEVEL SECURITY")
    op.execute(f"""CREATE POLICY organization_invitations_select ON organization_invitations FOR SELECT USING (organization_id = {CURRENT_ORGANIZATION} OR ({CURRENT_ORGANIZATION} IS NULL AND (email = (SELECT email FROM user_accounts WHERE id = {CURRENT_USER}) OR token_hash = {CURRENT_INVITATION_TOKEN_HASH})))""")
    op.execute(f"""CREATE POLICY organization_invitations_insert ON organization_invitations FOR INSERT WITH CHECK (organization_id = {CURRENT_ORGANIZATION})""")
    op.execute(f"""CREATE POLICY organization_invitations_update ON organization_invitations FOR UPDATE USING (organization_id = {CURRENT_ORGANIZATION}) WITH CHECK (organization_id = {CURRENT_ORGANIZATION})""")


def downgrade() -> None:
    for name in ("organization_invitations_select", "organization_invitations_insert", "organization_invitations_update"):
        op.execute(f"DROP POLICY {name} ON organization_invitations")
    op.execute("ALTER TABLE organization_invitations NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE organization_invitations DISABLE ROW LEVEL SECURITY")
    op.drop_index("ix_organization_invitations_invited_by_user_account_id", table_name="organization_invitations")
    op.drop_index("ix_organization_invitations_organization_id", table_name="organization_invitations")
    op.drop_table("organization_invitations")
    op.drop_column("outbox_messages", "provider_message_id")
