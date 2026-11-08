"""Chains of events and their replay (ADR-0048, ADR-0049); pure, no database."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from uuid import UUID

from app.timeline.errors import ChainBroken, ChangeInvalid
from app.timeline.state import Change, Metamodel, State, apply_change


@dataclass(frozen=True)
class EventRecord:
    id: UUID
    line_id: UUID
    occurred_on: date
    seq: int
    title: str
    changes: tuple[Change, ...] = ()


@dataclass(frozen=True)
class LineRecord:
    id: UUID
    parent_line_id: UUID | None = None
    branch_event_id: UUID | None = None


Lines = Mapping[UUID, LineRecord]
EventsByLine = Mapping[UUID, Sequence[EventRecord]]


def sort_events(events: Sequence[EventRecord]) -> list[EventRecord]:
    """Events by date, then by the order they were entered in."""
    return sorted(events, key=lambda event: (event.occurred_on, event.seq))


def chain_events(lines: Lines, events_by_line: EventsByLine, line_id: UUID, until_event_id: UUID | None = None) -> list[EventRecord]:
    """The events a state is computed from: the ancestors' events up to each branch event, then the line's own.

    With ``until_event_id`` the chain stops after that event of the line; without it, the whole line is included.
    """
    return _chain(lines, events_by_line, line_id, until_event_id, frozenset())


def _chain(lines: Lines, events_by_line: EventsByLine, line_id: UUID, until_event_id: UUID | None, seen: frozenset[UUID]) -> list[EventRecord]:
    if line_id in seen or line_id not in lines:
        raise ChainBroken(line_id, None, None, "missing_branch_event")
    line = lines[line_id]
    own = sort_events(events_by_line.get(line_id, ()))
    if until_event_id is not None:
        index = next((i for i, event in enumerate(own) if event.id == until_event_id), None)
        if index is None:
            raise ChainBroken(line_id, until_event_id, None, "missing_branch_event")
        own = own[: index + 1]
    prefix: list[EventRecord] = []
    if line.parent_line_id is not None:
        if line.branch_event_id is None:
            raise ChainBroken(line_id, None, None, "missing_branch_event")
        prefix = _chain(lines, events_by_line, line.parent_line_id, line.branch_event_id, seen | {line_id})
    return prefix + own


def replay(chain: Sequence[EventRecord], metamodel: Metamodel) -> State:
    """The state after a chain; raises ``ChainBroken`` naming the event, change position and cause where it fails."""
    state = State()
    for event in chain:
        for position, change in enumerate(event.changes):
            try:
                apply_change(state, change, metamodel)
            except ChangeInvalid as error:
                raise ChainBroken(event.line_id, event.id, position, error.cause, error.element_id) from error
    return state


def state_after(lines: Lines, events_by_line: EventsByLine, metamodel: Metamodel, line_id: UUID, event_id: UUID | None = None) -> State:
    """The state after one event of a line (after its last event when none is named)."""
    return replay(chain_events(lines, events_by_line, line_id, event_id), metamodel)


def state_as_of(lines: Lines, events_by_line: EventsByLine, metamodel: Metamodel, line_id: UUID, day: date) -> State:
    """The state after the last event of the line dated on or before ``day``.

    Before the line's first own event that is the state at its branch point (an empty state for the Base line).
    """
    own = [event for event in sort_events(events_by_line.get(line_id, ())) if event.occurred_on <= day]
    if own:
        return state_after(lines, events_by_line, metamodel, line_id, own[-1].id)
    line = lines[line_id]
    if line.parent_line_id is None:
        return State()
    return replay(chain_events(lines, events_by_line, line.parent_line_id, line.branch_event_id), metamodel)


def descendants(lines: Lines, line_id: UUID) -> list[UUID]:
    """Every line that branches from the line, directly or through other Scenarios."""
    found: list[UUID] = []
    frontier = [line_id]
    while frontier:
        current = frontier.pop()
        for candidate in lines.values():
            if candidate.parent_line_id == current and candidate.id not in found:
                found.append(candidate.id)
                frontier.append(candidate.id)
    return found


def validate_lines(lines: Lines, events_by_line: EventsByLine, metamodel: Metamodel, line_ids: Sequence[UUID] | None = None) -> None:
    """Replay each line to its last event and check its branch rules; raises ``ChainBroken`` at the first failure.

    A Scenario's branch event must exist in its parent, and its own events must not be dated before it.
    """
    for line_id in line_ids if line_ids is not None else list(lines):
        line = lines[line_id]
        if line.parent_line_id is not None:
            parent_events = {event.id: event for event in events_by_line.get(line.parent_line_id, ())}
            branch = parent_events.get(line.branch_event_id) if line.branch_event_id else None
            if branch is None:
                raise ChainBroken(line_id, line.branch_event_id, None, "missing_branch_event")
            for event in sort_events(events_by_line.get(line_id, ())):
                if event.occurred_on < branch.occurred_on:
                    raise ChainBroken(line_id, event.id, None, "before_branch_event")
        replay(chain_events(lines, events_by_line, line_id), metamodel)


def branch_prefix(lines: Lines, events_by_line: EventsByLine, line_id: UUID) -> tuple[UUID, ...]:
    """The ids of the events a Scenario starts from, in order; compare before and after a write to notice a changed start."""
    line = lines[line_id]
    if line.parent_line_id is None:
        return ()
    return tuple(event.id for event in chain_events(lines, events_by_line, line.parent_line_id, line.branch_event_id))
