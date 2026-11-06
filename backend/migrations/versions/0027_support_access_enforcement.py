"""Enforce Support Access grants in PostgreSQL (ADR-0020).

``app_support_grant_allows(needs_write)`` is true when a transaction carries
no Support Access id, or when it carries one for an approved, unexpired grant
of the current Organization (with write scope when needed). Restrictive
policies on every content table AND this check with the existing Organization
policies, so a support session can never read or write outside its grant.

``support_access_requests`` gains row-level security: rows are visible to the
Organization's own context and to the Support Agent who requested them.

Revision ID: 0027
Revises: 0026
"""

import sqlalchemy as sa
from alembic import op


revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None

CONTENT_TABLES = ("yearclocks", "lanes", "categories", "events", "event_series", "series_occurrences", "yearclock_access_grants")
CURRENT_ORGANIZATION = "NULLIF(current_setting('app.current_organization_id', true), '')::uuid"
CURRENT_USER = "NULLIF(current_setting('app.current_user_account_id', true), '')::uuid"


def upgrade() -> None:
    op.add_column("support_access_requests", sa.Column("requested_hours", sa.Integer(), server_default="1", nullable=False))
    op.add_column("support_access_requests", sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.add_column("support_access_requests", sa.Column("decided_at", sa.DateTime(timezone=True)))
    op.add_column("support_access_requests", sa.Column("revoked_at", sa.DateTime(timezone=True)))
    op.create_check_constraint("ck_support_access_scope", "support_access_requests", "scope IN ('read', 'write')")
    op.create_check_constraint("ck_support_access_status", "support_access_requests", "status IN ('pending', 'approved', 'rejected', 'revoked', 'expired')")
    op.create_check_constraint("ck_support_access_hours", "support_access_requests", "requested_hours BETWEEN 1 AND 24")
    op.execute("ALTER TABLE support_access_requests ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE support_access_requests FORCE ROW LEVEL SECURITY")
    visible = f"organization_id = {CURRENT_ORGANIZATION} OR requested_by_user_account_id = {CURRENT_USER}"
    op.execute(f"CREATE POLICY support_access_requests_select ON support_access_requests FOR SELECT USING ({visible})")
    op.execute(f"CREATE POLICY support_access_requests_insert ON support_access_requests FOR INSERT WITH CHECK (requested_by_user_account_id = {CURRENT_USER} AND status = 'pending')")
    op.execute(f"CREATE POLICY support_access_requests_update ON support_access_requests FOR UPDATE USING ({visible}) WITH CHECK ({visible})")
    op.execute(
        f"""
        CREATE FUNCTION app_support_grant_allows(needs_write boolean) RETURNS boolean
        LANGUAGE sql STABLE AS $$
            SELECT CASE
                WHEN NULLIF(current_setting('app.current_support_access_id', true), '') IS NULL THEN true
                ELSE EXISTS (
                    SELECT 1 FROM support_access_requests grant_row
                    WHERE grant_row.id = NULLIF(current_setting('app.current_support_access_id', true), '')::uuid
                      AND grant_row.organization_id = {CURRENT_ORGANIZATION}
                      AND grant_row.status = 'approved'
                      AND grant_row.expires_at > now()
                      AND (NOT needs_write OR grant_row.scope = 'write')
                )
            END
        $$
        """
    )
    for table in CONTENT_TABLES:
        op.execute(f"CREATE POLICY {table}_support_select ON {table} AS RESTRICTIVE FOR SELECT USING (app_support_grant_allows(false))")
        op.execute(f"CREATE POLICY {table}_support_insert ON {table} AS RESTRICTIVE FOR INSERT WITH CHECK (app_support_grant_allows(true))")
        op.execute(f"CREATE POLICY {table}_support_update ON {table} AS RESTRICTIVE FOR UPDATE USING (app_support_grant_allows(true)) WITH CHECK (app_support_grant_allows(true))")
        op.execute(f"CREATE POLICY {table}_support_delete ON {table} AS RESTRICTIVE FOR DELETE USING (app_support_grant_allows(true))")


def downgrade() -> None:
    for table in CONTENT_TABLES:
        for operation in ("select", "insert", "update", "delete"):
            op.execute(f"DROP POLICY {table}_support_{operation} ON {table}")
    op.execute("DROP FUNCTION app_support_grant_allows(boolean)")
    for operation in ("select", "insert", "update"):
        op.execute(f"DROP POLICY support_access_requests_{operation} ON support_access_requests")
    op.execute("ALTER TABLE support_access_requests NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE support_access_requests DISABLE ROW LEVEL SECURITY")
    for constraint in ("ck_support_access_hours", "ck_support_access_status", "ck_support_access_scope"):
        op.drop_constraint(constraint, "support_access_requests", type_="check")
    for column in ("revoked_at", "decided_at", "created_at", "requested_hours"):
        op.drop_column("support_access_requests", column)
