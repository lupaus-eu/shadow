"""Metamodel editing: a Model's node types, connection types, and which node types may connect.

The default metamodel seeds every new Model; from then on the Model owns its types. Every member
can edit the types of a Model (like nodes); a type, or an allowed-connection rule, that an event of any line
still uses cannot be deleted (409 ``in_use``, ADR-0049). A node or connection type is used when any event
change payload names it; a rule is used when the chains would no longer replay without it. The deletes lock
the Model like event writes do, so an event cannot start using a type while it is deleted. Until ticket 08 of
the model timeline drops the old ``nodes`` and ``connections`` tables their rows count too, because their
foreign keys would otherwise stop the delete.
"""

import re
from dataclasses import replace
from typing import Annotated, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import AfterValidator, BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.auth import AuthenticatedUser
from app.auth_routes import AuthenticatedUserDependency
from app.model_routes import (
    AllowedConnectionResponse,
    ConnectionTypeResponse,
    NodeTypeResponse,
    _audit,
    _editor_session,
    _model,
    _stale,
)
from app.models import AllowedConnection, Connection, ConnectionType, EventChange, Node, NodeType, TimelineEvent
from app.timeline.chain import validate_lines
from app.timeline.errors import ChainBroken
from app.timeline.loader import load_timeline

COLOR = r"^#[0-9A-Fa-f]{6}$"
Style = Literal["solid", "dashed"]
End = Literal["none", "arrow"]


def _clean(value: str) -> str:
    if not (value := " ".join(value.split())):
        raise ValueError("must not be blank")
    return value


Name = Annotated[str, Field(min_length=1, max_length=80), AfterValidator(_clean)]


class NodeTypeRequest(BaseModel):
    name: Name
    color: str = Field(pattern=COLOR)
    shape: Literal["rectangle"] = "rectangle"


class NodeTypeUpdate(BaseModel):
    expected_version: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=80)
    color: str | None = Field(default=None, pattern=COLOR)


class ConnectionTypeRequest(BaseModel):
    name: Name
    style: Style = "solid"
    source_end: End = "none"
    target_end: End = "arrow"


class ConnectionTypeUpdate(BaseModel):
    expected_version: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=80)
    style: Style | None = None
    source_end: End | None = None
    target_end: End | None = None


class AllowedRequest(BaseModel):
    connection_type_id: UUID
    source_node_type_id: UUID
    target_node_type_id: UUID


def _key(name: str, taken: set[str]) -> str:
    base = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")[:50] or "type"
    key, number = base, 2
    while key in taken:
        key, number = f"{base}_{number}", number + 1
    return key


def _type(session: Session, cls, organization_id: UUID, model_id: UUID, type_id: UUID, *, lock: bool = False):
    statement = select(cls).where(cls.id == type_id, cls.model_id == model_id, cls.organization_id == organization_id)
    item = session.scalar(statement.with_for_update() if lock else statement)
    if item is None:
        raise HTTPException(status_code=404, detail="Type not found")
    return item


def _named_by_event(session: Session, model_id: UUID, key: str, type_id: UUID) -> bool:
    """Whether any event change of any line of the Model names the type (``node_type_id`` or ``connection_type_id`` in its payload)."""
    statement = select(func.count()).select_from(EventChange).join(TimelineEvent, TimelineEvent.id == EventChange.event_id).where(TimelineEvent.model_id == model_id, EventChange.payload[key].as_string() == str(type_id))
    return bool(session.scalar(statement))


def _rule_needed_by_events(session: Session, model_id: UUID, rule: tuple[UUID, UUID, UUID]) -> bool:
    """Whether some chain of the Model would stop replaying if the rule (connection type, source type, target type) were gone."""
    timeline = load_timeline(session, model_id)
    without = replace(timeline.metamodel, allowed=timeline.metamodel.allowed - {rule})
    try:
        validate_lines(timeline.lines, timeline.events, without)
    except ChainBroken:
        return True
    return False


