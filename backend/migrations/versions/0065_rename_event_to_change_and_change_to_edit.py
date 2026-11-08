"""Rename the model timeline's tables to the Change vocabulary (ADR-0052, tech-change-terminology ticket 01).

The dated item of a line is a **Change** and its steps are **Edits**, so ``timeline_events`` becomes
``timeline_changes`` and ``event_changes`` becomes ``change_edits``. The columns follow:
``change_edits.event_id`` becomes ``change_id`` and ``model_lines.branch_event_id`` becomes
``branch_change_id``. Every dependent object whose name carries the old words is renamed with them: primary
keys, unique, check, not-null and foreign key constraints (including ``fk_model_lines_branch_event``), indexes
(``ix_timeline_events_line_order``), the row-level security policies, and the identity sequence. Objects are
found in the catalog and renamed by the same word mapping, so a server that does not name its not-null
constraints simply has fewer of them.

No data moves and nothing is copied: only names change, so row-level security, grants, foreign keys and the
check constraint of ``model_lines`` (whose expression follows the renamed column) keep working. Migrations 0060
to 0064 keep their historical names and docstrings; the Audit Event table and the ``event.*`` audit actions of
rows already written are not touched (the Activity view reads both ``event.*`` and ``change.*``).

Downgrade renames everything back with the reverse mapping.

Revision ID: 0065
Revises: 0064
"""

import sqlalchemy as sa
from alembic import op


revision = "0065"
down_revision = "0064"
branch_labels = None
depends_on = None

TABLES = (("timeline_events", "timeline_changes"), ("event_changes", "change_edits"))
COLUMNS = (("change_edits", "event_id", "change_id"), ("model_lines", "branch_event_id", "branch_change_id"))
# Longest first; applied to the names of objects that belong to the four timeline tables.
WORDS = (("timeline_events", "timeline_changes"), ("event_changes", "change_edits"), ("branch_event", "branch_change"), ("event_id", "change_id"), ("event_position", "change_position"))
OWNERS = ("timeline_events", "event_changes", "model_lines", "node_positions")


def _renamed(name: str, words) -> str:
    for old, new in words:
        name = name.replace(old, new)
    return name


def _rename_objects(owners: tuple[str, ...], words) -> None:
    connection = op.get_bind()
    constraints = connection.execute(
        sa.text("SELECT c.conrelid::regclass::text, c.conname FROM pg_constraint c WHERE c.conrelid::regclass::text = ANY(:owners) ORDER BY c.conname"),
        {"owners": list(owners)},
    ).all()
    for table, name in constraints:
        new = _renamed(name, words)
        if new != name:
            op.execute(f'ALTER TABLE {table} RENAME CONSTRAINT "{name}" TO "{new}"')
    indexes = connection.execute(
        sa.text("SELECT indexname FROM pg_indexes WHERE schemaname = current_schema() AND tablename = ANY(:owners) ORDER BY indexname"),
        {"owners": list(owners)},
    ).all()
    for (name,) in indexes:
        new = _renamed(name, words)
        if new != name:
            op.execute(f'ALTER INDEX "{name}" RENAME TO "{new}"')
    policies = connection.execute(
        sa.text("SELECT tablename, policyname FROM pg_policies WHERE schemaname = current_schema() AND tablename = ANY(:owners) ORDER BY policyname"),
        {"owners": list(owners)},
    ).all()
    for table, name in policies:
        new = _renamed(name, words)
        if new != name:
            op.execute(f'ALTER POLICY "{name}" ON {table} RENAME TO "{new}"')
    sequences = connection.execute(
        sa.text("SELECT relname FROM pg_class WHERE relkind = 'S' AND relnamespace = current_schema()::regnamespace AND (relname LIKE 'timeline_events%' OR relname LIKE 'timeline_changes%')"),
    ).all()
    for (name,) in sequences:
        new = _renamed(name, words)
        if new != name:
            op.execute(f'ALTER SEQUENCE "{name}" RENAME TO "{new}"')


def upgrade() -> None:
    for old, new in TABLES:
        op.rename_table(old, new)
    for table, old, new in COLUMNS:
        op.alter_column(table, old, new_column_name=new)
    _rename_objects(("timeline_changes", "change_edits", "model_lines", "node_positions"), WORDS)


def downgrade() -> None:
    reverse = tuple((new, old) for old, new in WORDS)
    _rename_objects(("timeline_changes", "change_edits", "model_lines", "node_positions"), reverse)
    for table, old, new in reversed(COLUMNS):
        op.alter_column(table, new, new_column_name=old)
    for old, new in reversed(TABLES):
        op.rename_table(new, old)
