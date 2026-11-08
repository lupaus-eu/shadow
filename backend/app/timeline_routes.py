"""Reading a Model's lines, their changes, and the graph after a change or on a date (model timeline, ADR-0048).

Reads need membership only; a read-only Organization can read. Nothing here writes (writes arrive with
the change routes). The graph is computed by replaying the chain of changes (ancestors up to the branch
change, then the line's own changes); positions belong to the line and fall back to the parent line and
then to the position the node was added with.
"""

from collections import Counter
from datetime import date, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.auth import AuthenticatedUser, Clock
from app.auth_routes import AuthenticatedUserDependency
from app.model_routes import (
    LineResponse,
    AllowedConnectionResponse,
    ConnectionTypeResponse,
    NodeTypeResponse,
    _member_session,
    _model,
)
from app.models import AllowedConnection, ConnectionType, NodePosition, NodeType
from app.timeline.chain import chain_changes, replay, state_as_of
from app.timeline.errors import ChainBroken
from app.timeline.loader import ModelTimeline, is_planned, load_timeline, today_in_organization
from app.timeline.state import ConnectionState, NodeState, State


class BranchResponse(BaseModel):
    line_id: UUID
    name: str


class ChangeResponse(BaseModel):
    id: UUID
    line_id: UUID
    occurred_on: date
    seq: int
    title: str
    note: str | None
    version: int
    planned: bool
    edit_count: int
    edit_counts: dict[str, int]
    branches: list[BranchResponse]


class StateNode(BaseModel):
    id: UUID
    node_type_id: UUID
    name: str
    description: str | None
    x: float
    y: float


class StateConnection(BaseModel):
    id: UUID
    connection_type_id: UUID
    source_node_id: UUID
    target_node_id: UUID


class PositionResponse(BaseModel):
    node_id: UUID
    x: float
    y: float


class ChangedNode(BaseModel):
    """A node the shown change changed; ``previous`` holds the node as it was before an update."""

    node: StateNode
    previous: StateNode | None = None


class ChangedConnection(BaseModel):
    connection: StateConnection
    previous: StateConnection | None = None


class ElementList(BaseModel):
    nodes: list[ChangedNode] = []
    connections: list[ChangedConnection] = []


class StateResponse(BaseModel):
    line: LineResponse
    change: ChangeResponse | None
    as_of: date | None
    planned: bool
    node_types: list[NodeTypeResponse]
    connection_types: list[ConnectionTypeResponse]
    allowed_connections: list[AllowedConnectionResponse]
    nodes: list[StateNode]
    connections: list[StateConnection]
    positions: list[PositionResponse]
    added: ElementList
    updated: ElementList
    removed: ElementList


def _line_response(timeline: ModelTimeline, line_id: UUID) -> LineResponse:
    row = timeline.line_rows[line_id]
    own = timeline.changes.get(line_id, ())
    return LineResponse(
        id=row.id,
        name=row.name,
        description=row.description,
        kind=row.kind,
        parent_line_id=row.parent_line_id,
        branch_change_id=row.branch_change_id,
        start_changed_at=row.start_changed_at,
        created_by_user_account_id=row.created_by_user_account_id,
        version=row.version,
        created_at=row.created_at,
        change_count=len(own),
        latest_change_date=max((change.occurred_on for change in own), default=None),
    )


def _change_response(timeline: ModelTimeline, change_id: UUID, today: date) -> ChangeResponse:
    row = timeline.change_rows[change_id]
    record = next(item for item in timeline.changes[row.line_id] if item.id == change_id)
    counts = Counter(edit.op for edit in record.edits)
    branches = sorted((line for line in timeline.line_rows.values() if line.branch_change_id == change_id), key=lambda line: (line.created_at, line.id))
    return ChangeResponse(
        id=row.id,
        line_id=row.line_id,
        occurred_on=row.occurred_on,
        seq=record.seq,
        title=row.title,
        note=row.note,
        version=row.version,
        planned=is_planned(row.occurred_on, today),
        edit_count=len(record.edits),
        edit_counts=dict(sorted(counts.items())),
        branches=[BranchResponse(line_id=line.id, name=line.name) for line in branches],
    )


