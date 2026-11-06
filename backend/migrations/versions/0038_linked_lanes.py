"""Linked Lanes (Yearclock V2, P3 ticket 05).

A Linked Lane shows another Yearclock's Lane live and read only. Removing
the Source Lane, or purging its Yearclock, removes the link with it.

Revision ID: 0038
Revises: 0037
"""

import sqlalchemy as sa
from alembic import op


revision = "0038"
down_revision = "0037"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("lanes", sa.Column("source_lane_id", sa.Uuid(), nullable=True))
    op.create_foreign_key("fk_lanes_source_lane", "lanes", "lanes", ["source_lane_id"], ["id"], ondelete="CASCADE")
    op.create_check_constraint("ck_lanes_not_own_source", "lanes", "source_lane_id IS NULL OR source_lane_id <> id")
    op.create_index("ix_lanes_source_lane_id", "lanes", ["source_lane_id"])


def downgrade() -> None:
    op.drop_index("ix_lanes_source_lane_id", table_name="lanes")
    op.drop_constraint("ck_lanes_not_own_source", "lanes", type_="check")
    op.drop_constraint("fk_lanes_source_lane", "lanes", type_="foreignkey")
    op.drop_column("lanes", "source_lane_id")
