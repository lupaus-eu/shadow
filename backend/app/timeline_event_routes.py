"""Writing events: create, change (date, content, replace the changes) and delete (model timeline, ADR-0049).

Every write locks the Model row, loads the whole timeline, applies the mutation in memory and replays the
changed line and every Scenario that branches from it (``app.timeline.validate``). If any step would be
invalid nothing is saved and the answer is 422 ``chain_broken`` with structured data for the interface.
Owners and Admins write the Base line; any Member writes Scenarios; a read-only Organization writes nothing.
Audit entries carry ids, the date and change counts per operation, never names, titles or notes.
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
from app.limits import EVENTS_PER_LINE, _refuse_at
from app.model_routes import MANAGERS, _audit, _member_session, _model, _stale
from app.models import EventChange, NodePosition, OrganizationMembership, TimelineEvent
from app.subscription_access import require_organization_mutation_access
from app.timeline.chain import EventRecord
from app.timeline.loader import ModelTimeline, load_timeline, today_in_organization
from app.timeline.payloads import AddNode, dump_payload, parse_payload
from app.timeline.state import Change
from app.timeline.validate import ChainRefused, Mutation, Validation, next_seq, validate_model
from app.timeline_routes import EventResponse, _event_response

ChangeOp = Literal["add_node", "remove_node", "update_node", "add_connection", "remove_connection", "reroute_connection", "change_connection_type"]
ADDING = ("add_node", "add_connection")


class ChangeRequest(BaseModel):
    """One change inside an event. ``element_id`` is the node or connection id; an add may leave it out and the server generates one."""

    op: ChangeOp
    element_id: UUID | None = None
    payload: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _valid(self) -> "ChangeRequest":
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


class EventRequest(BaseModel):
    occurred_on: date
    title: str = Field(min_length=1, max_length=200)
    note: str | None = Field(default=None, max_length=10000)
    changes: list[ChangeRequest] = Field(default_factory=list)

    @field_validator("title")
    @classmethod
    def _trim_title(cls, value: str) -> str:
        return _trimmed(value)


class EventUpdate(BaseModel):
    """Only the fields sent change; ``changes`` replaces the whole list."""

    expected_version: int = Field(ge=1)
    occurred_on: date | None = None
    title: str | None = Field(default=None, min_length=1, max_length=200)
    note: str | None = Field(default=None, max_length=10000)
    changes: list[ChangeRequest] | None = None

    @model_validator(mode="after")
    def _not_null(self) -> "EventUpdate":
        for key in ("occurred_on", "title", "changes"):
            if key in self.model_fields_set and getattr(self, key) is None:
                raise ValueError(f"{key} must not be null")
        if self.title is not None:
            self.title = _trimmed(self.title)
        return self


class ChangeResponse(BaseModel):
    position: int
    op: str
    element_id: UUID
    payload: dict[str, Any]


class EventDetailResponse(EventResponse):
    changes: list[ChangeResponse]


def _counts(changes: list[Change] | tuple[Change, ...]) -> dict[str, int]:
    return dict(sorted(Counter(change.op for change in changes).items()))


def _records(changes: list[ChangeRequest]) -> tuple[Change, ...]:
    return tuple(Change(item.op, item.element_id, item.payload) for item in changes)  # type: ignore[arg-type]


def _detail(session: Session, organization_id: UUID, model_id: UUID, event_id: UUID, clock: Clock) -> EventDetailResponse:
    """The saved event with its changes, read back from the database."""
    session.flush()
    timeline = load_timeline(session, model_id)
    base = _event_response(timeline, event_id, today_in_organization(session, organization_id, clock))
    record = next(item for item in timeline.events[timeline.event_rows[event_id].line_id] if item.id == event_id)
    changes = [ChangeResponse(position=position, op=change.op, element_id=change.element_id, payload=change.payload) for position, change in enumerate(record.changes)]
    return EventDetailResponse(**base.model_dump(), changes=changes)


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


def _store_changes(session: Session, organization_id: UUID, model_id: UUID, line_id: UUID, event_id: UUID, changes: tuple[Change, ...]) -> None:
    """Save the changes numbered 0..n-1 and give each node added here a drawn position on the line unless it has one."""
    positioned = set(session.scalars(select(NodePosition.node_id).where(NodePosition.line_id == line_id)))
    for position, change in enumerate(changes):
        session.add(EventChange(id=uuid4(), organization_id=organization_id, event_id=event_id, position=position, op=change.op, element_id=change.element_id, payload=change.payload))
        if change.op == "add_node" and change.element_id not in positioned:
            added = parse_payload("add_node", change.payload)
            assert isinstance(added, AddNode)
            session.add(NodePosition(line_id=line_id, node_id=change.element_id, organization_id=organization_id, model_id=model_id, x=added.x, y=added.y))
            positioned.add(change.element_id)
    session.flush()


def _forget_positions(session: Session, model_id: UUID, old: tuple[Change, ...], after: dict[UUID, list[EventRecord]]) -> None:
    """Drop the drawn positions of nodes that no event adds any more (the event that added them was deleted or rewritten)."""
    still_added = {change.element_id for items in after.values() for event in items for change in event.changes if change.op == "add_node"}
    gone = {change.element_id for change in old if change.op == "add_node"} - still_added
    if gone:
        session.execute(delete(NodePosition).where(NodePosition.model_id == model_id, NodePosition.node_id.in_(gone)))


def _restart(timeline: ModelTimeline, validation: Validation, clock: Clock) -> None:
    """A Scenario whose starting point moved is marked so its owner can acknowledge it."""
    for line_id in validation.restarted:
        timeline.line_rows[line_id].start_changed_at = clock()


def _summary(model_id: UUID, line_id: UUID, event_id: UUID, day: date, counts: dict[str, int]) -> dict[str, Any]:
    return {"model_id": str(model_id), "line_id": str(line_id), "event_id": str(event_id), "occurred_on": day.isoformat(), "change_counts": counts}


def create_timeline_event_router(*, session_factory: sessionmaker[Session], authenticated_user_dependency: AuthenticatedUserDependency, clock: Clock) -> APIRouter:
    router = APIRouter(prefix="/api/v1/organizations", tags=["Timeline"])
    base = "/{organization_id}/models/{model_id}"

    @router.get(base + "/events/{event_id}", response_model=EventDetailResponse)
    def read_event(organization_id: UUID, model_id: UUID, event_id: UUID, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> EventDetailResponse:
        with _member_session(session_factory, organization_id, user) as (session, _membership):
            _model(session, organization_id, model_id)
            if session.scalar(select(TimelineEvent.id).where(TimelineEvent.id == event_id, TimelineEvent.model_id == model_id)) is None:
                raise HTTPException(status_code=404, detail="Event not found")
            return _detail(session, organization_id, model_id, event_id, clock)

    @router.post(base + "/lines/{line_id}/events", response_model=EventDetailResponse, status_code=201)
    def create_event(organization_id: UUID, model_id: UUID, line_id: UUID, body: EventRequest, request: Request, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> EventDetailResponse:
        with _member_session(session_factory, organization_id, user) as (session, membership):
            require_organization_mutation_access(session, organization_id)
            _model(session, organization_id, model_id, lock=True)  # one writer per Model while the chain is checked and saved
            timeline = load_timeline(session, model_id)
            _may_write(timeline, line_id, membership)
            _refuse_at(EVENTS_PER_LINE, len(timeline.events.get(line_id, ())))
            changes = _records(body.changes)
            event_id = uuid4()
            record = EventRecord(event_id, line_id, body.occurred_on, next_seq(timeline), body.title, changes)
            validation = _validate(session, model_id, timeline, Mutation(line_id, lambda events: events.setdefault(line_id, []).append(record)))
            session.add(TimelineEvent(id=event_id, organization_id=organization_id, model_id=model_id, line_id=line_id, occurred_on=body.occurred_on, title=body.title, note=body.note, created_by_user_account_id=user.account.id))
            session.flush()
            _store_changes(session, organization_id, model_id, line_id, event_id, changes)
            _restart(timeline, validation, clock)
            _audit(session, request, "event.created", "event", event_id, _summary(model_id, line_id, event_id, body.occurred_on, _counts(changes)))
            return _detail(session, organization_id, model_id, event_id, clock)

    @router.patch(base + "/events/{event_id}", response_model=EventDetailResponse)
    def update_event(organization_id: UUID, model_id: UUID, event_id: UUID, body: EventUpdate, request: Request, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> EventDetailResponse:
        with _member_session(session_factory, organization_id, user) as (session, membership):
            require_organization_mutation_access(session, organization_id)
            _model(session, organization_id, model_id, lock=True)
            timeline = load_timeline(session, model_id)
            row = timeline.event_rows.get(event_id)
            if row is None:
                raise HTTPException(status_code=404, detail="Event not found")
            line_id = row.line_id
            _may_write(timeline, line_id, membership)
            _stale(row.version, body.expected_version)
            old = next(item for item in timeline.events[line_id] if item.id == event_id)
            fields = body.model_fields_set
            new = replace(
                old,
                occurred_on=body.occurred_on if "occurred_on" in fields and body.occurred_on else old.occurred_on,
                title=body.title if "title" in fields and body.title else old.title,
                changes=_records(body.changes) if "changes" in fields and body.changes is not None else old.changes,
            )
            note = body.note if "note" in fields else row.note
            changed = [key for key, differs in (("occurred_on", new.occurred_on != old.occurred_on), ("title", new.title != old.title), ("note", note != row.note), ("changes", new.changes != old.changes)) if differs]
            if not changed:
                return _detail(session, organization_id, model_id, event_id, clock)

            def apply(events: dict[UUID, list[EventRecord]]) -> None:
                events[line_id] = [new if item.id == event_id else item for item in events[line_id]]

            validation = _validate(session, model_id, timeline, Mutation(line_id, apply))
            row.occurred_on, row.title, row.note = new.occurred_on, new.title, note
            row.version += 1
            row.updated_at = clock()
            if "changes" in changed:
                session.execute(delete(EventChange).where(EventChange.event_id == event_id))
                session.flush()
                _store_changes(session, organization_id, model_id, line_id, event_id, new.changes)
                _forget_positions(session, model_id, old.changes, validation.events)
            _restart(timeline, validation, clock)
            summary = _summary(model_id, line_id, event_id, new.occurred_on, _counts(new.changes))
            summary["fields"] = changed
            if "occurred_on" in changed:
                summary["previous_occurred_on"] = old.occurred_on.isoformat()
            if "changes" in changed:
                summary["previous_change_counts"] = _counts(old.changes)
            _audit(session, request, "event.updated", "event", event_id, summary)
            return _detail(session, organization_id, model_id, event_id, clock)

    @router.delete(base + "/events/{event_id}", status_code=204)
    def delete_event(organization_id: UUID, model_id: UUID, event_id: UUID, expected_version: int, request: Request, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> Response:
        with _member_session(session_factory, organization_id, user) as (session, membership):
            require_organization_mutation_access(session, organization_id)
            _model(session, organization_id, model_id, lock=True)
            timeline = load_timeline(session, model_id)
            row = timeline.event_rows.get(event_id)
            if row is None:
                raise HTTPException(status_code=404, detail="Event not found")
            line_id = row.line_id
            _may_write(timeline, line_id, membership)
            _stale(row.version, expected_version)
            branching = sorted((line for line in timeline.line_rows.values() if line.branch_event_id == event_id), key=lambda line: (line.created_at, line.id))
            if branching:  # checked before the chain: another line starts from this event (ADR-0049)
                raise HTTPException(status_code=409, detail={"reason": "branch_point", "line": branching[0].name, "line_id": str(branching[0].id), "lines": [{"line_id": str(line.id), "name": line.name} for line in branching]})
            old = next(item for item in timeline.events[line_id] if item.id == event_id)

            def apply(events: dict[UUID, list[EventRecord]]) -> None:
                events[line_id] = [item for item in events[line_id] if item.id != event_id]

            validation = _validate(session, model_id, timeline, Mutation(line_id, apply))
            summary = _summary(model_id, line_id, event_id, old.occurred_on, _counts(old.changes))
            session.delete(row)
            session.flush()
            _forget_positions(session, model_id, old.changes, validation.events)
            _restart(timeline, validation, clock)
            _audit(session, request, "event.deleted", "event", event_id, summary)
        return Response(status_code=204)

    return router
