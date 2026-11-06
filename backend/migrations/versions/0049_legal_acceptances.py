"""Legal document acceptances and announcements (ADR-0041; yearclock-v2-legal-documents tickets 03 and 05).

``legal_acceptances`` records which Owner accepted which version of a required legal document for an
Organization. It is contract evidence, so it has no ``live organization`` policy (rows are written while
the Organization is still pending activation) and the Organization purge does not touch it.
``legal_announcements`` makes the announcement of a published version idempotent.

Revision ID: 0049
Revises: 0048
"""

import sqlalchemy as sa
from alembic import op


revision = "0049"
down_revision = "0048"
branch_labels = None
depends_on = None

CURRENT_ORGANIZATION = "NULLIF(current_setting('app.current_organization_id', true), '')::uuid"


def upgrade() -> None:
    op.create_table(
        "legal_acceptances",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_account_id", sa.Uuid(), sa.ForeignKey("user_accounts.id", ondelete="SET NULL")),
        sa.Column("accepted_by_email", sa.String(320), nullable=False),
        sa.Column("document_key", sa.String(40), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("locale", sa.String(5), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("request_id", sa.String(120), nullable=False),
        sa.UniqueConstraint("organization_id", "document_key", "version", name="uq_legal_acceptances_version"),
    )
    op.create_index("ix_legal_acceptances_organization_id", "legal_acceptances", ["organization_id"])
    op.execute("GRANT SELECT, INSERT ON legal_acceptances TO shadow_app")
    op.execute("ALTER TABLE legal_acceptances ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE legal_acceptances FORCE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY legal_acceptances_policy ON legal_acceptances USING (organization_id = {CURRENT_ORGANIZATION}) WITH CHECK (organization_id = {CURRENT_ORGANIZATION})")
    op.execute("CREATE POLICY legal_acceptances_no_support ON legal_acceptances AS RESTRICTIVE USING (NULLIF(current_setting('app.current_support_access_id', true), '') IS NULL)")

    op.create_table(
        "legal_announcements",
        sa.Column("document_key", sa.String(40), primary_key=True),
        sa.Column("version", sa.Integer(), primary_key=True),
        sa.Column("announced_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.execute("GRANT SELECT, INSERT ON legal_announcements TO shadow_app")


def downgrade() -> None:
    op.drop_table("legal_announcements")
    op.drop_table("legal_acceptances")
