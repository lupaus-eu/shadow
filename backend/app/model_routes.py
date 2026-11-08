"""Models (digital twins): the Model, its metamodel and the graph a line shows (Shadow feature 1, model timeline).

A Model belongs to an Organization. Every member can read the graph; the graph itself is a replay of the changes of
a line (``timeline_*`` routes). Owners and Admins create, rename, and delete Models. A new Model starts with the
default metamodel and a Base line holding an empty "Initial situation" change. Writes carry ``expected_version``
(409 on a stale one) and are audited. Row-level security keeps every row inside its Organization.
"""

import json
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.audit import AuditEventDraft, record_audit_event
from app.auth import AuthenticatedUser
from app.auth_routes import AuthenticatedUserDependency
from app.database import RequestContext, apply_request_context, transaction_session
from app.models import (
    AllowedConnection,
    ConnectionType,
    ModelLine,
    NodeType,
    Organization,
    OrganizationMembership,
    OrganizationRole,
    TimelineChange,
    TwinModel,
)
from app.subscription_access import require_organization_mutation_access
from app.timeline.chain import state_after
from app.timeline.errors import ChainBroken
from app.timeline.loader import ModelTimeline, load_timeline
from app.timeline.state import State

MANAGERS = {OrganizationRole.OWNER.value, OrganizationRole.ADMIN.value}
DEFAULT_METAMODEL = json.loads((Path(__file__).parent / "default_metamodel.json").read_text())


class ModelRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)

    @field_validator("name")
    @classmethod
    def trimmed(cls, value: str) -> str:
        if not (value := " ".join(value.split())):
            raise ValueError("must not be blank")
        return value


class ModelUpdate(ModelRequest):
    expected_version: int = Field(ge=1)


class ModelResponse(BaseModel):
    id: UUID
    name: str
    description: str | None
    version: int
    nodes: int = 0
    base_line_id: UUID | None = None  # the Base line: GET /lines lists the others


class NodeResponse(BaseModel):
    id: UUID
    node_type_id: UUID
    name: str
    description: str | None
    x: float
    y: float


class ConnectionResponse(BaseModel):
    id: UUID
    connection_type_id: UUID
    source_node_id: UUID
    target_node_id: UUID


class LatestChangeResponse(BaseModel):
    """The last change of the shown line: the one canvas edits and ``create_node`` / ``create_connection`` write into."""

    id: UUID
    version: int
    occurred_on: date
    title: str


class NodeTypeResponse(BaseModel):
    id: UUID
    key: str
    name: str
    color: str
    shape: str
    version: int


class ConnectionTypeResponse(BaseModel):
    id: UUID
    key: str
    name: str
    style: str
    source_end: str
    target_end: str
    version: int


class AllowedConnectionResponse(BaseModel):
    connection_type_id: UUID
    source_node_type_id: UUID
    target_node_type_id: UUID


class LineResponse(BaseModel):
    id: UUID
    name: str
    description: str | None
    kind: str
    parent_line_id: UUID | None
    branch_change_id: UUID | None
    start_changed_at: datetime | None
    created_by_user_account_id: UUID | None
    version: int
    created_at: datetime
    change_count: int
    latest_change_date: date | None


class GraphResponse(BaseModel):
    model: ModelResponse
    line: LineResponse  # the line whose graph is shown (the Base line unless a line_id is given)
    lines: list[LineResponse]  # the Base line first, then the Scenarios
    node_types: list[NodeTypeResponse]
    connection_types: list[ConnectionTypeResponse]
    allowed_connections: list[AllowedConnectionResponse]
    nodes: list[NodeResponse]
    connections: list[ConnectionResponse]
    latest_change: LatestChangeResponse | None = None


@contextmanager
def _member_session(session_factory: sessionmaker, organization_id: UUID, user: AuthenticatedUser):
    with transaction_session(session_factory, RequestContext(user_account_id=user.account.id)) as session:
        membership = session.scalar(select(OrganizationMembership).where(OrganizationMembership.organization_id == organization_id, OrganizationMembership.user_account_id == user.account.id))
        if membership is None:
            raise HTTPException(status_code=404, detail="Organization not found")
        apply_request_context(session, RequestContext(user_account_id=user.account.id, organization_id=organization_id))
        yield session, membership


@contextmanager
def _editor_session(session_factory: sessionmaker, organization_id: UUID, user: AuthenticatedUser):
    with _member_session(session_factory, organization_id, user) as (session, membership):
        require_organization_mutation_access(session, organization_id)
        yield session


@contextmanager
def _manager_session(session_factory: sessionmaker, organization_id: UUID, user: AuthenticatedUser):
    with _member_session(session_factory, organization_id, user) as (session, membership):
        if membership.role not in MANAGERS:
            raise HTTPException(status_code=403, detail="Owner or Admin required")
        require_organization_mutation_access(session, organization_id)
        yield session


