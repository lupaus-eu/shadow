"""Writing changes: create, edit (date, content, replace the edits) and delete (model timeline, ADR-0049).

Every write locks the Model row, loads the whole timeline, applies the mutation in memory and replays the
changed line and every Scenario that branches from it (``app.timeline.validate``). If any step would be
invalid nothing is saved and the answer is 422 ``chain_broken`` with structured data for the interface.
Owners and Admins write the Base line; any Member writes Scenarios; a read-only Organization writes nothing.
Audit entries carry ids, the date and edit counts per operation, never names, titles or notes.
"""

from collections import Counter
from dataclasses import replace
from datetime import date
from typing import Any, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from app.auth import AuthenticatedUser, Clock
from app.auth_routes import AuthenticatedUserDependency
from app.limits import CHANGES_PER_LINE, _refuse_at
from app.model_routes import MANAGERS, _audit, _member_session, _model, _stale
from app.models import ChangeEdit, NodePosition, OrganizationMembership, TimelineChange
from app.subscription_access import require_organization_mutation_access
from app.timeline.chain import ChangeRecord
from app.timeline.loader import ModelTimeline, load_timeline, today_in_organization
from app.timeline.payloads import AddNode, dump_payload, parse_payload
from app.timeline.state import Edit
from app.timeline.validate import ChainRefused, Mutation, Validation, next_seq, validate_model
from app.timeline_routes import ChangeResponse, _change_response

EditOp = Literal["add_node", "remove_node", "update_node", "add_connection", "remove_connection", "reroute_connection", "change_connection_type"]
ADDING = ("add_node", "add_connection")


class EditRequest(BaseModel):
    """One edit inside a change. ``element_id`` is the node or connection id; an add may leave it out and the server generates one."""

    op: EditOp
    element_id: UUID | None = None
    payload: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _valid(self) -> "EditRequest":
        try:
            self.payload = dump_payload(self.op, self.payload)
        except ValidationError as error:
            raise ValueError("; ".join(f"{'.'.join(map(str, item['loc']))}: {item['msg']}" for item in error.errors())) from None
        if self.element_id is None:
            if self.op not in ADDING:
                raise ValueError(f"{self.op} needs element_id")
            self.element_id = uuid4()
        return self


def _trimmed(value: str) -> str:
    if not (value := " ".join(value.split())):
        raise ValueError("must not be blank")
    return value


class ChangeRequest(BaseModel):
    occurred_on: date
    title: str = Field(min_length=1, max_length=200)
    note: str | None = Field(default=None, max_length=10000)
    edits: list[EditRequest] = Field(default_factory=list)

    @field_validator("title")
    @classmethod
    def _trim_title(cls, value: str) -> str:
        return _trimmed(value)


class ChangeUpdate(BaseModel):
    """Only the fields sent are applied; ``edits`` replaces the whole list."""

    expected_version: int = Field(ge=1)
    occurred_on: date | None = None
    title: str | None = Field(default=None, min_length=1, max_length=200)
    note: str | None = Field(default=None, max_length=10000)
    edits: list[EditRequest] | None = None

    @model_validator(mode="after")
    def _not_null(self) -> "ChangeUpdate":
        for key in ("occurred_on", "title", "edits"):
            if key in self.model_fields_set and getattr(self, key) is None:
                raise ValueError(f"{key} must not be null")
        if self.title is not None:
            self.title = _trimmed(self.title)
        return self


class EditResponse(BaseModel):
    position: int
    op: str
    element_id: UUID
    payload: dict[str, Any]


class ChangeDetailResponse(ChangeResponse):
    edits: list[EditResponse]


def _counts(edits: list[Edit] | tuple[Edit, ...]) -> dict[str, int]:
    return dict(sorted(Counter(edit.op for edit in edits).items()))


def _records(edits: list[EditRequest]) -> tuple[Edit, ...]:
    return tuple(Edit(item.op, item.element_id, item.payload) for item in edits)  # type: ignore[arg-type]


def _detail(session: Session, organization_id: UUID, model_id: UUID, change_id: UUID, clock: Clock) -> ChangeDetailResponse:
    """The saved change with its edits, read back from the database."""
    session.flush()
    timeline = load_timeline(session, model_id)
    base = _change_response(timeline, change_id, today_in_organization(session, organization_id, clock))
    record = next(item for item in timeline.changes[timeline.change_rows[change_id].line_id] if item.id == change_id)
    edits = [EditResponse(position=position, op=edit.op, element_id=edit.element_id, payload=edit.payload) for position, edit in enumerate(record.edits)]
    return ChangeDetailResponse(**base.model_dump(), edits=edits)


