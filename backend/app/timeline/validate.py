"""Validating a write to a Model's timeline by replaying every chain it can affect (ADR-0049).

``validate_model`` takes the Model's whole timeline, applies a mutation to a copy of the events in memory,
and replays the changed line and every line that branches from it, directly or through other Scenarios,
checking the branch and dated-order rules on the way. It raises ``ChainRefused`` (carrying the structured
refusal) at the first failure and changes nothing; the caller saves only when it returns. The caller holds the Model row lock (the validity of
one event depends on every other event in the chain), so two writers cannot each pass the check and
together break it.

``describe_break`` turns a ``ChainBroken`` into the structured refusal the interface words in Finnish and
English: machine-readable codes and the ids and names a message needs, never prose.
"""

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ConnectionType, NodeType
from app.timeline.chain import EventRecord, EventsByLine, Lines, chain_events, descendants, sort_events, validate_lines
from app.timeline.errors import ChainBroken
from app.timeline.loader import ModelTimeline, load_timeline

MutableEvents = dict[UUID, list[EventRecord]]

# What the person should do first, per cause (a stable code; the interface words it).
HINTS = {
    "missing_element": "add_element_before",
    "duplicate_element": "remove_duplicate_add",
    "missing_type": "choose_existing_type",
    "connection_not_allowed": "choose_allowed_connection",
    "missing_endpoint": "add_endpoint_before",
    "self_connection": "choose_different_ends",
    "duplicate_connection": "remove_duplicate_connection",
    "missing_branch_event": "restore_branch_event",
    "before_branch_event": "move_after_branch_event",
}


@dataclass(frozen=True)
class Mutation:
    """A change to the events of one line, applied in memory to a copy of every line's events."""

    line_id: UUID
    apply: Callable[[MutableEvents], None]


@dataclass
class Validation:
    timeline: ModelTimeline
    events: MutableEvents  # every line's events after the mutation
    restarted: list[UUID] = field(default_factory=list)  # Scenarios whose starting point changed


class ChainRefused(Exception):
    """A write would break a chain; ``detail`` is the structured 422 answer (see ``describe_break``)."""

    def __init__(self, detail: dict[str, Any]) -> None:
        super().__init__(detail["cause"])
        self.detail = detail


def _start_signature(lines: Lines, events: EventsByLine, line_id: UUID) -> tuple:
    """What a Scenario starts from: the events before it and what each one does."""
    line = lines[line_id]
    return tuple((event.id, event.changes) for event in chain_events(lines, events, line.parent_line_id, line.branch_event_id))


def validate_model(session: Session, model_id: UUID, mutation: Mutation, *, timeline: ModelTimeline | None = None) -> Validation:
    """Apply ``mutation`` in memory, replay what it can affect, and report the Scenarios whose start changed.

    ``timeline`` is the already loaded timeline of the (locked) Model; it is loaded here when not given.
    """
    timeline = timeline or load_timeline(session, model_id)
    after: MutableEvents = {line_id: list(items) for line_id, items in timeline.events.items()}
    mutation.apply(after)
    dependent = descendants(timeline.lines, mutation.line_id)
    try:
        validate_lines(timeline.lines, after, timeline.metamodel, [mutation.line_id, *dependent])
    except ChainBroken as error:
        raise ChainRefused(describe_break(error, Validation(timeline, after), mutation.line_id, load_type_names(session, model_id))) from error
    restarted = [line_id for line_id in dependent if _start_signature(timeline.lines, timeline.events, line_id) != _start_signature(timeline.lines, after, line_id)]
    return Validation(timeline, after, restarted)


def load_type_names(session: Session, model_id: UUID) -> dict[UUID, str]:
    """Names of the Model's node and connection types, for refusal messages."""
    rows = [*session.execute(select(NodeType.id, NodeType.name).where(NodeType.model_id == model_id)), *session.execute(select(ConnectionType.id, ConnectionType.name).where(ConnectionType.model_id == model_id))]
    return {row[0]: row[1] for row in rows}


