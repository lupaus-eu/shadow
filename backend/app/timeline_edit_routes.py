"""Canvas edits of nodes and connections as changes inside an event (model timeline, ADR-0048, ADR-0049).

Every edit belongs to the event whose state the person is looking at: any event of a line they may write, not
only the last. The edit is appended to the event's changes, the list is tidied with ``compact`` (an element
added and removed in the same event leaves no trace; repeated renames and re-routes merge), the whole chain
is replayed with ``validate_model`` and, only if it holds, the event's changes are rewritten and renumbered.
A refusal answers 422 ``chain_broken`` (the body of ``app.timeline.validate``) and leaves the event unchanged.

``expected_version`` is the event's ``version`` (409 when stale), in the body of a create or change and in
the query of a delete, as in ``timeline_event_routes``; a create may leave it out. A node created here also
gets a drawn position on the line (``_store_changes``). Moving nodes is not an edit: it uses the positions route.
The audit entry is the ``event.updated`` entry of the event routes: ids, the date and change counts per
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
from app.models import EventChange
from app.subscription_access import require_organization_mutation_access
from app.timeline.chain import EventRecord, chain_events, replay
from app.timeline.compact import compact
from app.timeline.errors import ChainBroken, ChangeInvalid
from app.timeline.loader import ModelTimeline, load_timeline
from app.timeline.payloads import dump_payload
from app.timeline.state import Change, NodeState, State, apply_changes
from app.timeline.validate import Mutation
from app.timeline_event_routes import EventDetailResponse, _counts, _detail, _forget_positions, _may_write, _restart, _store_changes, _summary, _validate
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
    """Only the fields sent change; ``description`` null clears it."""

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
    """Re-type and/or re-route; the fields sent change."""

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


class EditResponse(BaseModel):
    """The element the edit made or changed (its id is the stable element id) and the event as saved."""

    id: UUID
    event: EventDetailResponse
    node: StateNode | None = None
    connection: StateConnection | None = None


class Edit:
    """What one edit does, given the state the person sees (after the event): the changes to append."""

    def __init__(self, element_id: UUID, plan: Callable[[State, ModelTimeline], list[Change]]) -> None:
        self.element_id = element_id
        self.plan = plan


def _missing(kind: str) -> HTTPException:
    return HTTPException(status_code=404, detail=f"{kind} not found")


def _edit_event(
    session_factory: sessionmaker[Session],
    clock: Clock,
    organization_id: UUID,
    model_id: UUID,
    event_id: UUID,
    user: AuthenticatedUser,
    request: Request,
    edit: Edit,
    expected_version: int | None,
) -> EditResponse:
    with _member_session(session_factory, organization_id, user) as (session, membership):
        require_organization_mutation_access(session, organization_id)
        _model(session, organization_id, model_id, lock=True)  # one writer per Model while the chain is checked and saved
        timeline = load_timeline(session, model_id)
        row = timeline.event_rows.get(event_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Event not found")
        line_id = row.line_id
        _may_write(timeline, line_id, membership)
        if expected_version is not None:
            _stale(row.version, expected_version)
        old = next(item for item in timeline.events[line_id] if item.id == event_id)
        try:
            chain = chain_events(timeline.lines, timeline.events, line_id, event_id)
            before = replay(chain[:-1], timeline.metamodel)
            current = replay(chain, timeline.metamodel)
        except ChainBroken as error:
            raise _broken(error) from error
        added = edit.plan(current, timeline)
        merged = tuple(compact([*old.changes, *added], before, timeline.metamodel)) if added else old.changes
        if merged == old.changes:  # nothing to write: the edit changes nothing the event does not already do
            return _response(session, organization_id, model_id, event_id, edit.element_id, timeline, line_id, current, clock)
        new = replace(old, changes=merged)

        def apply(events: dict[UUID, list[EventRecord]]) -> None:
            events[line_id] = [new if item.id == event_id else item for item in events[line_id]]

        validation = _validate(session, model_id, timeline, Mutation(line_id, apply))
        row.version += 1
        row.updated_at = clock()
        session.execute(delete(EventChange).where(EventChange.event_id == event_id))
        session.flush()
        _store_changes(session, organization_id, model_id, line_id, event_id, merged)
        _forget_positions(session, model_id, old.changes, validation.events)
        _restart(timeline, validation, clock)
        summary = _summary(model_id, line_id, event_id, row.occurred_on, _counts(merged))
        summary["fields"] = ["changes"]
        summary["previous_change_counts"] = _counts(old.changes)
        _audit(session, request, "event.updated", "event", event_id, summary)
        return _response(session, organization_id, model_id, event_id, edit.element_id, timeline, line_id, apply_changes(before, merged, timeline.metamodel), clock)


def _response(session: Session, organization_id: UUID, model_id: UUID, event_id: UUID, element_id: UUID, timeline: ModelTimeline, line_id: UUID, state: State, clock: Clock) -> EditResponse:
    node = state.nodes.get(element_id)
    connection = state.connections.get(element_id)
    drawn = _resolve_positions(session, timeline, line_id, State({element_id: node}, {})) if node is not None else {}
    x, y = drawn.get(element_id, (node.x, node.y) if node is not None else (0, 0))
    return EditResponse(
        id=element_id,
        event=_detail(session, organization_id, model_id, event_id, clock),
        node=StateNode(id=node.id, node_type_id=node.node_type_id, name=node.name, description=node.description, x=x, y=y) if node is not None else None,
        connection=_connection(connection) if connection is not None else None,
    )


def _node(state: State, node_id: UUID) -> NodeState:
    node = state.nodes.get(node_id)
    if node is None:
        raise _missing("Node")
    return node


def _create_node(body: NodeCreate) -> Edit:
    element = uuid4()
    payload: dict[str, Any] = {"node_type_id": str(body.node_type_id), "name": body.name, "x": body.x, "y": body.y}
    if body.description is not None:
        payload["description"] = body.description
    change = Change("add_node", element, dump_payload("add_node", payload))
    return Edit(element, lambda state, timeline: [change])


def _change_node(node_id: UUID, body: NodeEdit) -> Edit:
    def plan(state: State, timeline: ModelTimeline) -> list[Change]:
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
        return [Change("update_node", node_id, dump_payload("update_node", differing))] if differing else []

    return Edit(node_id, plan)


def _remove_node(node_id: UUID) -> Edit:
    def plan(state: State, timeline: ModelTimeline) -> list[Change]:
        _node(state, node_id)
        return [Change("remove_node", node_id, {})]

    return Edit(node_id, plan)


def _create_connection(body: ConnectionCreate) -> Edit:
    element = uuid4()
    payload = {"connection_type_id": str(body.connection_type_id), "source_node_id": str(body.source_node_id), "target_node_id": str(body.target_node_id)}
    change = Change("add_connection", element, dump_payload("add_connection", payload))
    return Edit(element, lambda state, timeline: [change])


def _change_connection(connection_id: UUID, body: ConnectionEdit) -> Edit:
    def plan(state: State, timeline: ModelTimeline) -> list[Change]:
        connection = state.connections.get(connection_id)
        if connection is None:
            raise _missing("Connection")
        retype = {"connection_type_id": str(body.connection_type_id)} if body.connection_type_id and body.connection_type_id != connection.connection_type_id else {}
        ends = {key: str(value) for key in ("source_node_id", "target_node_id") if (value := getattr(body, key)) is not None and value != getattr(connection, key)}
        steps = [Change("change_connection_type", connection_id, dump_payload("change_connection_type", retype))] if retype else []
        reroute = [Change("reroute_connection", connection_id, dump_payload("reroute_connection", ends))] if ends else []
        if not (retype and ends):
            return steps + reroute
        # Both change: a rule may allow the new type only between the new ends (or the new ends only with the old type), so try both orders.
        for order in (steps + reroute, reroute + steps):
            try:
                apply_changes(state, order, timeline.metamodel)
                return order
            except ChangeInvalid:
                continue
        return steps + reroute  # neither order fits: the replay will refuse it with the cause

    return Edit(connection_id, plan)


def _remove_connection(connection_id: UUID) -> Edit:
    def plan(state: State, timeline: ModelTimeline) -> list[Change]:
        if connection_id not in state.connections:
            raise _missing("Connection")
        return [Change("remove_connection", connection_id, {})]

    return Edit(connection_id, plan)


def create_timeline_edit_router(*, session_factory: sessionmaker[Session], authenticated_user_dependency: AuthenticatedUserDependency, clock: Clock) -> APIRouter:
    router = APIRouter(prefix="/api/v1/organizations", tags=["Timeline"])
    base = "/{organization_id}/models/{model_id}/events/{event_id}"

    @router.post(base + "/nodes", response_model=EditResponse, status_code=201)
    def create_node(organization_id: UUID, model_id: UUID, event_id: UUID, body: NodeCreate, request: Request, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> EditResponse:
        return _edit_event(session_factory, clock, organization_id, model_id, event_id, user, request, _create_node(body), body.expected_version)

    @router.patch(base + "/nodes/{node_id}", response_model=EditResponse)
    def update_node(organization_id: UUID, model_id: UUID, event_id: UUID, node_id: UUID, body: NodeEdit, request: Request, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> EditResponse:
        return _edit_event(session_factory, clock, organization_id, model_id, event_id, user, request, _change_node(node_id, body), body.expected_version)

    @router.delete(base + "/nodes/{node_id}", status_code=204)
    def delete_node(organization_id: UUID, model_id: UUID, event_id: UUID, node_id: UUID, expected_version: int, request: Request, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> Response:
        _edit_event(session_factory, clock, organization_id, model_id, event_id, user, request, _remove_node(node_id), expected_version)
        return Response(status_code=204)

    @router.post(base + "/connections", response_model=EditResponse, status_code=201)
    def create_connection(organization_id: UUID, model_id: UUID, event_id: UUID, body: ConnectionCreate, request: Request, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> EditResponse:
        return _edit_event(session_factory, clock, organization_id, model_id, event_id, user, request, _create_connection(body), body.expected_version)

    @router.patch(base + "/connections/{connection_id}", response_model=EditResponse)
    def update_connection(organization_id: UUID, model_id: UUID, event_id: UUID, connection_id: UUID, body: ConnectionEdit, request: Request, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> EditResponse:
        return _edit_event(session_factory, clock, organization_id, model_id, event_id, user, request, _change_connection(connection_id, body), body.expected_version)

    @router.delete(base + "/connections/{connection_id}", status_code=204)
    def delete_connection(organization_id: UUID, model_id: UUID, event_id: UUID, connection_id: UUID, expected_version: int, request: Request, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> Response:
        _edit_event(session_factory, clock, organization_id, model_id, event_id, user, request, _remove_connection(connection_id), expected_version)
        return Response(status_code=204)

    return router
