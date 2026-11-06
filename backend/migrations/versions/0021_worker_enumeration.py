"""Let background workers enumerate tenant identifiers read-only.

Workers must find which Organizations have due work before they can act in
one Organization's context. These permissive SELECT policies apply only when a
transaction sets ``app.worker_scope`` to ``enumerate``; request handlers never
set it, and every write still requires the normal Organization context.

Revision ID: 0021
Revises: 0020
"""

from alembic import op


revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None

ENUMERATE = "current_setting('app.worker_scope', true) = 'enumerate'"
TABLES = ("organizations", "event_series")


def upgrade() -> None:
    for table in TABLES:
        op.execute(f"CREATE POLICY {table}_worker_enumerate ON {table} FOR SELECT USING ({ENUMERATE})")


def downgrade() -> None:
    for table in TABLES:
        op.execute(f"DROP POLICY {table}_worker_enumerate ON {table}")
