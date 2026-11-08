"""Models (digital twins) and their graph: nodes and connections (Shadow feature 1).

A Model belongs to an Organization. Every member can read and edit the graph; Owners and
Admins create, rename, and delete Models. A new Model starts with the default metamodel:
node types, connection types, and which types may connect. Writes carry ``expected_version``
(409 on a stale one) and are audited. Row-level security keeps every row inside its
Organization; the composite foreign keys keep a graph inside its Model.
"""

import json
from contextlib import contextmanager
from datetime import datetime
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
    Connection,
    ConnectionType,
    ModelLine,
    ModelVersion,
    Node,
    NodeType,
    Organization,
    OrganizationMembership,
    OrganizationRole,
    TimelineEvent,
    TwinModel,
)
from app.subscription_access import require_organization_mutation_access

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


class NodeRequest(BaseModel):
    version_id: UUID | None = None
    node_type_id: UUID
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=4000)
    x: float = 0
    y: float = 0

    @field_validator("name")
    @classmethod
    def trimmed(cls, value: str) -> str:
        if not (value := " ".join(value.split())):
            raise ValueError("must not be blank")
        return value


class NodeUpdate(BaseModel):
    expected_version: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=4000)
    x: float | None = None
    y: float | None = None


class ConnectionRequest(BaseModel):
    connection_type_id: UUID
    source_node_id: UUID
    target_node_id: UUID


class VersionResponse(BaseModel):
    id: UUID
    name: str
    description: str | None
    is_baseline: bool
    base_version_id: UUID | None
    version: int


class NodeResponse(BaseModel):
    id: UUID
    node_type_id: UUID
    name: str
    description: str | None
    x: float
    y: float
    version: int


class ConnectionResponse(BaseModel):
    id: UUID
    connection_type_id: UUID
    source_node_id: UUID
    target_node_id: UUID
    version: int


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


class GraphResponse(BaseModel):
    model: ModelResponse
    version: VersionResponse
    versions: list[VersionResponse]
    node_types: list[NodeTypeResponse]
    connection_types: list[ConnectionTypeResponse]
    allowed_connections: list[AllowedConnectionResponse]
    nodes: list[NodeResponse]
    connections: list[ConnectionResponse]


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


def baseline_of(session: Session, model_id: UUID) -> ModelVersion:
    return session.scalars(select(ModelVersion).where(ModelVersion.model_id == model_id, ModelVersion.is_baseline.is_(True))).one()


def version_of(session: Session, organization_id: UUID, model_id: UUID, version_id: UUID | None, *, lock: bool = False) -> ModelVersion:
    """The requested version of the Model, or its baseline."""
    if version_id is None:
        return baseline_of(session, model_id)
    statement = select(ModelVersion).where(ModelVersion.id == version_id, ModelVersion.model_id == model_id, ModelVersion.organization_id == organization_id)
    version = session.scalar(statement.with_for_update() if lock else statement)
    if version is None:
        raise HTTPException(status_code=404, detail="Version not found")
    return version


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


def _model_response(session: Session, model: TwinModel) -> ModelResponse:
    nodes = session.scalar(select(func.count()).select_from(Node).where(Node.version_id == baseline_of(session, model.id).id)) or 0
    return ModelResponse(id=model.id, name=model.name, description=model.description, version=model.version, nodes=nodes)


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


