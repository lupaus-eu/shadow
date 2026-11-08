"""Scenarios and positions: create, rename, delete, adopt, acknowledge a changed start, and draw positions (model timeline, ADR-0048, ADR-0050).

Any Member may create a Scenario, from any change of any line of the Model (a Scenario of a Scenario works to any
depth); it starts from the parent's state after that change and gets a copy of the parent's metrics and values. Owners
and Admins manage the Base line; a Scenario's creator, Owners and Admins rename and delete it. Moving nodes is part
of drawing, so it follows the line's write rule (Base line: Owner or Admin; Scenario: any Member) and writes neither
a change nor an audit entry. Audit entries carry ids only, never names.

Adopting appends a Scenario's own changes to its parent line when the parent has not moved on (ADR-0050); the answer
to a refusal is structured data (``parent_moved_on``, ``dates_precede``) that the interface words.
"""

from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.auth import AuthenticatedUser, Clock
from app.auth_routes import AuthenticatedUserDependency
from app.limits import CHANGES_PER_LINE, LINES_PER_MODEL, _refuse_at
from app.metric_routes import copy_metrics
from app.model_routes import MANAGERS, _audit, _member_session, _model, _stale
from app.models import Metric, ModelLine, NodePosition, OrganizationMembership, TimelineChange
from app.subscription_access import require_organization_mutation_access
from app.timeline.chain import ChangeRecord, LineRecord, descendants, state_after, validate_lines
from app.timeline.errors import ChainBroken
from app.timeline.loader import ModelTimeline, load_timeline, today_in_organization
from app.timeline.validate import Validation, describe_break, load_type_names, next_seq
from app.timeline_change_routes import _counts, _line, _may_write, _store_edits
from app.timeline_routes import ChangeResponse, LineResponse, PositionResponse, _broken, _line_response, _change_response


def _trimmed(value: str) -> str:
    if not (value := " ".join(value.split())):
        raise ValueError("must not be blank")
    return value


class ScenarioRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    branch_change_id: UUID

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


class AdoptRequest(BaseModel):
    """``expected_version`` is the Scenario's version as the person saw it; leave it out to skip the stale check."""

    expected_version: int | None = Field(default=None, ge=1)


