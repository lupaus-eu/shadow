"""Let Owners and Admins read their Organization's Audit Events under RLS.

The application role could only insert Audit Events, so the audit activity API
failed. Reads are now limited to the current Organization by row-level
security; inserts must carry the current Organization context; there is still
no UPDATE or DELETE privilege, so Audit Events stay append-only.

Revision ID: 0025
Revises: 0024
"""

from alembic import op


revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None

CURRENT_ORGANIZATION = "NULLIF(current_setting('app.current_organization_id', true), '')::uuid"


def upgrade() -> None:
    op.execute("GRANT SELECT ON audit_events TO shadow_app")
    op.execute("ALTER TABLE audit_events ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE audit_events FORCE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY audit_events_select ON audit_events FOR SELECT USING (organization_id = {CURRENT_ORGANIZATION})")
    op.execute(f"CREATE POLICY audit_events_insert ON audit_events FOR INSERT WITH CHECK (organization_id IS NOT DISTINCT FROM {CURRENT_ORGANIZATION})")
    op.execute("CREATE INDEX ix_audit_events_organization_occurred ON audit_events (organization_id, occurred_at DESC)")


def downgrade() -> None:
    op.execute("DROP INDEX ix_audit_events_organization_occurred")
    op.execute("DROP POLICY audit_events_insert ON audit_events")
    op.execute("DROP POLICY audit_events_select ON audit_events")
    op.execute("ALTER TABLE audit_events NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE audit_events DISABLE ROW LEVEL SECURITY")
    op.execute("REVOKE SELECT ON audit_events FROM shadow_app")
