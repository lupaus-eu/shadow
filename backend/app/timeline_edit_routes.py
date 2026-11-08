"""Canvas edits of nodes and connections as edits inside a change (model timeline, ADR-0048, ADR-0049).

Every edit belongs to the change whose state the person is looking at: any change of a line they may write, not
only the last. The edit is appended to the change's edits, the list is tidied with ``compact`` (an element
added and removed in the same change leaves no trace; repeated renames and re-routes merge), the whole chain
is replayed with ``validate_model`` and, only if it holds, the change's edits are rewritten and renumbered.
A refusal answers 422 ``chain_broken`` (the body of ``app.timeline.validate``) and leaves the change unchanged.

``expected_version`` is the change's ``version`` (409 when stale), in the body of a create or edit and in
the query of a delete, as in ``timeline_change_routes``; a create may leave it out. A node created here also
gets a drawn position on the line (``_store_edits``). Moving nodes is not an edit: it uses the positions route.
The audit entry is the ``change.updated`` entry of the change routes: ids, the date and edit counts per
operation, never names.
"""

from collections.abc import Callable
from dataclasses import replace
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import delete
from sqlalchemy.orm import Session, sessionmaker

from app.auth import AuthenticatedUser, Clock
from app.auth_routes import AuthenticatedUserDependency
from app.model_routes import _audit, _member_session, _model, _stale
from app.models import ChangeEdit
from app.subscription_access import require_organization_mutation_access
from app.timeline.chain import ChangeRecord, chain_changes, replay
from app.timeline.compact import compact
from app.timeline.errors import ChainBroken, EditInvalid
from app.timeline.loader import ModelTimeline, load_timeline
from app.timeline.payloads import dump_payload
from app.timeline.state import Edit, NodeState, State, apply_edits
from app.timeline.validate import Mutation
from app.timeline_change_routes import ChangeDetailResponse, _counts, _detail, _forget_positions, _may_write, _restart, _store_edits, _summary, _validate
from app.timeline_routes import StateConnection, StateNode, _broken, _connection, _resolve_positions


def _trimmed(value: str) -> str:
    if not (value := " ".join(value.split())):
        raise ValueError("must not be blank")
    return value


Version = Field(default=None, ge=1)


class NodeCreate(BaseModel):
    expected_version: int | None = Version
    node_type_id: UUID
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=4000)
    x: float = Field(default=0, allow_inf_nan=False)
    y: float = Field(default=0, allow_inf_nan=False)

    @field_validator("name")
    @classmethod
    def _trim(cls, value: str) -> str:
        return _trimmed(value)


class NodeEdit(BaseModel):
    """Only the fields sent are applied; ``description`` null clears it."""

    expected_version: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=4000)
    node_type_id: UUID | None = None

    @model_validator(mode="after")
    def _valid(self) -> "NodeEdit":
        sent = self.model_fields_set
        if not sent & {"name", "description", "node_type_id"}:
            raise ValueError("send a name, description or node_type_id")
        for key in ("name", "node_type_id"):
            if key in sent and getattr(self, key) is None:
                raise ValueError(f"{key} must not be null")
        if self.name is not None:
            self.name = _trimmed(self.name)
        return self


class ConnectionCreate(BaseModel):
    expected_version: int | None = Version
    connection_type_id: UUID
    source_node_id: UUID
    target_node_id: UUID


class ConnectionEdit(BaseModel):
    """Re-type and/or re-route; the fields sent are applied."""

    expected_version: int = Field(ge=1)
    connection_type_id: UUID | None = None
    source_node_id: UUID | None = None
    target_node_id: UUID | None = None

    @model_validator(mode="after")
    def _valid(self) -> "ConnectionEdit":
        sent = self.model_fields_set
        if not sent & {"connection_type_id", "source_node_id", "target_node_id"}:
            raise ValueError("send a connection_type_id, source_node_id or target_node_id")
        for key in sent & {"connection_type_id", "source_node_id", "target_node_id"}:
            if getattr(self, key) is None:
                raise ValueError(f"{key} must not be null")
        return self


class CanvasEditResponse(BaseModel):
    """The element the edit made or changed (its id is the stable element id) and the change as saved."""

    id: UUID
    change: ChangeDetailResponse
    node: StateNode | None = None
    connection: StateConnection | None = None


class CanvasEdit:
    """What one edit does, given the state the person sees (after the change): the edits to append."""

    def __init__(self, element_id: UUID, plan: Callable[[State, ModelTimeline], list[Edit]]) -> None:
        self.element_id = element_id
        self.plan = plan


def _missing(kind: str) -> HTTPException:
    return HTTPException(status_code=404, detail=f"{kind} not found")