class AdoptResponse(BaseModel):
    line: LineResponse  # the parent line after the adoption
    scenario: LineResponse | None  # the Scenario when it was kept (it has child Scenarios), now without changes
    adopted_changes: list[ChangeResponse]  # the new changes in the parent, in order
    moved_scenarios: int  # child Scenarios now branching from the parent's new changes


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
            branch = timeline.change_rows.get(body.branch_change_id)
            if branch is None:
                raise HTTPException(status_code=404, detail="Change not found")
            _duplicate_name(timeline, body.name)
            _refuse_at(LINES_PER_MODEL, len(timeline.line_rows))
            try:
                start = state_after(timeline.lines, timeline.changes, timeline.metamodel, branch.line_id, branch.id)
            except ChainBroken as error:
                raise _broken(error) from error
            line = ModelLine(id=uuid4(), organization_id=organization_id, model_id=model_id, name=body.name, description=body.description, kind="scenario", parent_line_id=branch.line_id, branch_change_id=branch.id, created_by_user_account_id=user.account.id, version=1)
            session.add(line)
            session.flush()
            # Node ids are the same in every line; a metric keeps its node only if the node exists at the branch point.
            linked = set(session.scalars(select(Metric.node_id).where(Metric.line_id == branch.line_id, Metric.node_id.is_not(None))))
            copy_metrics(session, branch.line_id, line.id, {node_id: node_id for node_id in linked if node_id in start.nodes})
            _audit(session, request, "line.created", "line", line.id, {"model_id": str(model_id), "line_id": str(line.id), "parent_line_id": str(branch.line_id), "branch_change_id": str(branch.id)})
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
            summary = {"model_id": str(model_id), "line_id": str(line_id), "parent_line_id": str(row.parent_line_id), "change_count": len(timeline.changes.get(line_id, ()))}
            _audit(session, request, "line.deleted", "line", line_id, summary)
            session.flush()
            session.delete(row)  # the database takes its changes, edits, positions, metrics, values and simulations with it
            session.flush()
        return Response(status_code=204)

    @router.post(base + "/{line_id}/adopt", response_model=AdoptResponse)
    def adopt_scenario(organization_id: UUID, model_id: UUID, line_id: UUID, request: Request, body: AdoptRequest | None = None, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> AdoptResponse:
        """Append the Scenario's own changes to its parent line (a fast-forward); see ADR-0050."""
        body = body or AdoptRequest()
        with _member_session(session_factory, organization_id, user) as (session, membership):
            require_organization_mutation_access(session, organization_id)
            _model(session, organization_id, model_id, lock=True)  # one writer per Model while the chain is checked and saved
            timeline = load_timeline(session, model_id)
            scenario = _line(timeline, line_id)
            if scenario.kind == "base" or scenario.parent_line_id is None:
                raise HTTPException(status_code=422, detail={"reason": "base_line"})
            parent_id = scenario.parent_line_id
            parent = _line(timeline, parent_id)
            _may_write(timeline, parent_id, membership)  # the Base line: Owner or Admin; a Scenario: any Member
            if body.expected_version is not None:
                _stale(scenario.version, body.expected_version)
            own = timeline.changes_of(line_id)
            if not own:
                raise HTTPException(status_code=422, detail={"reason": "nothing_to_adopt"})
            parent_changes = timeline.changes_of(parent_id)
            branch_index = next((index for index, change in enumerate(parent_changes) if change.id == scenario.branch_change_id), None)
            if branch_index is None:  # the branch point must exist; a refusal the chain check words
                raise HTTPException(status_code=422, detail={"reason": "chain_broken", "cause": "missing_branch_change", "line": str(line_id), "change": str(scenario.branch_change_id), "position": None, "element": None, "hint": {"code": "restore_branch_change"}})
            later = parent_changes[branch_index + 1 :]
            if later:
                last = parent_changes[-1]
                raise HTTPException(
                    status_code=409,
                    detail={
                        "reason": "parent_moved_on",
                        "parent_line_id": str(parent_id),
                        "parent_name": parent.name,
                        "parent_kind": parent.kind,
                        "changes_after": len(later),
                        "changes": [{"id": str(change.id), "title": change.title, "occurred_on": change.occurred_on.isoformat()} for change in later[:20]],
                        "suggestion": {"action": "create_scenario", "parent_line_id": str(parent_id), "branch_change_id": str(last.id), "branch_change_title": last.title, "branch_change_date": last.occurred_on.isoformat()},
                    },
                )
            last = parent_changes[-1]
            early = [change for change in own if change.occurred_on < last.occurred_on]
            if early:
                raise HTTPException(
                    status_code=422,
                    detail={
                        "reason": "dates_precede",
                        "parent_line_id": str(parent_id),
                        "parent_name": parent.name,
                        "parent_last_change_id": str(last.id),
                        "parent_last_change_title": last.title,
                        "parent_last_change_date": last.occurred_on.isoformat(),
                        "changes": [{"id": str(change.id), "title": change.title, "occurred_on": change.occurred_on.isoformat()} for change in early[:20]],
                        "suggestion": {"action": "move_changes_after", "date": last.occurred_on.isoformat()},
                    },
                )
            _refuse_at(CHANGES_PER_LINE, len(parent_changes) + len(own) - 1)
            # The adopted changes are new changes in the parent (new ids, entry order after everything else), same dates.
            first_seq = next_seq(timeline)
            copies = {change.id: ChangeRecord(uuid4(), parent_id, change.occurred_on, first_seq + index, change.title, change.edits) for index, change in enumerate(own)}
            children = [item for item in timeline.line_rows.values() if item.parent_line_id == line_id]
            keep = bool(children)
            lines_after = dict(timeline.lines)
            last_copy = copies[own[-1].id]
            if keep:
                lines_after[line_id] = LineRecord(line_id, parent_id, last_copy.id)
            else:
                lines_after.pop(line_id)
            for child in children:
                lines_after[child.id] = LineRecord(child.id, parent_id, copies[child.branch_change_id].id if child.branch_change_id in copies else child.branch_change_id)
            changes_after = {key: list(items) for key, items in timeline.changes.items()}
            changes_after[parent_id] = [*parent_changes, *copies.values()]
            if keep:
                changes_after[line_id] = []
            else:
                changes_after.pop(line_id, None)
            try:
                validate_lines(lines_after, changes_after, timeline.metamodel, [parent_id, *descendants(lines_after, parent_id)])
            except ChainBroken as error:
                raise HTTPException(status_code=422, detail=describe_break(error, Validation(timeline, changes_after), parent_id, load_type_names(session, model_id))) from error
            # Save. Positions drawn on the Scenario for nodes it added go to the parent line first, so the new changes keep them.
            added_nodes = {edit.element_id for change in own for edit in change.edits if edit.op == "add_node"}
            drawn = list(session.scalars(select(NodePosition).where(NodePosition.line_id == line_id, NodePosition.node_id.in_(added_nodes)))) if added_nodes else []
            for position in drawn:
                session.add(NodePosition(line_id=parent_id, node_id=position.node_id, organization_id=organization_id, model_id=model_id, x=position.x, y=position.y))
            session.flush()
            for change in own:
                copy, source = copies[change.id], timeline.change_rows[change.id]
                session.add(TimelineChange(id=copy.id, organization_id=organization_id, model_id=model_id, line_id=parent_id, occurred_on=copy.occurred_on, title=copy.title, note=source.note, created_by_user_account_id=source.created_by_user_account_id))
                session.flush()  # in order: the entry number grows with each insert
                _store_edits(session, organization_id, model_id, parent_id, copy.id, copy.edits)
            for child in children:  # a child's branch change was one of the Scenario's; it now is the copy in the parent
                child.parent_line_id = parent_id
                if child.branch_change_id in copies:
                    child.branch_change_id = copies[child.branch_change_id].id
            session.flush()
            counts = _counts([edit for change in own for edit in change.edits])
            summary = {"model_id": str(model_id), "line_id": str(line_id), "parent_line_id": str(parent_id), "change_count": len(own), "edit_counts": counts, "scenario_kept": keep, "moved_scenarios": len(children)}
            _audit(session, request, "line.adopted", "line", line_id, summary)
            if keep:
                scenario.branch_change_id = last_copy.id
                scenario.version += 1
                scenario.start_changed_at = None
                session.flush()
                for change in own:
                    session.delete(timeline.change_rows[change.id])
                for position in session.scalars(select(NodePosition).where(NodePosition.line_id == line_id, NodePosition.node_id.in_(added_nodes))) if added_nodes else []:
                    session.delete(position)  # the parent holds them now; the Scenario falls back to the parent's
            else:
                session.delete(scenario)  # the database takes its changes, edits, positions, metrics, values and simulations with it
            session.flush()
            session.expire_all()
            fresh = load_timeline(session, model_id)
            today = today_in_organization(session, organization_id, clock)
            return AdoptResponse(
                line=_line_response(fresh, parent_id),
                scenario=_line_response(fresh, line_id) if keep else None,
                adopted_changes=[_change_response(fresh, copies[change.id].id, today) for change in own],
                moved_scenarios=len(children),
            )

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
                nodes = state_after(timeline.lines, timeline.changes, timeline.metamodel, line_id).nodes
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