def _audit(session: Session, request: Request, action: str, target_type: str, target_id: UUID, summary: dict) -> None:
    record_audit_event(session, AuditEventDraft(action=action, target_type=target_type, target_id=target_id, request_id=(request.headers.get("X-Request-ID") or str(uuid4()))[:120], change_summary=summary))


def _today_in_organization(session: Session, organization_id: UUID):
    """Today's date in the Organization's time zone (UTC if the zone is unknown)."""
    name = session.scalar(select(Organization.time_zone).where(Organization.id == organization_id))
    try:
        zone = ZoneInfo(name) if name else ZoneInfo("UTC")
    except ZoneInfoNotFoundError:
        zone = ZoneInfo("UTC")
    return datetime.now(zone).date()


def _model(session: Session, organization_id: UUID, model_id: UUID, *, lock: bool = False) -> TwinModel:
    statement = select(TwinModel).where(TwinModel.id == model_id, TwinModel.organization_id == organization_id)
    model = session.scalar(statement.with_for_update() if lock else statement)
    if model is None:
        raise HTTPException(status_code=404, detail="Model not found")
    return model


def line_of(session: Session, organization_id: UUID, model_id: UUID, line_id: UUID, *, lock: bool = False) -> ModelLine:
    """The line (Base line or Scenario) of the Model; 404 when it is not one of this Model's."""
    statement = select(ModelLine).where(ModelLine.id == line_id, ModelLine.model_id == model_id, ModelLine.organization_id == organization_id)
    line = session.scalar(statement.with_for_update() if lock else statement)
    if line is None:
        raise HTTPException(status_code=404, detail="Line not found")
    return line


def _stale(current: int, expected: int) -> None:
    if current != expected:
        raise HTTPException(status_code=409, detail={"latest_version": current})


def _latest_state(timeline: ModelTimeline, line_id: UUID) -> tuple[State, TimelineChange | None]:
    """The graph after the last change of a line (including planned changes) and that change; empty if the chain cannot be replayed."""
    own = timeline.changes_of(line_id) if line_id in timeline.lines else []
    last = own[-1] if own else None
    try:
        return state_after(timeline.lines, timeline.changes, timeline.metamodel, line_id, last.id if last else None), (timeline.change_rows[last.id] if last else None)
    except ChainBroken:
        return State(), None


def _model_response(session: Session, model: TwinModel, timeline: ModelTimeline | None = None) -> ModelResponse:
    """``nodes`` counts the Base line's graph after its last change, which takes one replay of the Model's timeline."""
    base = session.scalar(select(ModelLine.id).where(ModelLine.model_id == model.id, ModelLine.kind == "base"))
    nodes = len(_latest_state(timeline or load_timeline(session, model.id), base)[0].nodes) if base is not None else 0
    return ModelResponse(id=model.id, name=model.name, description=model.description, version=model.version, nodes=nodes, base_line_id=base)


def seed_metamodel(session: Session, model: TwinModel) -> None:
    """Give a new Model the default node types, connection types, and allowed connections."""
    node_types = {item["key"]: NodeType(id=uuid4(), organization_id=model.organization_id, model_id=model.id, key=item["key"], name=item["name"], color=item["color"], shape=item["shape"]) for item in DEFAULT_METAMODEL["node_types"]}
    connection_types = {item["key"]: ConnectionType(id=uuid4(), organization_id=model.organization_id, model_id=model.id, key=item["key"], name=item["name"], style=item["style"], source_end=item["source_end"], target_end=item["target_end"]) for item in DEFAULT_METAMODEL["connection_types"]}
    session.add_all([*node_types.values(), *connection_types.values()])
    session.flush()
    session.add_all(
        AllowedConnection(id=uuid4(), organization_id=model.organization_id, model_id=model.id, connection_type_id=connection_types[item["key"]].id, source_node_type_id=node_types[source].id, target_node_type_id=node_types[target].id)
        for item in DEFAULT_METAMODEL["connection_types"]
        for source, target in item["allowed"]
    )


def models_of(session_factory: sessionmaker[Session], organization_id: UUID, user: AuthenticatedUser) -> list[ModelResponse]:
    with _member_session(session_factory, organization_id, user) as (session, _membership):
        models = session.scalars(select(TwinModel).where(TwinModel.organization_id == organization_id).order_by(func.lower(TwinModel.name))).all()
        return [_model_response(session, model) for model in models]


