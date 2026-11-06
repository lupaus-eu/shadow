"""Event Revisions (Yearclock V2, P4 ticket 01).

The state of an Event after each change, kept as customer content outside
the Audit Log (ADR-0014). Rows cascade with their Event, Yearclock, and
Organization and follow the content-table RLS set. Every existing Event gets
one baseline revision, written before RLS is enabled.

Revision ID: 0039
Revises: 0038
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY, JSONB


revision = "0039"
down_revision = "0038"
branch_labels = None
depends_on = None

CURRENT_ORGANIZATION = "NULLIF(current_setting('app.current_organization_id', true), '')::uuid"


def upgrade() -> None:
    op.create_table(
        "event_revisions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("yearclock_id", sa.Uuid(), sa.ForeignKey("yearclocks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_id", sa.Uuid(), sa.ForeignKey("events.id", ondelete="CASCADE"), nullable=False),
        sa.Column("series_id", sa.Uuid(), nullable=True),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("reason", sa.String(30), nullable=False),
        sa.Column("reason_detail", JSONB(), nullable=False, server_default="{}"),
        sa.Column("actor_account_id", sa.Uuid(), nullable=True),
        sa.Column("actor_kind", sa.String(10), nullable=False),
        sa.Column("snapshot", JSONB(), nullable=False),
        sa.Column("changed_fields", ARRAY(sa.String(20)), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("kind IN ('created', 'updated', 'deleted', 'restored', 'version_restored')", name="ck_event_revisions_kind"),
        sa.CheckConstraint("actor_kind IN ('member', 'support', 'system')", name="ck_event_revisions_actor_kind"),
    )
    op.create_index("ix_event_revisions_event_created", "event_revisions", ["event_id", "created_at"])
    op.create_index("ix_event_revisions_yearclock_created", "event_revisions", ["yearclock_id", "created_at"])
    op.execute(
        """
        INSERT INTO event_revisions (id, organization_id, yearclock_id, event_id, series_id, kind, reason, actor_kind, snapshot)
        SELECT gen_random_uuid(), e.organization_id, e.yearclock_id, e.id, o.series_id, 'created', 'baseline', 'system',
               jsonb_build_object(
                   'title', e.title, 'starts_on', e.starts_on, 'ends_on', e.ends_on, 'lane_id', e.lane_id,
                   'category_id', e.category_id, 'description', e.description, 'external_url', e.external_url,
                   'label_ids', COALESCE((SELECT jsonb_agg(l.label_id ORDER BY l.label_id::text) FROM event_labels l WHERE l.event_id = e.id), '[]'::jsonb),
                   'deleted', e.deleted_at IS NOT NULL, 'skipped', COALESCE(o.skipped, false))
        FROM events e LEFT JOIN series_occurrences o ON o.event_id = e.id
        """
    )
    op.execute("GRANT SELECT, INSERT, DELETE ON event_revisions TO yearclock_app")
    op.execute("ALTER TABLE event_revisions ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE event_revisions FORCE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY event_revisions_policy ON event_revisions USING (organization_id = {CURRENT_ORGANIZATION}) WITH CHECK (organization_id = {CURRENT_ORGANIZATION})")
    op.execute("CREATE POLICY event_revisions_live_organization ON event_revisions AS RESTRICTIVE USING (app_organization_live(organization_id)) WITH CHECK (app_organization_live(organization_id))")
    op.execute("CREATE POLICY event_revisions_support_select ON event_revisions AS RESTRICTIVE FOR SELECT USING (app_support_grant_allows(false))")
    op.execute("CREATE POLICY event_revisions_support_insert ON event_revisions AS RESTRICTIVE FOR INSERT WITH CHECK (app_support_grant_allows(true))")
    op.execute("CREATE POLICY event_revisions_support_delete ON event_revisions AS RESTRICTIVE FOR DELETE USING (app_support_grant_allows(true))")


def downgrade() -> None:
    op.drop_table("event_revisions")