def _node_name(element_id: UUID, sequences: Iterable[Sequence[EventRecord]], failing: tuple[UUID | None, int | None]) -> str | None:
    """The latest name any event gave the node, looking in the first sequence that mentions it.

    The failing change itself and the changes after it in its event are left out: a duplicate add must not rename the node it duplicates.
    """
    for events in sequences:
        found: str | None = None
        for event in events:
            for index, change in enumerate(event.changes):
                if event.id == failing[0] and failing[1] is not None and index >= failing[1]:
                    break
                if change.element_id == element_id and change.op in ("add_node", "update_node") and change.payload.get("name"):
                    found = str(change.payload["name"])
        if found is not None:
            return found
    return None


def _uuid(value: Any) -> UUID | None:
    try:
        return UUID(str(value)) if value else None
    except ValueError:
        return None


def describe_break(error: ChainBroken, validation: Validation, written_line_id: UUID, type_names: dict[UUID, str] | None = None) -> dict[str, Any]:
    """The 422 ``chain_broken`` detail: ids for the machine, titles and names for the message, a hint code for what to do first."""
    timeline, after = validation.timeline, validation.events
    names = type_names or {}

    def find(events: EventsByLine) -> EventRecord | None:
        return next((event for items in events.values() for event in items if event.id == error.event_id), None)

    event = find(after) or find(timeline.events)
    line_row = timeline.line_rows.get(error.line_id)
    change = event.changes[error.position] if event is not None and error.position is not None and error.position < len(event.changes) else None

    def chain(events: EventsByLine) -> list[EventRecord]:
        try:
            return chain_events(timeline.lines, events, error.line_id)
        except ChainBroken:
            return []

    everything = [sort_events([item for items in events.values() for item in items]) for events in (after, timeline.events)]
    sequences = [chain(after), chain(timeline.events), *everything]

    def name_of(raw: Any) -> str | None:
        element = raw if isinstance(raw, UUID) else _uuid(raw)
        return _node_name(element, sequences, (error.event_id, error.position)) if element is not None else None

    element_kind: str | None = None
    if error.cause in ("missing_element", "duplicate_element"):
        element_kind = "node" if change is not None and change.op.endswith("_node") else "connection"
    elif error.cause == "missing_endpoint":
        element_kind = "node"
    elif error.cause == "missing_type":
        element_kind = "type"
    elif error.cause in ("connection_not_allowed", "self_connection", "duplicate_connection"):
        element_kind = "connection"
    payload = change.payload if change is not None else {}
    branch_event = next((item for item in timeline.events.get(line_row.parent_line_id, ()) if item.id == line_row.branch_event_id), None) if line_row is not None and line_row.parent_line_id else None
    type_id = _uuid(payload.get("connection_type_id") or payload.get("node_type_id")) if payload else None
    hint: dict[str, Any] = {
        "code": HINTS.get(error.cause, "fix_event"),
        "event_title": event.title if event is not None else None,
        "event_date": event.occurred_on.isoformat() if event is not None else None,
        "op": change.op if change is not None else None,
        "line_name": line_row.name if line_row is not None else None,
        "line_kind": line_row.kind if line_row is not None else None,
        "scenario_name": line_row.name if line_row is not None and line_row.kind == "scenario" else None,
        "in_other_line": error.line_id != written_line_id,
        "element_kind": element_kind,
        "element_name": name_of(error.element_id) if element_kind in ("node", None) else None,
        "type_name": names.get(type_id) if type_id is not None else None,
        "source_name": name_of(payload.get("source_node_id")),
        "target_name": name_of(payload.get("target_node_id")),
        "branch_event_title": branch_event.title if branch_event is not None else None,
        "branch_event_date": branch_event.occurred_on.isoformat() if branch_event is not None else None,
    }
    return {
        "reason": "chain_broken",
        "event": str(error.event_id) if error.event_id else None,
        "line": str(error.line_id),
        "position": error.position,
        "element": str(error.element_id) if error.element_id else None,
        "cause": error.cause,
        "hint": hint,
    }


def next_seq(timeline: ModelTimeline) -> int:
    """The entry number a new event gets: after every existing one (the identity column only ever grows)."""
    return max((event.seq for items in timeline.events.values() for event in items), default=0) + 1
