"""Tidy the edits inside one change without changing what the change does (ADR-0049).

Folds an update into the add of the same node, merges repeated updates of one element, folds a re-route
or a type edit into the add of the same connection (and repeated re-routes or type edits into one), and
drops an element that the change both adds and removes together with every edit that touches it. Every
candidate is replayed on the state the change starts from; if it fails or ends differently, the edits
are returned unchanged.
"""

from collections.abc import Sequence
from uuid import UUID

from app.timeline.errors import EditInvalid
from app.timeline.state import Edit, Metamodel, State, apply_edits


def compact(edits: Sequence[Edit], base: State, metamodel: Metamodel) -> list[Edit]:
    original = list(edits)
    try:
        expected = apply_edits(base, original, metamodel)
    except EditInvalid:
        return original
    try:
        candidate = _drop_noops(_drop_short_lived(_merge_connection_edits(_merge_updates(original))), base, metamodel)
        if candidate == original:
            return original
        result = apply_edits(base, candidate, metamodel)
    except EditInvalid:
        return original
    return candidate if (result.nodes, result.connections) == (expected.nodes, expected.connections) else original


def _drop_noops(edits: list[Edit], base: State, metamodel: Metamodel) -> list[Edit]:
    """Leave out an update, re-route or type edit that finds the state unchanged; the rest is replayed on the way."""
    state, kept = base, []
    for edit in edits:
        after = apply_edits(state, [edit], metamodel)
        if edit.op in ("update_node", "reroute_connection", "change_connection_type") and (after.nodes, after.connections) == (state.nodes, state.connections):
            continue
        state = after
        kept.append(edit)
    return kept


def _merge_updates(edits: list[Edit]) -> list[Edit]:
    merged: list[Edit] = []
    for edit in edits:
        if edit.op == "update_node":
            earlier = next((i for i in range(len(merged) - 1, -1, -1) if merged[i].element_id == edit.element_id and merged[i].op in ("add_node", "update_node")), None)
            if earlier is not None:
                target = merged[earlier]
                merged[earlier] = Edit(target.op, target.element_id, {**target.payload, **edit.payload})
                continue
        merged.append(edit)
    return merged


def _merge_connection_edits(edits: list[Edit]) -> list[Edit]:
    """A re-route or a type edit joins the latest earlier add, or edit of the same kind, of that connection."""
    merged: list[Edit] = []
    for edit in edits:
        if edit.op in ("reroute_connection", "change_connection_type"):
            earlier = next((i for i in range(len(merged) - 1, -1, -1) if merged[i].element_id == edit.element_id and merged[i].op in ("add_connection", edit.op)), None)
            if earlier is not None:
                target = merged[earlier]
                merged[earlier] = Edit(target.op, target.element_id, {**target.payload, **edit.payload})
                continue
        merged.append(edit)
    return merged


def _drop_short_lived(edits: list[Edit]) -> list[Edit]:
    added: dict[UUID, int] = {}
    doomed: set[UUID] = set()
    for index, edit in enumerate(edits):
        if edit.op in ("add_node", "add_connection"):
            added[edit.element_id] = index
        elif edit.op in ("remove_node", "remove_connection") and edit.element_id in added:
            doomed.add(edit.element_id)
    if not doomed:
        return edits
    # A connection added in the change whose end is a doomed node cannot outlive it either.
    for edit in edits:
        if edit.op == "add_connection" and {UUID(str(edit.payload["source_node_id"])), UUID(str(edit.payload["target_node_id"]))} & doomed:
            doomed.add(edit.element_id)

    def touches(edit: Edit) -> bool:
        if edit.element_id in doomed:
            return True
        return any(UUID(str(edit.payload[key])) in doomed for key in ("source_node_id", "target_node_id") if edit.payload.get(key))

    return [edit for edit in edits if not touches(edit)]
