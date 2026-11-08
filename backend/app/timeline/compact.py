"""Tidy the changes inside one event without changing what the event does (ADR-0049).

Folds an update into the add of the same node, merges repeated updates of one element, and drops an
element that the event both adds and removes together with every change that touches it. Every
candidate is replayed on the state the event starts from; if it fails or ends differently, the changes
are returned unchanged.
"""

from collections.abc import Sequence
from uuid import UUID

from app.timeline.errors import ChangeInvalid
from app.timeline.state import Change, Metamodel, State, apply_changes


def compact(changes: Sequence[Change], base: State, metamodel: Metamodel) -> list[Change]:
    original = list(changes)
    try:
        expected = apply_changes(base, original, metamodel)
    except ChangeInvalid:
        return original
    candidate = _drop_short_lived(_merge_updates(original))
    if candidate == original:
        return original
    try:
        result = apply_changes(base, candidate, metamodel)
    except ChangeInvalid:
        return original
    return candidate if (result.nodes, result.connections) == (expected.nodes, expected.connections) else original


def _merge_updates(changes: list[Change]) -> list[Change]:
    merged: list[Change] = []
    for change in changes:
        if change.op == "update_node":
            earlier = next((i for i in range(len(merged) - 1, -1, -1) if merged[i].element_id == change.element_id and merged[i].op in ("add_node", "update_node")), None)
            if earlier is not None:
                target = merged[earlier]
                merged[earlier] = Change(target.op, target.element_id, {**target.payload, **change.payload})
                continue
        merged.append(change)
    return merged


def _drop_short_lived(changes: list[Change]) -> list[Change]:
    added: dict[UUID, int] = {}
    doomed: set[UUID] = set()
    for index, change in enumerate(changes):
        if change.op in ("add_node", "add_connection"):
            added[change.element_id] = index
        elif change.op in ("remove_node", "remove_connection") and change.element_id in added:
            doomed.add(change.element_id)
    if not doomed:
        return changes
    # A connection added in the event whose end is a doomed node cannot outlive it either.
    for change in changes:
        if change.op == "add_connection" and {UUID(str(change.payload["source_node_id"])), UUID(str(change.payload["target_node_id"]))} & doomed:
            doomed.add(change.element_id)

    def touches(change: Change) -> bool:
        if change.element_id in doomed:
            return True
        return any(UUID(str(change.payload[key])) in doomed for key in ("source_node_id", "target_node_id") if change.payload.get(key))

    return [change for change in changes if not touches(change)]