def _line(timeline: ModelTimeline, line_id: UUID):
    row = timeline.line_rows.get(line_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Line not found")
    return row


def _may_write(timeline: ModelTimeline, line_id: UUID, membership: OrganizationMembership) -> None:
    """Owners and Admins write the Base line; any Member writes a Scenario."""
    if _line(timeline, line_id).kind == "base" and membership.role not in MANAGERS:
        raise HTTPException(status_code=403, detail="Owner or Admin required")


def _validate(session: Session, model_id: UUID, timeline: ModelTimeline, mutation: Mutation) -> Validation:
    try:
        return validate_model(session, model_id, mutation, timeline=timeline)
    except ChainRefused as refused:
        raise HTTPException(status_code=422, detail=refused.detail) from refused


def _store_edits(session: Session, organization_id: UUID, model_id: UUID, line_id: UUID, change_id: UUID, edits: tuple[Edit, ...]) -> None:
    """Save the edits numbered 0..n-1 and give each node added here a drawn position on the line unless it has one."""
    positioned = set(session.scalars(select(NodePosition.node_id).where(NodePosition.line_id == line_id)))
    for position, edit in enumerate(edits):
        session.add(ChangeEdit(id=uuid4(), organization_id=organization_id, change_id=change_id, position=position, op=edit.op, element_id=edit.element_id, payload=edit.payload))
        if edit.op == "add_node" and edit.element_id not in positioned:
            added = parse_payload("add_node", edit.payload)
            assert isinstance(added, AddNode)
            session.add(NodePosition(line_id=line_id, node_id=edit.element_id, organization_id=organization_id, model_id=model_id, x=added.x, y=added.y))
            positioned.add(edit.element_id)
    session.flush()


def _forget_positions(session: Session, model_id: UUID, old: tuple[Edit, ...], after: dict[UUID, list[ChangeRecord]]) -> None:
    """Drop the drawn positions of nodes that no change adds any more (the change that added them was deleted or rewritten)."""
    still_added = {edit.element_id for items in after.values() for change in items for edit in change.edits if edit.op == "add_node"}
    gone = {edit.element_id for edit in old if edit.op == "add_node"} - still_added
    if gone:
        session.execute(delete(NodePosition).where(NodePosition.model_id == model_id, NodePosition.node_id.in_(gone)))


def _restart(timeline: ModelTimeline, validation: Validation, clock: Clock) -> None:
    """A Scenario whose starting point moved is marked so its owner can acknowledge it."""
    for line_id in validation.restarted:
        timeline.line_rows[line_id].start_changed_at = clock()


def _summary(model_id: UUID, line_id: UUID, change_id: UUID, day: date, counts: dict[str, int]) -> dict[str, Any]:
    return {"model_id": str(model_id), "line_id": str(line_id), "change_id": str(change_id), "occurred_on": day.isoformat(), "edit_counts": counts}


def create_timeline_change_router(*, session_factory: sessionmaker[Session], authenticated_user_dependency: AuthenticatedUserDependency, clock: Clock) -> APIRouter:
    router = APIRouter(prefix="/api/v1/organizations", tags=["Timeline"])
    base = "/{organization_id}/models/{model_id}"

    @router.get(base + "/changes/{change_id}", response_model=ChangeDetailResponse)
    def read_change(organization_id: UUID, model_id: UUID, change_id: UUID, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> ChangeDetailResponse:
        with _member_session(session_factory, organization_id, user) as (session, _membership):
            _model(session, organization_id, model_id)
            if session.scalar(select(TimelineChange.id).where(TimelineChange.id == change_id, TimelineChange.model_id == model_id)) is None:
                raise HTTPException(status_code=404, detail="Change not found")
            return _detail(session, organization_id, model_id, change_id, clock)

    @router.post(base + "/lines/{line_id}/changes", response_model=ChangeDetailResponse, status_code=201)
    def create_change(organization_id: UUID, model_id: UUID, line_id: UUID, body: ChangeRequest, request: Request, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> ChangeDetailResponse:
        with _member_session(session_factory, organization_id, user) as (session, membership):
            require_organization_mutation_access(session, organization_id)
            _model(session, organization_id, model_id, lock=True)  # one writer per Model while the chain is checked and saved
            timeline = load_timeline(session, model_id)
            _may_write(timeline, line_id, membership)
            _refuse_at(CHANGES_PER_LINE, len(timeline.changes.get(line_id, ())))
            edits = _records(body.edits)
            change_id = uuid4()
            record = ChangeRecord(change_id, line_id, body.occurred_on, next_seq(timeline), body.title, edits)
            validation = _validate(session, model_id, timeline, Mutation(line_id, lambda changes: changes.setdefault(line_id, []).append(record)))
            session.add(TimelineChange(id=change_id, organization_id=organization_id, model_id=model_id, line_id=line_id, occurred_on=body.occurred_on, title=body.title, note=body.note, created_by_user_account_id=user.account.id))
            session.flush()
            _store_edits(session, organization_id, model_id, line_id, change_id, edits)
            _restart(timeline, validation, clock)
            _audit(session, request, "change.created", "change", change_id, _summary(model_id, line_id, change_id, body.occurred_on, _counts(edits)))
            return _detail(session, organization_id, model_id, change_id, clock)

    @router.patch(base + "/changes/{change_id}", response_model=ChangeDetailResponse)
    def update_change(organization_id: UUID, model_id: UUID, change_id: UUID, body: ChangeUpdate, request: Request, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> ChangeDetailResponse:
        with _member_session(session_factory, organization_id, user) as (session, membership):
            require_organization_mutation_access(session, organization_id)
            _model(session, organization_id, model_id, lock=True)
            timeline = load_timeline(session, model_id)
            row = timeline.change_rows.get(change_id)
            if row is None:
                raise HTTPException(status_code=404, detail="Change not found")
            line_id = row.line_id
            _may_write(timeline, line_id, membership)
            _stale(row.version, body.expected_version)
            old = next(item for item in timeline.changes[line_id] if item.id == change_id)
            fields = body.model_fields_set
            new = replace(
                old,
                occurred_on=body.occurred_on if "occurred_on" in fields and body.occurred_on else old.occurred_on,
                title=body.title if "title" in fields and body.title else old.title,
                edits=_records(body.edits) if "edits" in fields and body.edits is not None else old.edits,
            )
            note = body.note if "note" in fields else row.note
            changed = [key for key, differs in (("occurred_on", new.occurred_on != old.occurred_on), ("title", new.title != old.title), ("note", note != row.note), ("edits", new.edits != old.edits)) if differs]
            if not changed:
                return _detail(session, organization_id, model_id, change_id, clock)

            def apply(changes: dict[UUID, list[ChangeRecord]]) -> None:
                changes[line_id] = [new if item.id == change_id else item for item in changes[line_id]]

            validation = _validate(session, model_id, timeline, Mutation(line_id, apply))
            row.occurred_on, row.title, row.note = new.occurred_on, new.title, note
            row.version += 1
            row.updated_at = clock()
            if "edits" in changed:
                session.execute(delete(ChangeEdit).where(ChangeEdit.change_id == change_id))
                session.flush()
                _store_edits(session, organization_id, model_id, line_id, change_id, new.edits)
                _forget_positions(session, model_id, old.edits, validation.changes)
            _restart(timeline, validation, clock)
            summary = _summary(model_id, line_id, change_id, new.occurred_on, _counts(new.edits))
            summary["fields"] = changed
            if "occurred_on" in changed:
                summary["previous_occurred_on"] = old.occurred_on.isoformat()
            if "edits" in changed:
                summary["previous_edit_counts"] = _counts(old.edits)
            _audit(session, request, "change.updated", "change", change_id, summary)
            return _detail(session, organization_id, model_id, change_id, clock)

    @router.delete(base + "/changes/{change_id}", status_code=204)
    def delete_change(organization_id: UUID, model_id: UUID, change_id: UUID, expected_version: int, request: Request, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> Response:
        with _member_session(session_factory, organization_id, user) as (session, membership):
            require_organization_mutation_access(session, organization_id)
            _model(session, organization_id, model_id, lock=True)
            timeline = load_timeline(session, model_id)
            row = timeline.change_rows.get(change_id)
            if row is None:
                raise HTTPException(status_code=404, detail="Change not found")
            line_id = row.line_id
            _may_write(timeline, line_id, membership)
            _stale(row.version, expected_version)
            branching = sorted((line for line in timeline.line_rows.values() if line.branch_change_id == change_id), key=lambda line: (line.created_at, line.id))
            if branching:  # checked before the chain: another line starts from this change (ADR-0049)
                raise HTTPException(status_code=409, detail={"reason": "branch_point", "line": branching[0].name, "line_id": str(branching[0].id), "lines": [{"line_id": str(line.id), "name": line.name} for line in branching]})
            old = next(item for item in timeline.changes[line_id] if item.id == change_id)

            def apply(changes: dict[UUID, list[ChangeRecord]]) -> None:
                changes[line_id] = [item for item in changes[line_id] if item.id != change_id]

            validation = _validate(session, model_id, timeline, Mutation(line_id, apply))
            summary = _summary(model_id, line_id, change_id, old.occurred_on, _counts(old.edits))
            session.delete(row)
            session.flush()
            _forget_positions(session, model_id, old.edits, validation.changes)
            _restart(timeline, validation, clock)
            _audit(session, request, "change.deleted", "change", change_id, summary)
        return Response(status_code=204)

    return router