def _ancestry(timeline: ModelTimeline, line_id: UUID) -> list[UUID]:
    """The line and then each parent in turn, nearest first."""
    found: list[UUID] = []
    current: UUID | None = line_id
    while current is not None and current not in found and current in timeline.lines:
        found.append(current)
        current = timeline.lines[current].parent_line_id
    return found


def _resolve_positions(session: Session, timeline: ModelTimeline, line_id: UUID, state: State) -> dict[UUID, tuple[float, float]]:
    """Per node: this line's position, else the nearest ancestor's, else where the node was added."""
    ancestry = _ancestry(timeline, line_id)
    rows = session.scalars(select(NodePosition).where(NodePosition.line_id.in_(ancestry), NodePosition.node_id.in_(list(state.nodes)))).all() if state.nodes else []
    by_line = {(row.line_id, row.node_id): (row.x, row.y) for row in rows}
    resolved: dict[UUID, tuple[float, float]] = {}
    for node in state.nodes.values():
        resolved[node.id] = next((by_line[(line, node.id)] for line in ancestry if (line, node.id) in by_line), (node.x, node.y))
    return resolved


def _node(node: NodeState, positions: dict[UUID, tuple[float, float]]) -> StateNode:
    x, y = positions.get(node.id, (node.x, node.y))
    return StateNode(id=node.id, node_type_id=node.node_type_id, name=node.name, description=node.description, x=x, y=y)


def _connection(connection: ConnectionState) -> StateConnection:
    return StateConnection(id=connection.id, connection_type_id=connection.connection_type_id, source_node_id=connection.source_node_id, target_node_id=connection.target_node_id)


def _diff(before: State, after: State, positions: dict[UUID, tuple[float, float]]) -> tuple[ElementList, ElementList, ElementList]:
    """What one change changed: elements it added, updated (with their previous data) and removed (with their data)."""
    added, updated, removed = ElementList(), ElementList(), ElementList()
    for key, node in after.nodes.items():
        old = before.nodes.get(key)
        if old is None:
            added.nodes.append(ChangedNode(node=_node(node, positions)))
        elif old != node:
            updated.nodes.append(ChangedNode(node=_node(node, positions), previous=_node(old, positions)))
    for key, node in before.nodes.items():
        if key not in after.nodes:
            removed.nodes.append(ChangedNode(node=_node(node, positions)))
    for key, connection in after.connections.items():
        old_connection = before.connections.get(key)
        if old_connection is None:
            added.connections.append(ChangedConnection(connection=_connection(connection)))
        elif old_connection != connection:
            updated.connections.append(ChangedConnection(connection=_connection(connection), previous=_connection(old_connection)))
    for key, connection in before.connections.items():
        if key not in after.connections:
            removed.connections.append(ChangedConnection(connection=_connection(connection)))
    return added, updated, removed


def _broken(error: ChainBroken) -> HTTPException:
    return HTTPException(status_code=422, detail={"reason": "chain_broken", "line_id": str(error.line_id), "change_id": str(error.change_id) if error.change_id else None, "position": error.position, "cause": error.cause, "element": str(error.element_id) if error.element_id else None})


def _line(timeline: ModelTimeline, line_id: UUID) -> None:
    if line_id not in timeline.lines:
        raise HTTPException(status_code=404, detail="Line not found")