def _edit_change(
    session_factory: sessionmaker[Session],
    clock: Clock,
    organization_id: UUID,
    model_id: UUID,
    change_id: UUID,
    user: AuthenticatedUser,
    request: Request,
    canvas: CanvasEdit,
    expected_version: int | None,
) -> CanvasEditResponse:
    with _member_session(session_factory, organization_id, user) as (session, membership):
        require_organization_mutation_access(session, organization_id)
        _model(session, organization_id, model_id, lock=True)  # one writer per Model while the chain is checked and saved
        timeline = load_timeline(session, model_id)
        row = timeline.change_rows.get(change_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Change not found")
        line_id = row.line_id
        _may_write(timeline, line_id, membership)
        if expected_version is not None:
            _stale(row.version, expected_version)
        old = next(item for item in timeline.changes[line_id] if item.id == change_id)
        try:
            chain = chain_changes(timeline.lines, timeline.changes, line_id, change_id)
            before = replay(chain[:-1], timeline.metamodel)
            current = replay(chain, timeline.metamodel)
        except ChainBroken as error:
            raise _broken(error) from error
        added = canvas.plan(current, timeline)
        merged = tuple(compact([*old.edits, *added], before, timeline.metamodel)) if added else old.edits
        if merged == old.edits:  # nothing to write: the edit does nothing the change does not already do
            return _response(session, organization_id, model_id, change_id, canvas.element_id, timeline, line_id, current, clock)
        new = replace(old, edits=merged)

        def apply(changes: dict[UUID, list[ChangeRecord]]) -> None:
            changes[line_id] = [new if item.id == change_id else item for item in changes[line_id]]

        validation = _validate(session, model_id, timeline, Mutation(line_id, apply))
        row.version += 1
        row.updated_at = clock()
        session.execute(delete(ChangeEdit).where(ChangeEdit.change_id == change_id))
        session.flush()
        _store_edits(session, organization_id, model_id, line_id, change_id, merged)
        _forget_positions(session, model_id, old.edits, validation.changes)
        _restart(timeline, validation, clock)
        summary = _summary(model_id, line_id, change_id, row.occurred_on, _counts(merged))
        summary["fields"] = ["edits"]
        summary["previous_edit_counts"] = _counts(old.edits)
        _audit(session, request, "change.updated", "change", change_id, summary)
        return _response(session, organization_id, model_id, change_id, canvas.element_id, timeline, line_id, apply_edits(before, merged, timeline.metamodel), clock)


def _response(session: Session, organization_id: UUID, model_id: UUID, change_id: UUID, element_id: UUID, timeline: ModelTimeline, line_id: UUID, state: State, clock: Clock) -> CanvasEditResponse:
    node = state.nodes.get(element_id)
    connection = state.connections.get(element_id)
    drawn = _resolve_positions(session, timeline, line_id, State({element_id: node}, {})) if node is not None else {}
    x, y = drawn.get(element_id, (node.x, node.y) if node is not None else (0, 0))
    return CanvasEditResponse(
        id=element_id,
        change=_detail(session, organization_id, model_id, change_id, clock),
        node=StateNode(id=node.id, node_type_id=node.node_type_id, name=node.name, description=node.description, x=x, y=y) if node is not None else None,
        connection=_connection(connection) if connection is not None else None,
    )


def _node(state: State, node_id: UUID) -> NodeState:
    node = state.nodes.get(node_id)
    if node is None:
        raise _missing("Node")
    return node


def _create_node(body: NodeCreate) -> CanvasEdit:
    element = uuid4()
    payload: dict[str, Any] = {"node_type_id": str(body.node_type_id), "name": body.name, "x": body.x, "y": body.y}
    if body.description is not None:
        payload["description"] = body.description
    edit = Edit("add_node", element, dump_payload("add_node", payload))
    return CanvasEdit(element, lambda state, timeline: [edit])


def _change_node(node_id: UUID, body: NodeEdit) -> CanvasEdit:
    def plan(state: State, timeline: ModelTimeline) -> list[Edit]:
        node = _node(state, node_id)
        sent = body.model_fields_set
        wanted: dict[str, Any] = {}
        if "name" in sent:
            wanted["name"] = body.name
        if "description" in sent:
            wanted["description"] = body.description
        if "node_type_id" in sent:
            wanted["node_type_id"] = str(body.node_type_id)
        current = {"name": node.name, "description": node.description, "node_type_id": str(node.node_type_id)}
        differing = {key: value for key, value in wanted.items() if current[key] != value}
        return [Edit("update_node", node_id, dump_payload("update_node", differing))] if differing else []

    return CanvasEdit(node_id, plan)


def _remove_node(node_id: UUID) -> CanvasEdit:
    def plan(state: State, timeline: ModelTimeline) -> list[Edit]:
        _node(state, node_id)
        return [Edit("remove_node", node_id, {})]

    return CanvasEdit(node_id, plan)


def _create_connection(body: ConnectionCreate) -> CanvasEdit:
    element = uuid4()
    payload = {"connection_type_id": str(body.connection_type_id), "source_node_id": str(body.source_node_id), "target_node_id": str(body.target_node_id)}
    edit = Edit("add_connection", element, dump_payload("add_connection", payload))
    return CanvasEdit(element, lambda state, timeline: [edit])


def _change_connection(connection_id: UUID, body: ConnectionEdit) -> CanvasEdit:
    def plan(state: State, timeline: ModelTimeline) -> list[Edit]:
        connection = state.connections.get(connection_id)
        if connection is None:
            raise _missing("Connection")
        retype = {"connection_type_id": str(body.connection_type_id)} if body.connection_type_id and body.connection_type_id != connection.connection_type_id else {}
        ends = {key: str(value) for key in ("source_node_id", "target_node_id") if (value := getattr(body, key)) is not None and value != getattr(connection, key)}
        steps = [Edit("change_connection_type", connection_id, dump_payload("change_connection_type", retype))] if retype else []
        reroute = [Edit("reroute_connection", connection_id, dump_payload("reroute_connection", ends))] if ends else []
        if not (retype and ends):
            return steps + reroute
        # Both change: a rule may allow the new type only between the new ends (or the new ends only with the old type), so try both orders.
        for order in (steps + reroute, reroute + steps):
            try:
                apply_edits(state, order, timeline.metamodel)
                return order
            except EditInvalid:
                continue
        return steps + reroute  # neither order fits: the replay will refuse it with the cause

    return CanvasEdit(connection_id, plan)


def _remove_connection(connection_id: UUID) -> CanvasEdit:
    def plan(state: State, timeline: ModelTimeline) -> list[Edit]:
        if connection_id not in state.connections:
            raise _missing("Connection")
        return [Edit("remove_connection", connection_id, {})]

    return CanvasEdit(connection_id, plan)


def create_timeline_edit_router(*, session_factory: sessionmaker[Session], authenticated_user_dependency: AuthenticatedUserDependency, clock: Clock) -> APIRouter:
    router = APIRouter(prefix="/api/v1/organizations", tags=["Timeline"])
    base = "/{organization_id}/models/{model_id}/changes/{change_id}"

    @router.post(base + "/nodes", response_model=CanvasEditResponse, status_code=201)
    def create_node(organization_id: UUID, model_id: UUID, change_id: UUID, body: NodeCreate, request: Request, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> CanvasEditResponse:
        return _edit_change(session_factory, clock, organization_id, model_id, change_id, user, request, _create_node(body), body.expected_version)

    @router.patch(base + "/nodes/{node_id}", response_model=CanvasEditResponse)
    def update_node(organization_id: UUID, model_id: UUID, change_id: UUID, node_id: UUID, body: NodeEdit, request: Request, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> CanvasEditResponse:
        return _edit_change(session_factory, clock, organization_id, model_id, change_id, user, request, _change_node(node_id, body), body.expected_version)

    @router.delete(base + "/nodes/{node_id}", status_code=204)
    def delete_node(organization_id: UUID, model_id: UUID, change_id: UUID, node_id: UUID, expected_version: int, request: Request, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> Response:
        _edit_change(session_factory, clock, organization_id, model_id, change_id, user, request, _remove_node(node_id), expected_version)
        return Response(status_code=204)

    @router.post(base + "/connections", response_model=CanvasEditResponse, status_code=201)
    def create_connection(organization_id: UUID, model_id: UUID, change_id: UUID, body: ConnectionCreate, request: Request, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> CanvasEditResponse:
        return _edit_change(session_factory, clock, organization_id, model_id, change_id, user, request, _create_connection(body), body.expected_version)

    @router.patch(base + "/connections/{connection_id}", response_model=CanvasEditResponse)
    def update_connection(organization_id: UUID, model_id: UUID, change_id: UUID, connection_id: UUID, body: ConnectionEdit, request: Request, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> CanvasEditResponse:
        return _edit_change(session_factory, clock, organization_id, model_id, change_id, user, request, _change_connection(connection_id, body), body.expected_version)

    @router.delete(base + "/connections/{connection_id}", status_code=204)
    def delete_connection(organization_id: UUID, model_id: UUID, change_id: UUID, connection_id: UUID, expected_version: int, request: Request, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> Response:
        _edit_change(session_factory, clock, organization_id, model_id, change_id, user, request, _remove_connection(connection_id), expected_version)
        return Response(status_code=204)

    return router
