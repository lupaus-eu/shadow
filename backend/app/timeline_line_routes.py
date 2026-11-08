"""Scenarios and positions: create, rename, delete, acknowledge a changed start, and draw positions (model timeline, ADR-0048).

Any Member may create a Scenario, from any event of any line of the Model (a Scenario of a Scenario works to any
depth); it starts from the parent's state after that event and gets a copy of the parent's metrics and values. Owners
and Admins manage the Base line; a Scenario's creator, Owners and Admins rename and delete it. Moving nodes is part
of drawing, so it follows the line's write rule (Base line: Owner or Admin; Scenario: any Member) and writes neither
an event nor an audit entry. Audit entries carry ids only, never names.
"""

from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.auth import AuthenticatedUser, Clock
from app.auth_routes import AuthenticatedUserDependency
from app.limits import LINES_PER_MODEL, _refuse_at
from app.metric_routes import copy_metrics
from app.model_routes import MANAGERS, _audit, _member_session, _model, _stale
from app.models import Metric, ModelLine, ModelVersion, Node, NodePosition, OrganizationMembership
from app.subscription_access import require_organization_mutation_access
from app.timeline.chain import state_after
from app.timeline.errors import ChainBroken
from app.timeline.loader import ModelTimeline, load_timeline
from app.timeline_event_routes import _line, _may_write
from app.timeline_routes import LineResponse, PositionResponse, _broken, _line_response


def _trimmed(value: str) -> str:
    if not (value := " ".join(value.split())):
        raise ValueError("must not be blank")
    return value


class ScenarioRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    branch_event_id: UUID

    @field_validator("name")
    @classmethod
    def _trim(cls, value: str) -> str:
        return _trimmed(value)


class LineUpdate(BaseModel):
    """``name`` is required; ``description`` is replaced (null clears it)."""

    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    expected_version: int = Field(ge=1)

    @field_validator("name")
    @classmethod
    def _trim(cls, value: str) -> str:
        return _trimmed(value)


class PositionItem(BaseModel):
    node_id: UUID
    x: float = Field(allow_inf_nan=False)
    y: float = Field(allow_inf_nan=False)


def _duplicate_name(timeline: ModelTimeline, name: str, *, except_line: UUID | None = None) -> None:
    if any(row.name.lower() == name.lower() for row in timeline.line_rows.values() if row.id != except_line):
        raise HTTPException(status_code=409, detail={"reason": "duplicate_name"})


def _may_manage(timeline: ModelTimeline, line_id: UUID, membership: OrganizationMembership) -> None:
    """The Base line belongs to Owners and Admins; a Scenario also to its creator."""
    row = _line(timeline, line_id)
    if membership.role in MANAGERS:
        return
    if row.kind == "base" or row.created_by_user_account_id != membership.user_account_id:
        raise HTTPException(status_code=403, detail="Owner, Admin or the creator of the Scenario required")


