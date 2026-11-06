"""Remember each user's recently opened Yearclocks (Yearclock V2, P2 ticket 01).

A visit belongs to one membership and one Yearclock and cascades away with
either, so removing a membership, deleting a Yearclock, or purging the
Organization removes it without needing RLS rights over another user's rows.
Rows are visible only to their own user inside their Organization, and only
while the Organization is live.

Revision ID: 0030
Revises: 0029
"""

import sqlalchemy as sa
from alembic import op


revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None

CURRENT_ORGANIZATION = "NULLIF(current_setting('app.current_organization_id', true), '')::uuid"
CURRENT_USER = "NULLIF(current_setting('app.current_user_account_id', true), '')::uuid"


def upgrade() -> None:
    op.create_table(
        "yearclock_visits",
        sa.Column("membership_id", sa.Uuid(), sa.ForeignKey("organization_memberships.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("yearclock_id", sa.Uuid(), sa.ForeignKey("yearclocks.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_account_id", sa.Uuid(), sa.ForeignKey("user_accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("visited_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_yearclock_visits_user_recent", "yearclock_visits", ["organization_id", "user_account_id", "visited_at"])
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON yearclock_visits TO shadow_app")
    op.execute("ALTER TABLE yearclock_visits ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE yearclock_visits FORCE ROW LEVEL SECURITY")
    own = f"organization_id = {CURRENT_ORGANIZATION} AND user_account_id = {CURRENT_USER}"
    op.execute(f"CREATE POLICY yearclock_visits_own ON yearclock_visits USING ({own}) WITH CHECK ({own})")
    op.execute("CREATE POLICY yearclock_visits_live_organization ON yearclock_visits AS RESTRICTIVE USING (app_organization_live(organization_id)) WITH CHECK (app_organization_live(organization_id))")


def downgrade() -> None:
    op.drop_table("yearclock_visits")
