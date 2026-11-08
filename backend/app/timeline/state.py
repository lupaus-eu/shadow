"""The graph after some changes, and how one edit moves it (pure; no database)."""

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from app.timeline.errors import EditInvalid
from app.timeline.payloads import AddConnection, AddNode, ChangeConnectionType, RerouteConnection, UpdateNode, parse_payload


@dataclass(frozen=True)
class NodeState:
    id: UUID
    node_type_id: UUID
    name: str
    description: str | None
    x: float
    y: float


@dataclass(frozen=True)
class ConnectionState:
    id: UUID
    connection_type_id: UUID
    source_node_id: UUID
    target_node_id: UUID


@dataclass
class State:
    nodes: dict[UUID, NodeState] = field(default_factory=dict)
    connections: dict[UUID, ConnectionState] = field(default_factory=dict)

    def copy(self) -> "State":
        return State(dict(self.nodes), dict(self.connections))


@dataclass(frozen=True)
class Metamodel:
    """What the Model's types allow: type ids and the allowed (connection, source, target) type triples."""

    node_type_ids: frozenset[UUID]
    connection_type_ids: frozenset[UUID]
    allowed: frozenset[tuple[UUID, UUID, UUID]]


@dataclass(frozen=True)
class Edit:
    op: str
    element_id: UUID
    payload: dict[str, Any] = field(default_factory=dict)


def apply_edit(state: State, edit: Edit, metamodel: Metamodel) -> None:
    """Apply one edit in place; raises ``EditInvalid`` when it does not fit the state or the metamodel.

    Removing a node removes the connections attached to it in the same step.
    """
    payload = parse_payload(edit.op, edit.payload)
    element = edit.element_id
    if edit.op == "add_node":
        assert isinstance(payload, AddNode)
        if element in state.nodes:
            raise EditInvalid("duplicate_element", element)
        if payload.node_type_id not in metamodel.node_type_ids:
            raise EditInvalid("missing_type", payload.node_type_id)
        state.nodes[element] = NodeState(element, payload.node_type_id, payload.name, payload.description, payload.x, payload.y)
    elif edit.op == "remove_node":
        if element not in state.nodes:
            raise EditInvalid("missing_element", element)
        del state.nodes[element]
        for key in [key for key, item in state.connections.items() if element in (item.source_node_id, item.target_node_id)]:
            del state.connections[key]
    elif edit.op == "update_node":
        assert isinstance(payload, UpdateNode)
        node = state.nodes.get(element)
        if node is None:
            raise EditInvalid("missing_element", element)
        fields = payload.model_fields_set
        new_type = payload.node_type_id if "node_type_id" in fields and payload.node_type_id else node.node_type_id
        if new_type not in metamodel.node_type_ids:
            raise EditInvalid("missing_type", new_type)
        updated = NodeState(
            element,
            new_type,
            payload.name if "name" in fields and payload.name else node.name,
            payload.description if "description" in fields else node.description,
            node.x,
            node.y,
        )
        state.nodes[element] = updated
        if new_type != node.node_type_id:
            for item in state.connections.values():
                if element in (item.source_node_id, item.target_node_id):
                    _check_connection(state, metamodel, item.id, item.connection_type_id, item.source_node_id, item.target_node_id, ignore=item.id)
    elif edit.op == "add_connection":
        assert isinstance(payload, AddConnection)
        if element in state.connections:
            raise EditInvalid("duplicate_element", element)
        _check_connection(state, metamodel, element, payload.connection_type_id, payload.source_node_id, payload.target_node_id, ignore=None)
        state.connections[element] = ConnectionState(element, payload.connection_type_id, payload.source_node_id, payload.target_node_id)
    elif edit.op == "remove_connection":
        if element not in state.connections:
            raise EditInvalid("missing_element", element)
        del state.connections[element]
    elif edit.op == "reroute_connection":
        assert isinstance(payload, RerouteConnection)
        connection = state.connections.get(element)
        if connection is None:
            raise EditInvalid("missing_element", element)
        source = payload.source_node_id or connection.source_node_id
        target = payload.target_node_id or connection.target_node_id
        _check_connection(state, metamodel, element, connection.connection_type_id, source, target, ignore=element)
        state.connections[element] = ConnectionState(element, connection.connection_type_id, source, target)
    elif edit.op == "change_connection_type":
        assert isinstance(payload, ChangeConnectionType)
        connection = state.connections.get(element)
        if connection is None:
            raise EditInvalid("missing_element", element)
        _check_connection(state, metamodel, element, payload.connection_type_id, connection.source_node_id, connection.target_node_id, ignore=element)
        state.connections[element] = ConnectionState(element, payload.connection_type_id, connection.source_node_id, connection.target_node_id)
    else:  # pragma: no cover - parse_payload already refuses unknown operations
        raise ValueError(edit.op)


def _check_connection(state: State, metamodel: Metamodel, element: UUID, type_id: UUID, source_id: UUID, target_id: UUID, *, ignore: UUID | None) -> None:
    if type_id not in metamodel.connection_type_ids:
        raise EditInvalid("missing_type", type_id)
    source = state.nodes.get(source_id)
    target = state.nodes.get(target_id)
    if source is None:
        raise EditInvalid("missing_endpoint", source_id)
    if target is None:
        raise EditInvalid("missing_endpoint", target_id)
    if source_id == target_id:
        raise EditInvalid("self_connection", element)
    if (type_id, source.node_type_id, target.node_type_id) not in metamodel.allowed:
        raise EditInvalid("connection_not_allowed", element)
    for other in state.connections.values():
        if other.id != ignore and (other.connection_type_id, other.source_node_id, other.target_node_id) == (type_id, source_id, target_id):
            raise EditInvalid("duplicate_connection", element)


def apply_edits(state: State, edits: Iterable[Edit], metamodel: Metamodel) -> State:
    """A new state after the edits, leaving the given state untouched."""
    result = state.copy()
    for edit in edits:
        apply_edit(result, edit, metamodel)
    return result
