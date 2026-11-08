"""Loading a Model's lines, events and metamodel for replay (ADR-0048); reads only.

Ticket 03 (read API) and ticket 05 (write validation) share this loader so both replay the same data.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AllowedConnection, ConnectionType, EventChange, ModelLine, NodeType, Organization, TimelineEvent
from app.timeline.chain import EventRecord, LineRecord, sort_events
from app.timeline.state import Change, Metamodel


@dataclass
class ModelTimeline:
    """Everything the engine needs for one Model: engine records plus the rows they came from."""

    lines: dict[UUID, LineRecord] = field(default_factory=dict)
    line_rows: dict[UUID, ModelLine] = field(default_factory=dict)
    events: dict[UUID, list[EventRecord]] = field(default_factory=dict)
    event_rows: dict[UUID, TimelineEvent] = field(default_factory=dict)
    metamodel: Metamodel = Metamodel(frozenset(), frozenset(), frozenset())

    def events_of(self, line_id: UUID) -> list[EventRecord]:
        """The line's own events in order (date, then entry order)."""
        return sort_events(self.events.get(line_id, ()))


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
    """Every line, event and change of the Model, and its metamodel (a Model's timeline is small; see the limits)."""
    line_rows = {row.id: row for row in session.scalars(select(ModelLine).where(ModelLine.model_id == model_id))}
    event_rows = {row.id: row for row in session.scalars(select(TimelineEvent).where(TimelineEvent.model_id == model_id))}
    changes: dict[UUID, list[Change]] = {}
    if event_rows:
        statement = select(EventChange).where(EventChange.event_id.in_(list(event_rows))).order_by(EventChange.event_id, EventChange.position)
        for row in session.scalars(statement):
            changes.setdefault(row.event_id, []).append(Change(row.op, row.element_id, row.payload or {}))
    events: dict[UUID, list[EventRecord]] = {}
    for row in event_rows.values():
        events.setdefault(row.line_id, []).append(EventRecord(row.id, row.line_id, row.occurred_on, row.seq, row.title, tuple(changes.get(row.id, ()))))
    return ModelTimeline(
        lines={row.id: LineRecord(row.id, row.parent_line_id, row.branch_event_id) for row in line_rows.values()},
        line_rows=line_rows,
        events=events,
        event_rows=event_rows,
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
    """An event dated after today (in the Organization's time zone) has not happened yet."""
    return occurred_on > today