def create_timeline_router(*, session_factory: sessionmaker[Session], authenticated_user_dependency: AuthenticatedUserDependency, clock: Clock) -> APIRouter:
    router = APIRouter(prefix="/api/v1/organizations", tags=["Timeline"])
    base = "/{organization_id}/models/{model_id}/lines"

    @router.get(base, response_model=list[LineResponse])
    def list_lines(organization_id: UUID, model_id: UUID, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> list[LineResponse]:
        with _member_session(session_factory, organization_id, user) as (session, _membership):
            _model(session, organization_id, model_id)
            timeline = load_timeline(session, model_id)
            ordered = sorted(timeline.line_rows.values(), key=lambda line: (line.kind != "base", line.created_at, line.id))
            return [_line_response(timeline, line.id) for line in ordered]

    @router.get(base + "/{line_id}/changes", response_model=list[ChangeResponse])
    def list_changes(organization_id: UUID, model_id: UUID, line_id: UUID, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> list[ChangeResponse]:
        with _member_session(session_factory, organization_id, user) as (session, _membership):
            _model(session, organization_id, model_id)
            timeline = load_timeline(session, model_id)
            _line(timeline, line_id)
            today = today_in_organization(session, organization_id, clock)
            return [_change_response(timeline, change.id, today) for change in timeline.changes_of(line_id)]

    @router.get(base + "/{line_id}/state", response_model=StateResponse)
    def read_state(organization_id: UUID, model_id: UUID, line_id: UUID, change_id: UUID | None = None, as_of: date | None = None, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> StateResponse:
        if change_id is not None and as_of is not None:
            raise HTTPException(status_code=422, detail={"reason": "change_id_and_as_of"})
        with _member_session(session_factory, organization_id, user) as (session, _membership):
            _model(session, organization_id, model_id)
            timeline = load_timeline(session, model_id)
            _line(timeline, line_id)
            today = today_in_organization(session, organization_id, clock)
            own = timeline.changes_of(line_id)
            day: date | None = None
            try:
                if change_id is not None:
                    shown = next((change for change in own if change.id == change_id), None)
                    if shown is None:
                        raise HTTPException(status_code=404, detail="Change not found")
                else:
                    day = as_of or today
                    shown = next(iter(reversed([change for change in own if change.occurred_on <= day])), None)
                if shown is not None:
                    chain = chain_changes(timeline.lines, timeline.changes, line_id, shown.id)
                    state = replay(chain, timeline.metamodel)
                    before = replay(chain[:-1], timeline.metamodel)
                else:
                    state = state_as_of(timeline.lines, timeline.changes, timeline.metamodel, line_id, day) if day else State()
                    before = state
            except ChainBroken as error:
                raise _broken(error) from error
            drawn = _resolve_positions(session, timeline, line_id, State({**before.nodes, **state.nodes}, {}))  # removed nodes keep the position they had
            positions = {key: drawn[key] for key in state.nodes}
            by_model = lambda entity: select(entity).where(entity.model_id == model_id)  # noqa: E731
            added, updated, removed = _diff(before, state, drawn) if shown is not None else (ElementList(), ElementList(), ElementList())
            return StateResponse(
                line=_line_response(timeline, line_id),
                change=_change_response(timeline, shown.id, today) if shown is not None else None,
                as_of=day,
                planned=is_planned(shown.occurred_on, today) if shown is not None else False,
                node_types=[NodeTypeResponse.model_validate(item, from_attributes=True) for item in session.scalars(by_model(NodeType).order_by(NodeType.name))],
                connection_types=[ConnectionTypeResponse.model_validate(item, from_attributes=True) for item in session.scalars(by_model(ConnectionType).order_by(ConnectionType.name))],
                allowed_connections=[AllowedConnectionResponse.model_validate(item, from_attributes=True) for item in session.scalars(by_model(AllowedConnection))],
                nodes=[_node(node, positions) for node in state.nodes.values()],
                connections=[_connection(connection) for connection in state.connections.values()],
                positions=[PositionResponse(node_id=key, x=x, y=y) for key, (x, y) in positions.items()],
                added=added,
                updated=updated,
                removed=removed,
            )

    return router