def graph_of(session_factory: sessionmaker[Session], organization_id: UUID, model_id: UUID, user: AuthenticatedUser, line_id: UUID | None = None) -> GraphResponse:
    """The Model with the lines and the graph of one line (the Base line unless given) after its last change."""
    from app.timeline_routes import _line_response, _resolve_positions  # a function-level import: timeline_routes imports this module

    with _member_session(session_factory, organization_id, user) as (session, _membership):
        model = _model(session, organization_id, model_id)
        timeline = load_timeline(session, model.id)
        if line_id is not None:
            shown = line_of(session, organization_id, model.id, line_id).id
        else:
            shown = next(row.id for row in timeline.line_rows.values() if row.kind == "base")
        by_model = lambda entity: select(entity).where(entity.model_id == model.id)  # noqa: E731
        ordered = sorted(timeline.line_rows.values(), key=lambda row: (row.kind != "base", row.created_at, row.id))
        state, latest = _latest_state(timeline, shown)
        drawn = _resolve_positions(session, timeline, shown, state)
        return GraphResponse(
            model=_model_response(session, model, timeline),
            line=_line_response(timeline, shown),
            lines=[_line_response(timeline, row.id) for row in ordered],
            node_types=[NodeTypeResponse.model_validate(item, from_attributes=True) for item in session.scalars(by_model(NodeType).order_by(NodeType.name)).all()],
            connection_types=[ConnectionTypeResponse.model_validate(item, from_attributes=True) for item in session.scalars(by_model(ConnectionType).order_by(ConnectionType.name)).all()],
            allowed_connections=[AllowedConnectionResponse.model_validate(item, from_attributes=True) for item in session.scalars(by_model(AllowedConnection)).all()],
            nodes=[NodeResponse(id=node.id, node_type_id=node.node_type_id, name=node.name, description=node.description, x=drawn.get(node.id, (node.x, node.y))[0], y=drawn.get(node.id, (node.x, node.y))[1]) for node in state.nodes.values()],
            connections=[ConnectionResponse(id=item.id, connection_type_id=item.connection_type_id, source_node_id=item.source_node_id, target_node_id=item.target_node_id) for item in state.connections.values()],
            latest_change=LatestChangeResponse(id=latest.id, version=latest.version, occurred_on=latest.occurred_on, title=latest.title) if latest is not None else None,
        )


def create_model_router(*, session_factory: sessionmaker[Session], authenticated_user_dependency: AuthenticatedUserDependency) -> APIRouter:
    router = APIRouter(prefix="/api/v1/organizations", tags=["Models"])

    @router.get("/{organization_id}/models", response_model=list[ModelResponse])
    def list_models(organization_id: UUID, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> list[ModelResponse]:
        return models_of(session_factory, organization_id, user)

    @router.post("/{organization_id}/models", response_model=ModelResponse, status_code=201)
    def create_model(organization_id: UUID, body: ModelRequest, request: Request, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> ModelResponse:
        with _manager_session(session_factory, organization_id, user) as session:
            if session.scalar(select(TwinModel.id).where(TwinModel.organization_id == organization_id, func.lower(TwinModel.name) == body.name.lower())) is not None:
                raise HTTPException(status_code=409, detail={"reason": "duplicate_name"})
            model = TwinModel(id=uuid4(), organization_id=organization_id, name=body.name, description=body.description, version=1)
            session.add(model)
            session.flush()
            baseline_id = uuid4()
            session.add(ModelLine(id=baseline_id, organization_id=organization_id, model_id=model.id, name="Baseline", kind="base", created_by_user_account_id=user.account.id, version=1))
            session.flush()
            # Rule 1 of the domain model: every Model has a Base line with an empty "Initial situation" change dated the creation day.
            session.add(TimelineChange(id=uuid4(), organization_id=organization_id, model_id=model.id, line_id=baseline_id, occurred_on=_today_in_organization(session, organization_id), title="Initial situation", created_by_user_account_id=user.account.id))
            seed_metamodel(session, model)
            _audit(session, request, "model.created", "model", model.id, {"name": model.name})
            return _model_response(session, model)

    @router.get("/{organization_id}/models/{model_id}", response_model=GraphResponse)
    def read_graph(organization_id: UUID, model_id: UUID, line_id: UUID | None = None, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> GraphResponse:
        return graph_of(session_factory, organization_id, model_id, user, line_id)

    @router.patch("/{organization_id}/models/{model_id}", response_model=ModelResponse)
    def update_model(organization_id: UUID, model_id: UUID, body: ModelUpdate, request: Request, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> ModelResponse:
        with _manager_session(session_factory, organization_id, user) as session:
            model = _model(session, organization_id, model_id, lock=True)
            _stale(model.version, body.expected_version)
            duplicate = session.scalar(select(TwinModel.id).where(TwinModel.organization_id == organization_id, func.lower(TwinModel.name) == body.name.lower(), TwinModel.id != model.id))
            if duplicate is not None:
                raise HTTPException(status_code=409, detail={"reason": "duplicate_name"})
            changes = {key: value for key, value in (("name", body.name), ("description", body.description)) if getattr(model, key) != value}
            model.name, model.description = body.name, body.description
            model.version += 1
            _audit(session, request, "model.updated", "model", model.id, changes)
            return _model_response(session, model)

    @router.delete("/{organization_id}/models/{model_id}", status_code=204)
    def delete_model(organization_id: UUID, model_id: UUID, expected_version: int, request: Request, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> Response:
        with _manager_session(session_factory, organization_id, user) as session:
            model = _model(session, organization_id, model_id, lock=True)
            _stale(model.version, expected_version)
            _audit(session, request, "model.deleted", "model", model.id, {"name": model.name})
            session.delete(model)
        return Response(status_code=204)

    return router