def create_metamodel_router(*, session_factory: sessionmaker[Session], authenticated_user_dependency: AuthenticatedUserDependency) -> APIRouter:
    router = APIRouter(prefix="/api/v1/organizations", tags=["metamodel"])

    def taken(session: Session, cls, model_id: UUID) -> set[str]:
        return set(session.scalars(select(cls.key).where(cls.model_id == model_id)).all())

    @router.post("/{organization_id}/models/{model_id}/node-types", response_model=NodeTypeResponse, status_code=201)
    def create_node_type(organization_id: UUID, model_id: UUID, body: NodeTypeRequest, request: Request, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> NodeTypeResponse:
        with _editor_session(session_factory, organization_id, user) as session:
            model = _model(session, organization_id, model_id)
            if session.scalar(select(NodeType.id).where(NodeType.model_id == model.id, func.lower(NodeType.name) == body.name.lower())):
                raise HTTPException(status_code=409, detail={"reason": "duplicate_name"})
            item = NodeType(id=uuid4(), organization_id=organization_id, model_id=model.id, key=_key(body.name, taken(session, NodeType, model.id)), name=body.name, color=body.color, shape=body.shape, version=1)
            session.add(item)
            session.flush()
            _audit(session, request, "node_type.created", "node_type", item.id, {"model_id": str(model.id), "name": item.name})
            return NodeTypeResponse.model_validate(item, from_attributes=True)

    @router.patch("/{organization_id}/models/{model_id}/node-types/{type_id}", response_model=NodeTypeResponse)
    def update_node_type(organization_id: UUID, model_id: UUID, type_id: UUID, body: NodeTypeUpdate, request: Request, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> NodeTypeResponse:
        with _editor_session(session_factory, organization_id, user) as session:
            item = _type(session, NodeType, organization_id, model_id, type_id, lock=True)
            _stale(item.version, body.expected_version)
            name = " ".join(body.name.split()) if body.name else None
            if "name" in body.model_fields_set and not name:
                raise HTTPException(status_code=422, detail="name must not be empty")
            if name and name.lower() != item.name.lower() and session.scalar(select(NodeType.id).where(NodeType.model_id == model_id, func.lower(NodeType.name) == name.lower())):
                raise HTTPException(status_code=409, detail={"reason": "duplicate_name"})
            changes = {key: value for key, value in (("name", name), ("color", body.color)) if value is not None and value != getattr(item, key)}
            for key, value in changes.items():
                setattr(item, key, value)
            if changes:
                item.version += 1
                _audit(session, request, "node_type.updated", "node_type", item.id, changes)
            return NodeTypeResponse.model_validate(item, from_attributes=True)

    @router.delete("/{organization_id}/models/{model_id}/node-types/{type_id}", status_code=204)
    def delete_node_type(organization_id: UUID, model_id: UUID, type_id: UUID, expected_version: int, request: Request, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> Response:
        with _editor_session(session_factory, organization_id, user) as session:
            _model(session, organization_id, model_id, lock=True)
            item = _type(session, NodeType, organization_id, model_id, type_id, lock=True)
            _stale(item.version, expected_version)
            if _named_by_event(session, model_id, "node_type_id", item.id) or session.scalar(select(func.count()).select_from(Node).where(Node.node_type_id == item.id)):
                raise HTTPException(status_code=409, detail={"reason": "in_use"})
            _audit(session, request, "node_type.deleted", "node_type", item.id, {"model_id": str(model_id), "name": item.name})
            session.delete(item)
        return Response(status_code=204)

    @router.post("/{organization_id}/models/{model_id}/connection-types", response_model=ConnectionTypeResponse, status_code=201)
    def create_connection_type(organization_id: UUID, model_id: UUID, body: ConnectionTypeRequest, request: Request, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> ConnectionTypeResponse:
        with _editor_session(session_factory, organization_id, user) as session:
            model = _model(session, organization_id, model_id)
            if session.scalar(select(ConnectionType.id).where(ConnectionType.model_id == model.id, func.lower(ConnectionType.name) == body.name.lower())):
                raise HTTPException(status_code=409, detail={"reason": "duplicate_name"})
            item = ConnectionType(id=uuid4(), organization_id=organization_id, model_id=model.id, key=_key(body.name, taken(session, ConnectionType, model.id)), name=body.name, style=body.style, source_end=body.source_end, target_end=body.target_end, version=1)
            session.add(item)
            session.flush()
            _audit(session, request, "connection_type.created", "connection_type", item.id, {"model_id": str(model.id), "name": item.name})
            return ConnectionTypeResponse.model_validate(item, from_attributes=True)

    @router.patch("/{organization_id}/models/{model_id}/connection-types/{type_id}", response_model=ConnectionTypeResponse)
    def update_connection_type(organization_id: UUID, model_id: UUID, type_id: UUID, body: ConnectionTypeUpdate, request: Request, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> ConnectionTypeResponse:
        with _editor_session(session_factory, organization_id, user) as session:
            item = _type(session, ConnectionType, organization_id, model_id, type_id, lock=True)
            _stale(item.version, body.expected_version)
            name = " ".join(body.name.split()) if body.name else None
            if "name" in body.model_fields_set and not name:
                raise HTTPException(status_code=422, detail="name must not be empty")
            if name and name.lower() != item.name.lower() and session.scalar(select(ConnectionType.id).where(ConnectionType.model_id == model_id, func.lower(ConnectionType.name) == name.lower())):
                raise HTTPException(status_code=409, detail={"reason": "duplicate_name"})
            wanted = {"name": name, "style": body.style, "source_end": body.source_end, "target_end": body.target_end}
            changes = {key: value for key, value in wanted.items() if value is not None and value != getattr(item, key)}
            for key, value in changes.items():
                setattr(item, key, value)
            if changes:
                item.version += 1
                _audit(session, request, "connection_type.updated", "connection_type", item.id, changes)
            return ConnectionTypeResponse.model_validate(item, from_attributes=True)

    @router.delete("/{organization_id}/models/{model_id}/connection-types/{type_id}", status_code=204)
    def delete_connection_type(organization_id: UUID, model_id: UUID, type_id: UUID, expected_version: int, request: Request, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> Response:
        with _editor_session(session_factory, organization_id, user) as session:
            _model(session, organization_id, model_id, lock=True)
            item = _type(session, ConnectionType, organization_id, model_id, type_id, lock=True)
            _stale(item.version, expected_version)
            if _named_by_event(session, model_id, "connection_type_id", item.id) or session.scalar(select(func.count()).select_from(Connection).where(Connection.connection_type_id == item.id)):
                raise HTTPException(status_code=409, detail={"reason": "in_use"})
            _audit(session, request, "connection_type.deleted", "connection_type", item.id, {"model_id": str(model_id), "name": item.name})
            session.delete(item)
        return Response(status_code=204)

    @router.post("/{organization_id}/models/{model_id}/allowed-connections", response_model=AllowedConnectionResponse, status_code=201)
    def allow_connection(organization_id: UUID, model_id: UUID, body: AllowedRequest, request: Request, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> AllowedConnectionResponse:
        with _editor_session(session_factory, organization_id, user) as session:
            model = _model(session, organization_id, model_id)
            _type(session, ConnectionType, organization_id, model.id, body.connection_type_id)
            _type(session, NodeType, organization_id, model.id, body.source_node_type_id)
            _type(session, NodeType, organization_id, model.id, body.target_node_type_id)
            if session.scalar(select(AllowedConnection.id).where(AllowedConnection.connection_type_id == body.connection_type_id, AllowedConnection.source_node_type_id == body.source_node_type_id, AllowedConnection.target_node_type_id == body.target_node_type_id)):
                raise HTTPException(status_code=409, detail={"reason": "duplicate_rule"})
            session.add(AllowedConnection(id=uuid4(), organization_id=organization_id, model_id=model.id, **body.model_dump()))
            session.flush()
            _audit(session, request, "allowed_connection.created", "model", model.id, {key: str(value) for key, value in body.model_dump().items()})
            return AllowedConnectionResponse(**body.model_dump())

    @router.delete("/{organization_id}/models/{model_id}/allowed-connections", status_code=204)
    def disallow_connection(organization_id: UUID, model_id: UUID, connection_type_id: UUID, source_node_type_id: UUID, target_node_type_id: UUID, request: Request, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> Response:
        with _editor_session(session_factory, organization_id, user) as session:
            model = _model(session, organization_id, model_id, lock=True)
            rule = session.scalar(select(AllowedConnection).where(AllowedConnection.model_id == model.id, AllowedConnection.connection_type_id == connection_type_id, AllowedConnection.source_node_type_id == source_node_type_id, AllowedConnection.target_node_type_id == target_node_type_id).with_for_update())
            if rule is None:
                raise HTTPException(status_code=404, detail="Rule not found")
            target = Node.__table__.alias("t")
            used = session.scalar(
                select(func.count())
                .select_from(Connection)
                .join(Node, Node.id == Connection.source_node_id)
                .join(target, target.c.id == Connection.target_node_id)
                .where(Connection.connection_type_id == connection_type_id, Node.node_type_id == source_node_type_id, target.c.node_type_id == target_node_type_id)
            )
            if used or _rule_needed_by_events(session, model.id, (connection_type_id, source_node_type_id, target_node_type_id)):
                raise HTTPException(status_code=409, detail={"reason": "in_use"})
            _audit(session, request, "allowed_connection.deleted", "model", model.id, {"connection_type_id": str(connection_type_id)})
            session.delete(rule)
        return Response(status_code=204)

    return router