def graph_of(session_factory: sessionmaker[Session], organization_id: UUID, model_id: UUID, user: AuthenticatedUser, version_id: UUID | None = None) -> GraphResponse:
    with _member_session(session_factory, organization_id, user) as (session, _membership):
        model = _model(session, organization_id, model_id)
        version = version_of(session, organization_id, model.id, version_id)
        by_model = lambda entity: select(entity).where(entity.model_id == model.id)  # noqa: E731
        by_version = lambda entity: select(entity).where(entity.version_id == version.id)  # noqa: E731
        versions = session.scalars(by_model(ModelVersion).order_by(ModelVersion.is_baseline.desc(), ModelVersion.created_at)).all()
        return GraphResponse(
            model=_model_response(session, model),
            version=VersionResponse.model_validate(version, from_attributes=True),
            versions=[VersionResponse.model_validate(item, from_attributes=True) for item in versions],
            node_types=[NodeTypeResponse.model_validate(item, from_attributes=True) for item in session.scalars(by_model(NodeType).order_by(NodeType.name)).all()],
            connection_types=[ConnectionTypeResponse.model_validate(item, from_attributes=True) for item in session.scalars(by_model(ConnectionType).order_by(ConnectionType.name)).all()],
            allowed_connections=[AllowedConnectionResponse.model_validate(item, from_attributes=True) for item in session.scalars(by_model(AllowedConnection)).all()],
            nodes=[NodeResponse.model_validate(item, from_attributes=True) for item in session.scalars(by_version(Node).order_by(Node.created_at, Node.id)).all()],
            connections=[ConnectionResponse.model_validate(item, from_attributes=True) for item in session.scalars(by_version(Connection).order_by(Connection.created_at, Connection.id)).all()],
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
            # The Base line shares its id with the baseline version, as migration 0061 does for existing Models (ticket 04 drops the version).
            baseline_id = uuid4()
            session.add(ModelVersion(id=baseline_id, organization_id=organization_id, model_id=model.id, name="Baseline", is_baseline=True, version=1))
            session.add(ModelLine(id=baseline_id, organization_id=organization_id, model_id=model.id, name="Baseline", kind="base", created_by_user_account_id=user.account.id, version=1))
            session.flush()
            # Rule 1 of the domain model: every Model has a Base line with an empty "Initial situation" event dated the creation day.
            session.add(TimelineEvent(id=uuid4(), organization_id=organization_id, model_id=model.id, line_id=baseline_id, occurred_on=_today_in_organization(session, organization_id), title="Initial situation", created_by_user_account_id=user.account.id))
            seed_metamodel(session, model)
            _audit(session, request, "model.created", "model", model.id, {"name": model.name})
            return _model_response(session, model)

    @router.get("/{organization_id}/models/{model_id}", response_model=GraphResponse)
    def read_graph(organization_id: UUID, model_id: UUID, version_id: UUID | None = None, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> GraphResponse:
        return graph_of(session_factory, organization_id, model_id, user, version_id)

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

    @router.post("/{organization_id}/models/{model_id}/nodes", response_model=NodeResponse, status_code=201)
    def create_node(organization_id: UUID, model_id: UUID, body: NodeRequest, request: Request, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> NodeResponse:
        with _editor_session(session_factory, organization_id, user) as session:
            model = _model(session, organization_id, model_id)
            if session.scalar(select(NodeType.id).where(NodeType.id == body.node_type_id, NodeType.model_id == model.id)) is None:
                raise HTTPException(status_code=422, detail="node type not found in this Model")
            version = version_of(session, organization_id, model.id, body.version_id)
            node = Node(id=uuid4(), organization_id=organization_id, model_id=model.id, version_id=version.id, node_type_id=body.node_type_id, name=body.name, description=body.description, x=body.x, y=body.y, version=1)
            session.add(node)
            session.flush()
            _audit(session, request, "node.created", "node", node.id, {"model_id": str(model.id), "name": node.name})
            return NodeResponse.model_validate(node, from_attributes=True)

    @router.patch("/{organization_id}/models/{model_id}/nodes/{node_id}", response_model=NodeResponse)
    def update_node(organization_id: UUID, model_id: UUID, node_id: UUID, body: NodeUpdate, request: Request, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> NodeResponse:
        with _editor_session(session_factory, organization_id, user) as session:
            node = _node(session, organization_id, model_id, node_id, lock=True)
            _stale(node.version, body.expected_version)
            changes = {}
            for key in ("name", "description", "x", "y"):
                value = getattr(body, key)
                if key in body.model_fields_set and value != getattr(node, key):
                    if key == "name" and value is None:
                        raise HTTPException(status_code=422, detail="name must not be empty")
                    changes[key] = value
                    setattr(node, key, value)
            if changes:
                node.version += 1
                moved_only = set(changes) <= {"x", "y"}
                if not moved_only:  # dragging a node on the canvas is not worth an audit entry per move
                    _audit(session, request, "node.updated", "node", node.id, {key: value for key, value in changes.items() if key != "description"})
            return NodeResponse.model_validate(node, from_attributes=True)

    @router.delete("/{organization_id}/models/{model_id}/nodes/{node_id}", status_code=204)
    def delete_node(organization_id: UUID, model_id: UUID, node_id: UUID, expected_version: int, request: Request, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> Response:
        with _editor_session(session_factory, organization_id, user) as session:
            node = _node(session, organization_id, model_id, node_id, lock=True)
            _stale(node.version, expected_version)
            _audit(session, request, "node.deleted", "node", node.id, {"model_id": str(model_id), "name": node.name})
            session.delete(node)
        return Response(status_code=204)

    @router.post("/{organization_id}/models/{model_id}/connections", response_model=ConnectionResponse, status_code=201)
    def create_connection(organization_id: UUID, model_id: UUID, body: ConnectionRequest, request: Request, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> ConnectionResponse:
        with _editor_session(session_factory, organization_id, user) as session:
            model = _model(session, organization_id, model_id)
            source = _node(session, organization_id, model.id, body.source_node_id)
            target = _node(session, organization_id, model.id, body.target_node_id)
            if source.id == target.id:
                raise HTTPException(status_code=422, detail="a node cannot connect to itself")
            if source.version_id != target.version_id:
                raise HTTPException(status_code=422, detail="both nodes must belong to the same version")
            allowed = session.scalar(select(AllowedConnection.id).where(AllowedConnection.model_id == model.id, AllowedConnection.connection_type_id == body.connection_type_id, AllowedConnection.source_node_type_id == source.node_type_id, AllowedConnection.target_node_type_id == target.node_type_id))
            if allowed is None:
                raise HTTPException(status_code=422, detail="this connection type is not allowed between these node types")
            duplicate = session.scalar(select(Connection.id).where(Connection.connection_type_id == body.connection_type_id, Connection.source_node_id == source.id, Connection.target_node_id == target.id))
            if duplicate is not None:
                raise HTTPException(status_code=409, detail={"reason": "duplicate_connection"})
            connection = Connection(id=uuid4(), organization_id=organization_id, model_id=model.id, version_id=source.version_id, connection_type_id=body.connection_type_id, source_node_id=source.id, target_node_id=target.id, version=1)
            session.add(connection)
            session.flush()
            _audit(session, request, "connection.created", "connection", connection.id, {"model_id": str(model.id), "source": source.name, "target": target.name})
            return ConnectionResponse.model_validate(connection, from_attributes=True)

    @router.delete("/{organization_id}/models/{model_id}/connections/{connection_id}", status_code=204)
    def delete_connection(organization_id: UUID, model_id: UUID, connection_id: UUID, expected_version: int, request: Request, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> Response:
        with _editor_session(session_factory, organization_id, user) as session:
            connection = session.scalar(select(Connection).where(Connection.id == connection_id, Connection.model_id == model_id, Connection.organization_id == organization_id).with_for_update())
            if connection is None:
                raise HTTPException(status_code=404, detail="Connection not found")
            _stale(connection.version, expected_version)
            _audit(session, request, "connection.deleted", "connection", connection.id, {"model_id": str(model_id)})
            session.delete(connection)
        return Response(status_code=204)

    return router


def _node(session: Session, organization_id: UUID, model_id: UUID, node_id: UUID, *, lock: bool = False) -> Node:
    statement = select(Node).where(Node.id == node_id, Node.model_id == model_id, Node.organization_id == organization_id)
    node = session.scalar(statement.with_for_update() if lock else statement)
    if node is None:
        raise HTTPException(status_code=404, detail="Node not found")
    return node
