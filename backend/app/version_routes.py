"""Model versions: the baseline and versions forked from it (Shadow feature 2).

A fork copies the base version's whole graph; every copied node remembers its origin, so the
changes against the base (added, removed, changed nodes and connections) can be listed.
Every member can create and edit versions; Owners and Admins delete them. The baseline cannot
be deleted.
"""

from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.auth import AuthenticatedUser
from app.auth_routes import AuthenticatedUserDependency
from app.model_routes import (
    MANAGERS,
    VersionResponse,
    _audit,
    _editor_session,
    _manager_session,
    _member_session,
    _model,
    _stale,
    baseline_of,
    version_of,
)
from app.metric_routes import copy_metrics
from app.models import Connection, ModelVersion, Node


class VersionRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    base_version_id: UUID | None = None

    @field_validator("name")
    @classmethod
    def trimmed(cls, value: str) -> str:
        if not (value := " ".join(value.split())):
            raise ValueError("must not be blank")
        return value


class VersionUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    expected_version: int = Field(ge=1)


class NodeChange(BaseModel):
    node_id: UUID
    name: str
    fields: list[str] = []


class ConnectionChange(BaseModel):
    connection_id: UUID
    connection_type_id: UUID
    source: str
    target: str


class DiffResponse(BaseModel):
    version: VersionResponse
    base: VersionResponse | None
    added_nodes: list[NodeChange]
    removed_nodes: list[NodeChange]
    changed_nodes: list[NodeChange]
    added_connections: list[ConnectionChange]
    removed_connections: list[ConnectionChange]


def fork_version(session: Session, base: ModelVersion, name: str, description: str | None) -> ModelVersion:
    """Copy ``base``'s graph into a new version that records where each node came from."""
    fork = ModelVersion(id=uuid4(), organization_id=base.organization_id, model_id=base.model_id, name=name, description=description, is_baseline=False, base_version_id=base.id, version=1)
    session.add(fork)
    session.flush()
    mapping: dict[UUID, UUID] = {}
    for node in session.scalars(select(Node).where(Node.version_id == base.id).order_by(Node.created_at, Node.id)).all():
        copy = Node(id=uuid4(), organization_id=node.organization_id, model_id=node.model_id, version_id=fork.id, origin_node_id=node.id, node_type_id=node.node_type_id, name=node.name, description=node.description, x=node.x, y=node.y, version=1)
        mapping[node.id] = copy.id
        session.add(copy)
    session.flush()
    for connection in session.scalars(select(Connection).where(Connection.version_id == base.id)).all():
        session.add(Connection(id=uuid4(), organization_id=connection.organization_id, model_id=connection.model_id, version_id=fork.id, connection_type_id=connection.connection_type_id, source_node_id=mapping[connection.source_node_id], target_node_id=mapping[connection.target_node_id], version=1))
    session.flush()
    copy_metrics(session, base.id, fork.id, mapping)
    return fork


def diff_of(session: Session, version: ModelVersion) -> DiffResponse:
    base = session.get(ModelVersion, version.base_version_id) if version.base_version_id else None
    response = DiffResponse(version=VersionResponse.model_validate(version, from_attributes=True), base=VersionResponse.model_validate(base, from_attributes=True) if base else None, added_nodes=[], removed_nodes=[], changed_nodes=[], added_connections=[], removed_connections=[])
    if base is None:
        return response
    base_nodes = {node.id: node for node in session.scalars(select(Node).where(Node.version_id == base.id)).all()}
    nodes = session.scalars(select(Node).where(Node.version_id == version.id)).all()
    origin_of = {node.id: node.origin_node_id for node in nodes}
    kept = {node.origin_node_id for node in nodes if node.origin_node_id}
    for node in nodes:
        origin = base_nodes.get(node.origin_node_id) if node.origin_node_id else None
        if origin is None:
            response.added_nodes.append(NodeChange(node_id=node.id, name=node.name))
            continue
        fields = [field for field in ("name", "description", "node_type_id") if getattr(node, field) != getattr(origin, field)]
        if fields:
            response.changed_nodes.append(NodeChange(node_id=node.id, name=node.name, fields=fields))
    for node_id, node in base_nodes.items():
        if node_id not in kept:
            response.removed_nodes.append(NodeChange(node_id=node.id, name=node.name))
    names = {node.id: node.name for node in nodes} | {node.id: node.name for node in base_nodes.values()}
    base_keys = {(c.connection_type_id, c.source_node_id, c.target_node_id): c for c in session.scalars(select(Connection).where(Connection.version_id == base.id)).all()}
    keys: set[tuple[UUID, UUID | None, UUID | None]] = set()
    for connection in session.scalars(select(Connection).where(Connection.version_id == version.id)).all():
        key = (connection.connection_type_id, origin_of.get(connection.source_node_id), origin_of.get(connection.target_node_id))
        keys.add(key)
        if key not in base_keys:
            response.added_connections.append(ConnectionChange(connection_id=connection.id, connection_type_id=connection.connection_type_id, source=names[connection.source_node_id], target=names[connection.target_node_id]))
    for key, connection in base_keys.items():
        if key not in keys:
            response.removed_connections.append(ConnectionChange(connection_id=connection.id, connection_type_id=connection.connection_type_id, source=names[connection.source_node_id], target=names[connection.target_node_id]))
    return response


