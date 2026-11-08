"""Loading a Model's lines, changes and metamodel for replay (ADR-0048); reads only.

Ticket 03 (read API) and ticket 05 (write validation) share this loader so both replay the same data.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AllowedConnection, ConnectionType, ChangeEdit, ModelLine, NodeType, Organization, TimelineChange
from app.timeline.chain import ChangeRecord, LineRecord, sort_changes
from app.timeline.state import Edit, Metamodel


@dataclass
class ModelTimeline:
    """Everything the engine needs for one Model: engine records plus the rows they came from."""

    lines: dict[UUID, LineRecord] = field(default_factory=dict)
    line_rows: dict[UUID, ModelLine] = field(default_factory=dict)
    changes: dict[UUID, list[ChangeRecord]] = field(default_factory=dict)
    change_rows: dict[UUID, TimelineChange] = field(default_factory=dict)
    metamodel: Metamodel = Metamodel(frozenset(), frozenset(), frozenset())

    def changes_of(self, line_id: UUID) -> list[ChangeRecord]:
        """The line's own changes in order (date, then entry order)."""
        return sort_changes(self.changes.get(line_id, ()))


def load_metamodel(session: Session, model_id: UUID) -> Metamodel:
    return Metamodel(
        frozenset(session.scalars(select(NodeType.id).where(NodeType.model_id == model_id))),
        frozenset(session.scalars(select(ConnectionType.id).where(ConnectionType.model_id == model_id))),
        frozenset(
            (row.connection_type_id, row.source_node_type_id, row.target_node_type_id)
            for row in session.scalars(select(AllowedConnection).where(AllowedConnection.model_id == model_id))
        ),
    )


def load_timeline(session: Session, model_id: UUID) -> ModelTimeline:
    """Every line, change and edit of the Model, and its metamodel (a Model's timeline is small; see the limits)."""
    line_rows = {row.id: row for row in session.scalars(select(ModelLine).where(ModelLine.model_id == model_id))}
    change_rows = {row.id: row for row in session.scalars(select(TimelineChange).where(TimelineChange.model_id == model_id))}
    edits: dict[UUID, list[Edit]] = {}
    if change_rows:
        statement = select(ChangeEdit).where(ChangeEdit.change_id.in_(list(change_rows))).order_by(ChangeEdit.change_id, ChangeEdit.position)
        for row in session.scalars(statement):
            edits.setdefault(row.change_id, []).append(Edit(row.op, row.element_id, row.payload or {}))
    changes: dict[UUID, list[ChangeRecord]] = {}
    for row in change_rows.values():
        changes.setdefault(row.line_id, []).append(ChangeRecord(row.id, row.line_id, row.occurred_on, row.seq, row.title, tuple(edits.get(row.id, ()))))
    return ModelTimeline(
        lines={row.id: LineRecord(row.id, row.parent_line_id, row.branch_change_id) for row in line_rows.values()},
        line_rows=line_rows,
        changes=changes,
        change_rows=change_rows,
        metamodel=load_metamodel(session, model_id),
    )


def today_in_organization(session: Session, organization_id: UUID, clock: Callable[[], datetime]) -> date:
    """Today's date in the Organization's time zone (UTC if the zone is unknown); ``clock`` is injected in tests."""
    name = session.scalar(select(Organization.time_zone).where(Organization.id == organization_id))
    try:
        zone = ZoneInfo(name) if name else ZoneInfo("UTC")
    except ZoneInfoNotFoundError:
        zone = ZoneInfo("UTC")
    return clock().astimezone(zone).date()


def is_planned(occurred_on: date, today: date) -> bool:
    """A change dated after today (in the Organization's time zone) has not happened yet."""
    return occurred_on > today
