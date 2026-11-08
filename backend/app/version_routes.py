"""Model versions: the baseline and versions forked from it (Shadow feature 2).

A fork copies the base version's whole graph; every copied node remembers its origin, so the
changes against the base (added, removed, changed nodes and connections) can be listed. Until the
model-timeline tickets 06 to 08 replace these routes, a fork also gets a Scenario line with the same id
(ADR-0048) so its metrics, simulations and analysis hang off a line; deleting a version deletes its line.
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
    _today_in_organization,
    baseline_of,
    version_of,
)
from app.metric_routes import copy_metrics
from app.models import Connection, ModelLine, ModelVersion, Node, TimelineEvent


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


class MergeRequest(BaseModel):
    expected_version: int = Field(ge=1)


class MergeResponse(BaseModel):
    base: VersionResponse
    added_nodes: int
    removed_nodes: int
    changed_nodes: int
    added_connections: int
    removed_connections: int
    skipped_connections: int


def merge_version(session: Session, version: ModelVersion) -> MergeResponse:
    """Apply the changes of ``version`` to the version it was forked from.

    Removed nodes and connections are deleted from the base, changed nodes copy their name,
    description and type, and added nodes and connections are created there. Afterwards the
    version's added nodes point at their new twins, so the version shows no changes against the
    base. Metrics are not merged. A node the base lost since the fork comes back as added.
    """
    diff = diff_of(session, version)
    if diff.base is None:
        raise HTTPException(status_code=422, detail="the baseline has nothing to merge into")
    base_id = diff.base.id
    removed_connections = [session.get(Connection, item.connection_id) for item in diff.removed_connections]
    for connection in removed_connections:
        if connection is not None:
            session.delete(connection)
    session.flush()
    for item in diff.removed_nodes:
        if (node := session.get(Node, item.node_id)) is not None:
            session.delete(node)
    session.flush()
    mapping: dict[UUID, UUID] = {}  # a node of this version -> its node in the base
    for node in session.scalars(select(Node).where(Node.version_id == version.id)).all():
        if node.origin_node_id is not None:
            mapping[node.id] = node.origin_node_id
    for item in diff.changed_nodes:
        node = session.get(Node, item.node_id)
        target = session.get(Node, node.origin_node_id) if node and node.origin_node_id else None
        if node is not None and target is not None:
            target.name, target.description, target.node_type_id = node.name, node.description, node.node_type_id
            target.version += 1
    for item in diff.added_nodes:
        node = session.get(Node, item.node_id)
        twin = Node(id=uuid4(), organization_id=node.organization_id, model_id=node.model_id, version_id=base_id, node_type_id=node.node_type_id, name=node.name, description=node.description, x=node.x, y=node.y, version=1)
        session.add(twin)
        session.flush()
        mapping[node.id] = twin.id
        node.origin_node_id = twin.id
    skipped = 0
    for item in diff.added_connections:
        connection = session.get(Connection, item.connection_id)
        source, target = mapping.get(connection.source_node_id), mapping.get(connection.target_node_id)
        duplicate = source and target and session.scalar(select(Connection.id).where(Connection.connection_type_id == connection.connection_type_id, Connection.source_node_id == source, Connection.target_node_id == target))
        if not source or not target or duplicate:
            skipped += 1
            continue
        session.add(Connection(id=uuid4(), organization_id=connection.organization_id, model_id=connection.model_id, version_id=base_id, connection_type_id=connection.connection_type_id, source_node_id=source, target_node_id=target, version=1))
    session.flush()
    base = session.get(ModelVersion, base_id)
    return MergeResponse(
        base=VersionResponse.model_validate(base, from_attributes=True),
        added_nodes=len(diff.added_nodes),
        removed_nodes=len(diff.removed_nodes),
        changed_nodes=len(diff.changed_nodes),
        added_connections=len(diff.added_connections) - skipped,
        removed_connections=sum(1 for connection in removed_connections if connection is not None),
        skipped_connections=skipped,
    )


def _fork_line(session: Session, base: ModelVersion, fork: ModelVersion, created_by: UUID | None) -> None:
    """Give the new version a Scenario line of the same id, branching from the base line's last event.

    A base line without an event first gets an empty "Initial situation" event dated today (a Scenario must
    branch from an event). The Scenario has no events yet, so it is dated on or after its branch event by
    construction; the graph still lives in the old tables until ticket 08.
    """
    if session.get(ModelLine, base.id) is None:  # a version made before lines existed cannot be forked
        raise HTTPException(status_code=409, detail={"reason": "no_line"})
    branch = session.scalars(select(TimelineEvent).where(TimelineEvent.line_id == base.id).order_by(TimelineEvent.occurred_on.desc(), TimelineEvent.seq.desc()).limit(1)).first()
    if branch is None:
        branch = TimelineEvent(id=uuid4(), organization_id=base.organization_id, model_id=base.model_id, line_id=base.id, occurred_on=_today_in_organization(session, base.organization_id), title="Initial situation", created_by_user_account_id=created_by)
        session.add(branch)
        session.flush()
    session.add(ModelLine(id=fork.id, organization_id=fork.organization_id, model_id=fork.model_id, name=fork.name, description=fork.description, kind="scenario", parent_line_id=base.id, branch_event_id=branch.id, created_by_user_account_id=created_by, version=1))
    session.flush()


def fork_version(session: Session, base: ModelVersion, name: str, description: str | None, created_by: UUID | None = None) -> ModelVersion:
    """Copy ``base``'s graph into a new version that records where each node came from, with its Scenario line."""
    fork = ModelVersion(id=uuid4(), organization_id=base.organization_id, model_id=base.model_id, name=name, description=description, is_baseline=False, base_version_id=base.id, version=1)
    session.add(fork)
    session.flush()
    _fork_line(session, base, fork, created_by)
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
            fork = fork_version(session, base, body.name, body.description, user.account.id)
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
            if (line := session.get(ModelLine, version.id)) is not None:
                line.name, line.description = body.name, body.description
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
            session.flush()
            if (line := session.get(ModelLine, version.id)) is not None:
                session.delete(line)  # takes its metrics, values, simulations, events and positions with it
            session.delete(version)
        return Response(status_code=204)

    @router.get("/{organization_id}/models/{model_id}/versions/{version_id}/changes", response_model=DiffResponse)
    def changes(organization_id: UUID, model_id: UUID, version_id: UUID, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> DiffResponse:
        with _member_session(session_factory, organization_id, user) as (session, _membership):
            _model(session, organization_id, model_id)
            return diff_of(session, version_of(session, organization_id, model_id, version_id))

    @router.post("/{organization_id}/models/{model_id}/versions/{version_id}/merge", response_model=MergeResponse)
    def merge(organization_id: UUID, model_id: UUID, version_id: UUID, body: MergeRequest, request: Request, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> MergeResponse:
        with _manager_session(session_factory, organization_id, user) as session:
            _model(session, organization_id, model_id)
            version = version_of(session, organization_id, model_id, version_id, lock=True)
            _stale(version.version, body.expected_version)
            if version.base_version_id is None:
                raise HTTPException(status_code=422, detail="the baseline has nothing to merge into")
            session.execute(select(ModelVersion.id).where(ModelVersion.id == version.base_version_id).with_for_update())
            result = merge_version(session, version)
            version.version += 1
            _audit(session, request, "version.merged", "model_version", version.id, {"version": version.name, "into": result.base.name, "added_nodes": result.added_nodes, "removed_nodes": result.removed_nodes, "changed_nodes": result.changed_nodes})
            return result

    return router


__all__ = ["MANAGERS", "baseline_of", "create_version_router", "diff_of", "fork_version"]