def create_version_router(*, session_factory: sessionmaker[Session], authenticated_user_dependency: AuthenticatedUserDependency) -> APIRouter:
    router = APIRouter(prefix="/api/v1/organizations", tags=["Versions"])

    @router.get("/{organization_id}/models/{model_id}/versions", response_model=list[VersionResponse])
    def list_versions(organization_id: UUID, model_id: UUID, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> list[VersionResponse]:
        with _member_session(session_factory, organization_id, user) as (session, _membership):
            _model(session, organization_id, model_id)
            versions = session.scalars(select(ModelVersion).where(ModelVersion.model_id == model_id).order_by(ModelVersion.is_baseline.desc(), ModelVersion.created_at)).all()
            return [VersionResponse.model_validate(item, from_attributes=True) for item in versions]

    @router.post("/{organization_id}/models/{model_id}/versions", response_model=VersionResponse, status_code=201)
    def create_version(organization_id: UUID, model_id: UUID, body: VersionRequest, request: Request, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> VersionResponse:
        with _editor_session(session_factory, organization_id, user) as session:
            model = _model(session, organization_id, model_id)
            base = version_of(session, organization_id, model.id, body.base_version_id)
            if session.scalar(select(ModelVersion.id).where(ModelVersion.model_id == model.id, func.lower(ModelVersion.name) == body.name.lower())) is not None:
                raise HTTPException(status_code=409, detail={"reason": "duplicate_name"})
            fork = fork_version(session, base, body.name, body.description)
            _audit(session, request, "version.created", "model_version", fork.id, {"model_id": str(model.id), "name": fork.name, "base": base.name})
            return VersionResponse.model_validate(fork, from_attributes=True)

    @router.patch("/{organization_id}/models/{model_id}/versions/{version_id}", response_model=VersionResponse)
    def update_version(organization_id: UUID, model_id: UUID, version_id: UUID, body: VersionUpdate, request: Request, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> VersionResponse:
        with _editor_session(session_factory, organization_id, user) as session:
            version = version_of(session, organization_id, model_id, version_id, lock=True)
            _stale(version.version, body.expected_version)
            if version.is_baseline and body.name.lower() != version.name.lower():
                raise HTTPException(status_code=422, detail="the baseline keeps its name")
            duplicate = session.scalar(select(ModelVersion.id).where(ModelVersion.model_id == model_id, func.lower(ModelVersion.name) == body.name.lower(), ModelVersion.id != version.id))
            if duplicate is not None:
                raise HTTPException(status_code=409, detail={"reason": "duplicate_name"})
            changes = {key: value for key, value in (("name", body.name), ("description", body.description)) if getattr(version, key) != value}
            version.name, version.description = body.name, body.description
            version.version += 1
            _audit(session, request, "version.updated", "model_version", version.id, changes)
            return VersionResponse.model_validate(version, from_attributes=True)

    @router.delete("/{organization_id}/models/{model_id}/versions/{version_id}", status_code=204)
    def delete_version(organization_id: UUID, model_id: UUID, version_id: UUID, expected_version: int, request: Request, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> Response:
        with _manager_session(session_factory, organization_id, user) as session:
            version = version_of(session, organization_id, model_id, version_id, lock=True)
            if version.is_baseline:
                raise HTTPException(status_code=422, detail="the baseline cannot be deleted")
            _stale(version.version, expected_version)
            if session.scalar(select(ModelVersion.id).where(ModelVersion.base_version_id == version.id)) is not None:
                raise HTTPException(status_code=409, detail={"reason": "has_forks"})
            _audit(session, request, "version.deleted", "model_version", version.id, {"name": version.name})
            session.delete(version)
        return Response(status_code=204)

    @router.get("/{organization_id}/models/{model_id}/versions/{version_id}/changes", response_model=DiffResponse)
    def changes(organization_id: UUID, model_id: UUID, version_id: UUID, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> DiffResponse:
        with _member_session(session_factory, organization_id, user) as (session, _membership):
            _model(session, organization_id, model_id)
            return diff_of(session, version_of(session, organization_id, model_id, version_id))

    return router


__all__ = ["MANAGERS", "baseline_of", "create_version_router", "diff_of", "fork_version"]
