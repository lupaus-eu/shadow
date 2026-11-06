"""The two switches that stop MCP traffic for one Organization (ADR-0037; tech-mcp-interface ticket 04).

``mcp_enabled`` is set by the Organization's Owners and Admins (on by default);
``mcp_platform_blocked`` by a Platform administrator (off by default). MCP works only
while the first is on and the second is off.

Revision ID: 0048
Revises: 0047
"""

import sqlalchemy as sa
from alembic import op


revision = "0048"
down_revision = "0047"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("organizations", sa.Column("mcp_enabled", sa.Boolean(), server_default="true", nullable=False))
    op.add_column("organizations", sa.Column("mcp_platform_blocked", sa.Boolean(), server_default="false", nullable=False))


def downgrade() -> None:
    op.drop_column("organizations", "mcp_platform_blocked")
    op.drop_column("organizations", "mcp_enabled")
