"""Chains of changes and their replay (ADR-0048, ADR-0049); pure, no database."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from uuid import UUID

from app.timeline.errors import ChainBroken, EditInvalid
from app.timeline.state import Edit, Metamodel, State, apply_edit


@dataclass(frozen=True)
class ChangeRecord:
    id: UUID
    line_id: UUID
    occurred_on: date
    seq: int
    title: str
    edits: tuple[Edit, ...] = ()


@dataclass(frozen=True)
class LineRecord:
    id: UUID
    parent_line_id: UUID | None = None
    branch_change_id: UUID | None = None


Lines = Mapping[UUID, LineRecord]
ChangesByLine = Mapping[UUID, Sequence[ChangeRecord]]


def sort_changes(changes: Sequence[ChangeRecord]) -> list[ChangeRecord]:
    """Changes by date, then by the order they were entered in."""
    return sorted(changes, key=lambda change: (change.occurred_on, change.seq))


def chain_changes(lines: Lines, changes_by_line: ChangesByLine, line_id: UUID, until_change_id: UUID | None = None) -> list[ChangeRecord]:
    """The changes a state is computed from: the ancestors' changes up to each branch change, then the line's own.

    With ``until_change_id`` the chain stops after that change of the line; without it, the whole line is included.
    """
    return _chain(lines, changes_by_line, line_id, until_change_id, frozenset())


def _chain(lines: Lines, changes_by_line: ChangesByLine, line_id: UUID, until_change_id: UUID | None, seen: frozenset[UUID]) -> list[ChangeRecord]:
    if line_id in seen or line_id not in lines:
        raise ChainBroken(line_id, None, None, "missing_branch_change")
    line = lines[line_id]
    own = sort_changes(changes_by_line.get(line_id, ()))
    if until_change_id is not None:
        index = next((i for i, change in enumerate(own) if change.id == until_change_id), None)
        if index is None:
            raise ChainBroken(line_id, until_change_id, None, "missing_branch_change")
        own = own[: index + 1]
    prefix: list[ChangeRecord] = []
    if line.parent_line_id is not None:
        if line.branch_change_id is None:
            raise ChainBroken(line_id, None, None, "missing_branch_change")
        prefix = _chain(lines, changes_by_line, line.parent_line_id, line.branch_change_id, seen | {line_id})
    return prefix + own


def replay(chain: Sequence[ChangeRecord], metamodel: Metamodel) -> State:
    """The state after a chain; raises ``ChainBroken`` naming the change, edit position and cause where it fails."""
    state = State()
    for change in chain:
        for position, edit in enumerate(change.edits):
            try:
                apply_edit(state, edit, metamodel)
            except EditInvalid as error:
                raise ChainBroken(change.line_id, change.id, position, error.cause, error.element_id) from error
    return state


def state_after(lines: Lines, changes_by_line: ChangesByLine, metamodel: Metamodel, line_id: UUID, change_id: UUID | None = None) -> State:
    """The state after one change of a line (after its last change when none is named)."""
    return replay(chain_changes(lines, changes_by_line, line_id, change_id), metamodel)


def state_as_of(lines: Lines, changes_by_line: ChangesByLine, metamodel: Metamodel, line_id: UUID, day: date) -> State:
    """The state after the last change of the line dated on or before ``day``.

    Before the line's first own change that is the state at its branch point (an empty state for the Base line).
    """
    own = [change for change in sort_changes(changes_by_line.get(line_id, ())) if change.occurred_on <= day]
    if own:
        return state_after(lines, changes_by_line, metamodel, line_id, own[-1].id)
    line = lines[line_id]
    if line.parent_line_id is None:
        return State()
    return replay(chain_changes(lines, changes_by_line, line.parent_line_id, line.branch_change_id), metamodel)


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


def validate_lines(lines: Lines, changes_by_line: ChangesByLine, metamodel: Metamodel, line_ids: Sequence[UUID] | None = None) -> None:
    """Replay each line to its last change and check its branch rules; raises ``ChainBroken`` at the first failure.

    A Scenario's branch change must exist in its parent, and its own changes must not be dated before it.
    """
    for line_id in line_ids if line_ids is not None else list(lines):
        line = lines[line_id]
        if line.parent_line_id is not None:
            parent_changes = {change.id: change for change in changes_by_line.get(line.parent_line_id, ())}
            branch = parent_changes.get(line.branch_change_id) if line.branch_change_id else None
            if branch is None:
                raise ChainBroken(line_id, line.branch_change_id, None, "missing_branch_change")
            for change in sort_changes(changes_by_line.get(line_id, ())):
                if change.occurred_on < branch.occurred_on:
                    raise ChainBroken(line_id, change.id, None, "before_branch_change")
        replay(chain_changes(lines, changes_by_line, line_id), metamodel)


def branch_prefix(lines: Lines, changes_by_line: ChangesByLine, line_id: UUID) -> tuple[UUID, ...]:
    """The ids of the changes a Scenario starts from, in order; compare before and after a write to notice a changed start."""
    line = lines[line_id]
    if line.parent_line_id is None:
        return ()
    return tuple(change.id for change in chain_changes(lines, changes_by_line, line.parent_line_id, line.branch_change_id))
