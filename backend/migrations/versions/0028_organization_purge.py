"""Make Organization deletion enforceable and purgeable (ADR-0008).

- ``ck_organizations_status`` accepts ``pending_deletion`` and ``purged``; the
  deletion request previously violated it.
- ``organizations.purged_at`` records the final purge as deletion evidence.
- ``app_organization_live(organization_id)`` is true for rows of an ``active``
  Organization, or inside the ``purge`` worker scope. Restrictive policies on
  customer content tables AND it with the Organization policies, so Pending
  Deletion blocks every content read and write at the database. Memberships
  and Invitations are blocked the same way inside an Organization context,
  while an Owner can still see their own membership to restore it.
- Audit events stay append-only except that the ``purge`` worker scope may
  empty ``change_summary`` (which can quote content) of its Organization's
  events. Action, actor, target, and time remain as minimal evidence.
- Support Access requests and Invitations can be deleted only by the
  ``purge`` scope.

Revision ID: 0028
Revises: 0027
"""

import sqlalchemy as sa
from alembic import op


revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None

CONTENT_TABLES = ("yearclocks", "lanes", "categories", "events", "event_series", "series_occurrences", "yearclock_access_grants")
CURRENT_ORGANIZATION = "NULLIF(current_setting('app.current_organization_id', true), '')::uuid"
PURGE_SCOPE = "current_setting('app.worker_scope', true) = 'purge'"
MANAGED_TABLES = ("organization_memberships", "organization_invitations")
PURGE_ONLY_DELETE = ("support_access_requests", "organization_invitations")
EVIDENCE_COLUMNS = "id, organization_id, actor_user_account_id, support_access_id, action, target_type, target_id, request_id, occurred_at"


def upgrade() -> None:
    op.drop_constraint("ck_organizations_status", "organizations", type_="check")
    op.create_check_constraint("ck_organizations_status", "organizations", "status IN ('pending_activation', 'active', 'expired', 'pending_deletion', 'purged')")
    op.add_column("organizations", sa.Column("purged_at", sa.DateTime(timezone=True)))
    op.execute(
        f"""
        CREATE FUNCTION app_organization_live(row_organization_id uuid) RETURNS boolean
        LANGUAGE sql STABLE AS $$
            SELECT {PURGE_SCOPE}
                OR EXISTS (SELECT 1 FROM organizations WHERE id = row_organization_id AND status = 'active')
        $$
        """
    )
    for table in CONTENT_TABLES:
        op.execute(f"CREATE POLICY {table}_live_organization ON {table} AS RESTRICTIVE USING (app_organization_live(organization_id)) WITH CHECK (app_organization_live(organization_id))")
    for table in MANAGED_TABLES:
        live = f"({CURRENT_ORGANIZATION} IS NULL OR app_organization_live(organization_id))"
        op.execute(f"CREATE POLICY {table}_live_organization ON {table} AS RESTRICTIVE USING {live} WITH CHECK {live}")
    op.execute(
        f"""
        CREATE OR REPLACE FUNCTION reject_audit_event_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF TG_OP = 'UPDATE'
               AND {PURGE_SCOPE}
               AND NEW.change_summary = '{{}}'::jsonb
               AND ROW({", ".join(f"NEW.{column.strip()}" for column in EVIDENCE_COLUMNS.split(","))})
                   IS NOT DISTINCT FROM ROW({", ".join(f"OLD.{column.strip()}" for column in EVIDENCE_COLUMNS.split(","))})
            THEN
                RETURN NEW;
            END IF;
            RAISE EXCEPTION 'audit events are append-only';
        END;
        $$
        """
    )
    op.execute("GRANT UPDATE (change_summary) ON audit_events TO shadow_app")
    for table in PURGE_ONLY_DELETE:
        op.execute(f"GRANT DELETE ON {table} TO shadow_app")
        op.execute(f"CREATE POLICY {table}_purge ON {table} FOR DELETE USING (organization_id = {CURRENT_ORGANIZATION} AND {PURGE_SCOPE})")
    op.execute(f"CREATE POLICY audit_events_purge_scrub ON audit_events FOR UPDATE USING (organization_id = {CURRENT_ORGANIZATION} AND {PURGE_SCOPE}) WITH CHECK (organization_id = {CURRENT_ORGANIZATION} AND {PURGE_SCOPE})")


def downgrade() -> None:
    for table in PURGE_ONLY_DELETE:
        op.execute(f"DROP POLICY {table}_purge ON {table}")
        op.execute(f"REVOKE DELETE ON {table} FROM shadow_app")
    op.execute("DROP POLICY audit_events_purge_scrub ON audit_events")
    op.execute("REVOKE UPDATE (change_summary) ON audit_events FROM shadow_app")
    op.execute(
        """
        CREATE OR REPLACE FUNCTION reject_audit_event_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RAISE EXCEPTION 'audit events are append-only';
        END;
        $$
        """
    )
    for table in CONTENT_TABLES + MANAGED_TABLES:
        op.execute(f"DROP POLICY {table}_live_organization ON {table}")
    op.execute("DROP FUNCTION app_organization_live(uuid)")
    op.drop_column("organizations", "purged_at")
    op.execute("UPDATE organizations SET status = 'expired' WHERE status IN ('pending_deletion', 'purged')")
    op.drop_constraint("ck_organizations_status", "organizations", type_="check")
    op.create_check_constraint("ck_organizations_status", "organizations", "status IN ('pending_activation', 'active', 'expired')")