def create_timeline_line_router(*, session_factory: sessionmaker[Session], authenticated_user_dependency: AuthenticatedUserDependency, clock: Clock) -> APIRouter:
    router = APIRouter(prefix="/api/v1/organizations", tags=["Timeline"])
    base = "/{organization_id}/models/{model_id}/lines"

    @router.post(base, response_model=LineResponse, status_code=201)
    def create_scenario(organization_id: UUID, model_id: UUID, body: ScenarioRequest, request: Request, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> LineResponse:
        with _member_session(session_factory, organization_id, user) as (session, _membership):
            require_organization_mutation_access(session, organization_id)
            _model(session, organization_id, model_id, lock=True)
            timeline = load_timeline(session, model_id)
            branch = timeline.event_rows.get(body.branch_event_id)
            if branch is None:
                raise HTTPException(status_code=404, detail="Event not found")
            _duplicate_name(timeline, body.name)
            _refuse_at(LINES_PER_MODEL, len(timeline.line_rows))
            try:
                start = state_after(timeline.lines, timeline.events, timeline.metamodel, branch.line_id, branch.id)
            except ChainBroken as error:
                raise _broken(error) from error
            line = ModelLine(id=uuid4(), organization_id=organization_id, model_id=model_id, name=body.name, description=body.description, kind="scenario", parent_line_id=branch.line_id, branch_event_id=branch.id, created_by_user_account_id=user.account.id, version=1)
            session.add(line)
            session.flush()
            # Node ids are the same in every line; a metric keeps its node only if the node exists at the branch point
            # (and, until ticket 08 moves metrics.node_id off the old ``nodes`` table, still has a row there).
            linked = set(session.scalars(select(Metric.node_id).where(Metric.line_id == branch.line_id, Metric.node_id.is_not(None))))
            kept = set(session.scalars(select(Node.id).where(Node.id.in_(linked)))) if linked else set()
            copy_metrics(session, branch.line_id, line.id, {node_id: node_id for node_id in linked & kept if node_id in start.nodes})
            _audit(session, request, "line.created", "line", line.id, {"model_id": str(model_id), "line_id": str(line.id), "parent_line_id": str(branch.line_id), "branch_event_id": str(branch.id)})
            session.refresh(line)
            return _line_response(load_timeline(session, model_id), line.id)

    @router.patch(base + "/{line_id}", response_model=LineResponse)
    def update_line(organization_id: UUID, model_id: UUID, line_id: UUID, body: LineUpdate, request: Request, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> LineResponse:
        with _member_session(session_factory, organization_id, user) as (session, membership):
            require_organization_mutation_access(session, organization_id)
            _model(session, organization_id, model_id, lock=True)
            timeline = load_timeline(session, model_id)
            row = _line(timeline, line_id)
            _may_manage(timeline, line_id, membership)
            _stale(row.version, body.expected_version)
            fields = [key for key, new in (("name", body.name), ("description", body.description)) if getattr(row, key) != new]
            if fields:
                _duplicate_name(timeline, body.name, except_line=line_id)
                row.name, row.description = body.name, body.description
                row.version += 1
                if (version := session.get(ModelVersion, line_id)) is not None:  # the old version routes until ticket 08
                    version.name, version.description = body.name, body.description
                _audit(session, request, "line.renamed", "line", line_id, {"model_id": str(model_id), "line_id": str(line_id), "fields": fields})
            session.flush()
            return _line_response(load_timeline(session, model_id), line_id)

    @router.delete(base + "/{line_id}", status_code=204)
    def delete_line(organization_id: UUID, model_id: UUID, line_id: UUID, request: Request, expected_version: int | None = None, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> Response:
        with _member_session(session_factory, organization_id, user) as (session, membership):
            require_organization_mutation_access(session, organization_id)
            _model(session, organization_id, model_id, lock=True)
            timeline = load_timeline(session, model_id)
            row = _line(timeline, line_id)
            if row.kind == "base":
                raise HTTPException(status_code=422, detail={"reason": "base_line"})
            _may_manage(timeline, line_id, membership)
            if expected_version is not None:
                _stale(row.version, expected_version)
            children = [item for item in timeline.line_rows.values() if item.parent_line_id == line_id]
            if children:
                raise HTTPException(status_code=409, detail={"reason": "has_children", "children": len(children)})
            summary = {"model_id": str(model_id), "line_id": str(line_id), "parent_line_id": str(row.parent_line_id), "event_count": len(timeline.events.get(line_id, ()))}
            _audit(session, request, "line.deleted", "line", line_id, summary)
            session.flush()
            if (version := session.get(ModelVersion, line_id)) is not None:  # the old version routes until ticket 08
                session.delete(version)
            session.delete(row)  # the database takes its events, changes, positions, metrics, values and simulations with it
            session.flush()
        return Response(status_code=204)

    @router.post(base + "/{line_id}/acknowledge-start", response_model=LineResponse)
    def acknowledge_start(organization_id: UUID, model_id: UUID, line_id: UUID, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> LineResponse:
        with _member_session(session_factory, organization_id, user) as (session, membership):
            require_organization_mutation_access(session, organization_id)
            _model(session, organization_id, model_id, lock=True)
            timeline = load_timeline(session, model_id)
            row = _line(timeline, line_id)
            _may_write(timeline, line_id, membership)
            row.start_changed_at = None
            session.flush()
            return _line_response(timeline, line_id)

    @router.put(base + "/{line_id}/positions", response_model=list[PositionResponse])
    def put_positions(organization_id: UUID, model_id: UUID, line_id: UUID, body: Annotated[list[PositionItem], Body(max_length=5000)], user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> list[PositionResponse]:
        with _member_session(session_factory, organization_id, user) as (session, membership):
            require_organization_mutation_access(session, organization_id)
            _model(session, organization_id, model_id)
            timeline = load_timeline(session, model_id)
            _line(timeline, line_id)
            _may_write(timeline, line_id, membership)
            try:
                nodes = state_after(timeline.lines, timeline.events, timeline.metamodel, line_id).nodes
            except ChainBroken as error:
                raise _broken(error) from error
            latest = {item.node_id: item for item in body}  # the last entry for a node wins
            unknown = [node_id for node_id in latest if node_id not in nodes]
            if unknown:
                raise HTTPException(status_code=422, detail={"reason": "unknown_node", "node_ids": [str(node_id) for node_id in unknown]})
            existing = {row.node_id: row for row in session.scalars(select(NodePosition).where(NodePosition.line_id == line_id, NodePosition.node_id.in_(list(latest))))} if latest else {}
            for node_id, item in latest.items():
                if (row := existing.get(node_id)) is not None:
                    row.x, row.y = item.x, item.y
                else:
                    session.add(NodePosition(line_id=line_id, node_id=node_id, organization_id=organization_id, model_id=model_id, x=item.x, y=item.y))
            session.flush()
            return [PositionResponse(node_id=node_id, x=item.x, y=item.y) for node_id, item in latest.items()]

    return router
