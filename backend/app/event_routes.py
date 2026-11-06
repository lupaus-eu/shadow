from calendar import monthrange
from datetime import date, datetime, time, timedelta, timezone
from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, object_session, sessionmaker

from app.limits import EVENTS, require_bulk_size, require_event_capacity
from app.audit import AuditEventDraft, record_audit_event
from app.auth import AuthenticatedUser
from app.auth_routes import AuthenticatedUserDependency
from app.database import RequestContext, apply_request_context, transaction_session
from app.event_content import LOCATION_MAX, DescriptionFormat, LinkItem, check_links, check_times, clean_location, clean_time, links_json, time_text
from app.models import Category, Event, EventSeries, Lane, Organization, OrganizationMembership, OrganizationRole, SeriesOccurrence, Yearclock
from app.event_labels import event_label_ids, resolve_labels, set_event_labels
from app.lifecycle import content_retention, live_yearclock
from app.planning_window import WINDOW_LENGTHS, planning_window
from app.recurrence import materialization_horizon, materialize_series
from app.subscription_access import require_organization_mutation_access
from app.access import role_on
from app.revisions import set_revision_reason
from app.time_zone import organization_today
from app.yearclock_reading import readable_links


class EventRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    lane_id: UUID
    category_id: UUID | None = None
    starts_on: date
    ends_on: date | None = None
    description: str | None = Field(default=None, max_length=10_000)
    # None keeps the current format on update and means plain text on create.
    description_format: DescriptionFormat | None = None
    location: str | None = Field(default=None, max_length=LOCATION_MAX)
    links: list[LinkItem] = []
    starts_at: time | None = None
    ends_at: time | None = None
    expected_version: int | None = Field(default=None, ge=1)
    # None keeps the current Labels on update; a list replaces them.
    label_ids: list[UUID] | None = None
    # Where a new Event came from, for its first Event Revision (Yearclock V2).
    origin: Literal["duplicate", "plan_again"] | None = None

    @field_validator("title")
    @classmethod
    def title_not_blank(cls, value: str) -> str:
        if not (value := value.strip()): raise ValueError("must not be blank")
        return value
    @field_validator("location")
    @classmethod
    def trimmed_location(cls, value: str | None) -> str | None: return clean_location(value)
    @field_validator("links")
    @classmethod
    def valid_links(cls, value: list[LinkItem]) -> list[LinkItem]: return check_links(value)
    @field_validator("starts_at", "ends_at")
    @classmethod
    def whole_minutes(cls, value: time | None) -> time | None: return clean_time(value)
    @model_validator(mode="after")
    def valid_range(self):
        if self.ends_on and self.ends_on < self.starts_on: raise ValueError("end date must not precede start date")
        check_times(self.starts_on, self.ends_on, self.starts_at, self.ends_at)
        return self

class EventResponse(BaseModel):
    id: UUID; lane_id: UUID; category_id: UUID | None; title: str; description: str | None; description_format: str = "plain"; location: str | None = None; links: list[LinkItem] = []; starts_at: str | None = None; ends_at: str | None = None; starts_on: date; ends_on: date | None; version: int
    deleted_at: datetime | None = None
    purge_after: datetime | None = None
    occurrence_id: UUID | None = None
    series_id: UUID | None = None
    series_date: date | None = None
    exception: bool = False
    skipped: bool = False
    label_ids: list[UUID] = []
    # Events shown through a Linked Lane: lane_id is the Linked Lane of this Yearclock.
    linked: bool = False
    source_yearclock_id: UUID | None = None

class BulkItem(BaseModel):
    id: UUID
    expected_version: int = Field(ge=1)

class BulkRequest(BaseModel):
    items: list[BulkItem] = Field(min_length=1)
    action: Literal["move", "categorize", "label", "delete"]
    lane_id: UUID | None = None
    category_id: UUID | None = None
    add_label_ids: list[UUID] = []
    remove_label_ids: list[UUID] = []

    @model_validator(mode="after")
    def complete(self):
        if len({item.id for item in self.items}) != len(self.items): raise ValueError("items must be unique")
        if self.action == "move" and self.lane_id is None: raise ValueError("move needs lane_id")
        if self.action == "label" and not (self.add_label_ids or self.remove_label_ids): raise ValueError("label needs add_label_ids or remove_label_ids")
        return self

class BulkResponse(BaseModel):
    bulk_id: UUID
    changed: int
    items: list[EventResponse]

class PlanAgainRequest(BaseModel):
    season_start: date
    lane_ids: list[UUID] = Field(min_length=1)
    category_ids: list[UUID] = []
    include_uncategorized: bool = True
    date_rule: Literal["same_date", "same_weekday"] = "same_date"
    dry_run: bool = True

    @field_validator("season_start")
    @classmethod
    def first_of_month(cls, value: date) -> date:
        if value.day != 1: raise ValueError("must be the first day of a month")
        return value

class PlanAgainResponse(BaseModel):
    to_create: int
    skipped_existing: int
    limit_exceeded: bool
    maximum: int
    created_ids: list[UUID] = []

def next_year(value: date) -> date:
    """The same date a year later; 29 February becomes 28 February."""
    return value.replace(year=value.year + 1, day=min(value.day, monthrange(value.year + 1, value.month)[1]))

def same_weekday_next_year(value: date) -> date:
    """52 weeks later: always the same weekday nearest to the date a year later."""
    return value + timedelta(days=364)

def create_event_router(*, session_factory: sessionmaker[Session], authenticated_user_dependency: AuthenticatedUserDependency) -> APIRouter:
    router = APIRouter(prefix="/api/v1/organizations", tags=["Events"])
    @router.get("/{organization_id}/yearclocks/{yearclock_id}/events", response_model=list[EventResponse])
    def list_events(organization_id: UUID, yearclock_id: UUID, window_start: date | None = None, include_skipped: bool = False, months: int = Query(default=12), user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> list[EventResponse]:
        return read_events(session_factory, organization_id, yearclock_id, user, window_start, include_skipped, months)
    @router.post("/{organization_id}/yearclocks/{yearclock_id}/events", response_model=EventResponse, status_code=201)
    def create(organization_id: UUID, yearclock_id: UUID, body: EventRequest, request: Request, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> EventResponse:
        return create_event_for(session_factory, organization_id, yearclock_id, body, user, request)
    @router.patch("/{organization_id}/yearclocks/{yearclock_id}/events/{event_id}", response_model=EventResponse)
    def update(organization_id: UUID, yearclock_id: UUID, event_id: UUID, body: EventRequest, request: Request, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> EventResponse:
        return update_event_for(session_factory, organization_id, yearclock_id, event_id, body, user, request)
    @router.post("/{organization_id}/yearclocks/{yearclock_id}/events/bulk", response_model=BulkResponse)
    def bulk(organization_id: UUID, yearclock_id: UUID, body: BulkRequest, request: Request, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> BulkResponse:
        """One all-or-nothing change to many single Events (V2 P3 Bulk Edit)."""
        with _access_session(session_factory, organization_id, yearclock_id, user, mutate=True) as session:
            require_bulk_size(len(body.items))
            ids = [item.id for item in body.items]
            events = {event.id: event for event in session.scalars(select(Event).where(Event.id.in_(ids), Event.yearclock_id == yearclock_id).order_by(Event.id).with_for_update()).all()}
            if len(events) != len(ids): raise HTTPException(status_code=422, detail={"reason": "not_in_yearclock", "ids": [str(item) for item in ids if item not in events]})
            recurring = session.scalars(select(SeriesOccurrence.event_id).where(SeriesOccurrence.event_id.in_(ids))).all()
            if recurring: raise HTTPException(status_code=422, detail={"reason": "recurring_occurrence", "ids": [str(item) for item in recurring]})
            stale = [str(item.id) for item in body.items if events[item.id].version != item.expected_version or events[item.id].deleted_at is not None]
            if stale: raise HTTPException(status_code=409, detail={"reason": "stale", "ids": stale})
            if body.action == "move": _lane(session, organization_id, yearclock_id, body.lane_id)
            if body.action == "categorize": _category(session, yearclock_id, body.category_id)
            resolve_labels(session, organization_id, body.add_label_ids); resolve_labels(session, organization_id, body.remove_label_ids)
            current_labels = event_label_ids(session, ids)
            bulk_id, changed, now = uuid4(), 0, datetime.now(timezone.utc)
            set_revision_reason(session, "bulk", {"bulk_id": str(bulk_id)})
            for item in body.items:
                event = events[item.id]
                if body.action == "delete":
                    event.deleted_at = now; event.version += 1; changed += 1
                    _audit(session, request, "event.deleted", event.id, {"title": event.title, "bulk_id": str(bulk_id)}); continue
                summary: dict = {}
                if body.action == "move" and event.lane_id != body.lane_id: event.lane_id = body.lane_id; summary["lane_id"] = str(body.lane_id)
                if body.action == "categorize" and event.category_id != body.category_id: event.category_id = body.category_id; summary["category_id"] = str(body.category_id) if body.category_id else None
                if body.action == "label":
                    before = current_labels.get(event.id, [])
                    wanted = [label for label in before if label not in body.remove_label_ids] + [label for label in body.add_label_ids if label not in before and label not in body.remove_label_ids]
                    if set(wanted) != set(before): summary.update({key: value for key, value in set_event_labels(session, event, resolve_labels(session, organization_id, wanted)).items() if value})
                if not summary: continue
                event.version += 1; changed += 1
                _audit(session, request, "event.updated", event.id, {"title": event.title, **summary, "bulk_id": str(bulk_id)})
            session.flush()
            labels = event_label_ids(session, ids)
            return BulkResponse(bulk_id=bulk_id, changed=changed, items=[_response(events[item], None, labels.get(item, [])) for item in ids])
    @router.post("/{organization_id}/yearclocks/{yearclock_id}/plan-again", response_model=PlanAgainResponse)
    def plan_again(organization_id: UUID, yearclock_id: UUID, body: PlanAgainRequest, request: Request, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> PlanAgainResponse:
        """Copy a season's single Events one year ahead (V2 P3 Plan Again); a dry run only counts."""
        with _access_session(session_factory, organization_id, yearclock_id, user, mutate=True) as session:
            for lane_id in body.lane_ids: _lane(session, organization_id, yearclock_id, lane_id)
            month_end = body.season_start.month + 11
            season_end = date(body.season_start.year + (month_end - 1) // 12, (month_end - 1) % 12 + 1, 1)
            season_end = season_end.replace(day=monthrange(season_end.year, season_end.month)[1])
            categories = or_(Event.category_id.in_(body.category_ids), Event.category_id.is_(None)) if body.include_uncategorized else Event.category_id.in_(body.category_ids)
            recurring = select(SeriesOccurrence.event_id).where(SeriesOccurrence.event_id.is_not(None))
            sources = session.scalars(select(Event).where(Event.yearclock_id == yearclock_id, Event.deleted_at.is_(None), Event.lane_id.in_(body.lane_ids), categories, Event.starts_on >= body.season_start, Event.starts_on <= season_end, Event.id.not_in(recurring)).order_by(Event.starts_on, Event.id)).all()
            shift = same_weekday_next_year if body.date_rule == "same_weekday" else next_year
            existing = {(title, lane_id, starts_on) for title, lane_id, starts_on in session.execute(select(Event.title, Event.lane_id, Event.starts_on).where(Event.yearclock_id == yearclock_id, Event.deleted_at.is_(None))).all()}
            planned, skipped = [], 0
            for source in sources:
                key = (source.title, source.lane_id, shift(source.starts_on))
                if key in existing: skipped += 1; continue
                existing.add(key); planned.append(source)
            if planned and not body.dry_run: require_event_capacity(session, yearclock_id)
            count = session.scalar(select(func.count()).select_from(Event).where(Event.yearclock_id == yearclock_id, Event.deleted_at.is_(None))) or 0
            exceeded = count + len(planned) > EVENTS.maximum
            if body.dry_run or not planned or exceeded:
                if exceeded and not body.dry_run: raise HTTPException(status_code=409, detail={"reason": "limit_reached", "limit": EVENTS.name, "maximum": EVENTS.maximum})
                return PlanAgainResponse(to_create=len(planned), skipped_existing=skipped, limit_exceeded=exceeded, maximum=EVENTS.maximum)
            source_labels = event_label_ids(session, [source.id for source in planned])
            plan_id, created = uuid4(), []
            set_revision_reason(session, "plan_again", {"plan_id": str(plan_id)})
            for source in planned:
                ends_on = shift(source.ends_on) if source.ends_on else None
                event = Event(id=uuid4(), organization_id=organization_id, yearclock_id=yearclock_id, lane_id=source.lane_id, category_id=source.category_id, title=source.title, description=source.description, description_format=source.description_format, location=source.location, links=list(source.links or []), starts_at=source.starts_at, ends_at=source.ends_at, starts_on=shift(source.starts_on), ends_on=ends_on, version=1)
                session.add(event)
                labels = resolve_labels(session, organization_id, source_labels.get(source.id, []))
                set_event_labels(session, event, labels)
                _audit(session, request, "event.created", event.id, {"title": event.title, "labels": [label.name for label in labels], "plan_id": str(plan_id)})
                created.append(event.id)
            record_audit_event(session, AuditEventDraft(action="yearclock.planned_again", target_type="yearclock", target_id=yearclock_id, request_id=(request.headers.get("X-Request-ID") or str(uuid4()))[:120], change_summary={"plan_id": str(plan_id), "season_start": body.season_start.isoformat(), "date_rule": body.date_rule, "created": len(created), "skipped_existing": skipped}))
            return PlanAgainResponse(to_create=len(created), skipped_existing=skipped, limit_exceeded=False, maximum=EVENTS.maximum, created_ids=created)
    @router.delete("/{organization_id}/yearclocks/{yearclock_id}/events/{event_id}", status_code=204)
    def delete(organization_id: UUID, yearclock_id: UUID, event_id: UUID, request: Request, expected_version: int = Query(ge=1), user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> None:
        delete_event_for(session_factory, organization_id, yearclock_id, event_id, expected_version, user, request)
    @router.get("/{organization_id}/yearclocks/{yearclock_id}/deleted-events", response_model=list[EventResponse])
    def deleted_events(organization_id: UUID, yearclock_id: UUID, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> list[EventResponse]:
        with _access_session(session_factory, organization_id, yearclock_id, user, mutate=False) as session: return [_response(item) for item in session.scalars(select(Event).where(Event.yearclock_id == yearclock_id, Event.deleted_at.is_not(None))).all()]
    @router.post("/{organization_id}/yearclocks/{yearclock_id}/events/{event_id}/restore", response_model=EventResponse)
    def restore(organization_id: UUID, yearclock_id: UUID, event_id: UUID, request: Request, expected_version: int = Query(ge=1), user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> EventResponse:
        with _access_session(session_factory, organization_id, yearclock_id, user, mutate=True) as session:
            event = _event(session, yearclock_id, event_id)
            if expected_version != event.version: raise HTTPException(status_code=409, detail={"latest_version": event.version})
            if event.deleted_at is None: raise HTTPException(status_code=409, detail="Event is not deleted")
            event.deleted_at = None; event.version += 1; _audit(session, request, "event.restored", event.id, {"title": event.title}); return _response(event)
    return router

def read_events(session_factory: sessionmaker[Session], organization_id: UUID, yearclock_id: UUID, user: AuthenticatedUser, window_start: date | None, include_skipped: bool, months: int) -> list[EventResponse]:
    with _access_session(session_factory, organization_id, yearclock_id, user, mutate=False) as session:
        organization = session.get(Organization, organization_id)
        if organization is None:
            raise HTTPException(status_code=404, detail="Organization not found")
        today = organization_today(organization.time_zone)
        if months not in WINDOW_LENGTHS:
            raise HTTPException(status_code=422, detail=f"months must be one of {list(WINDOW_LENGTHS)}")
        start, end = planning_window(window_start, today=today, months=months)
        through = max(end, materialization_horizon(organization.time_zone))
        links = readable_links(session, organization_id, yearclock_id, user.account.id)
        for series in session.scalars(select(EventSeries).where(or_(EventSeries.yearclock_id == yearclock_id, EventSeries.lane_id.in_(links.keys())))).all():
            materialize_series(session, series, through=through)
        session.flush()
        in_window = (Event.deleted_at.is_(None), Event.starts_on <= end, func.coalesce(Event.ends_on, Event.starts_on) >= start)
        events = session.scalars(select(Event).where(Event.yearclock_id == yearclock_id, *in_window).order_by(Event.starts_on, Event.id)).all()
        linked = session.scalars(select(Event).where(Event.lane_id.in_(links.keys()), *in_window).order_by(Event.starts_on, Event.id)).all() if links else []
        occurrences = {item.event_id: item for item in session.scalars(select(SeriesOccurrence).where(SeriesOccurrence.event_id.in_([event.id for event in [*events, *linked]]))).all()}
        labels = event_label_ids(session, [event.id for event in [*events, *linked]])
        shown = lambda event, own: own and include_skipped or not (occurrences.get(event.id) and occurrences[event.id].skipped)
        responses = [_response(event, occurrences.get(event.id), labels.get(event.id, [])) for event in events if shown(event, True)]
        responses += [_response(event, occurrences.get(event.id), labels.get(event.id, [])).model_copy(update={"lane_id": links[event.lane_id][0], "linked": True, "source_yearclock_id": links[event.lane_id][1]}) for event in linked if shown(event, False)]
        return sorted(responses, key=lambda item: (item.starts_on, item.starts_at is not None, item.starts_at or "", str(item.id)))
def create_event_for(session_factory: sessionmaker[Session], organization_id: UUID, yearclock_id: UUID, body: EventRequest, user: AuthenticatedUser, request: Request | None) -> EventResponse:
    with _access_session(session_factory, organization_id, yearclock_id, user, mutate=True) as session:
        _lane(session, organization_id, yearclock_id, body.lane_id)
        _category(session, yearclock_id, body.category_id)
        labels = resolve_labels(session, organization_id, body.label_ids or [])
        require_event_capacity(session, yearclock_id)
        if body.origin: set_revision_reason(session, body.origin)
        event = Event(id=uuid4(), organization_id=organization_id, yearclock_id=yearclock_id, lane_id=body.lane_id, category_id=body.category_id, title=body.title, description=body.description, description_format=body.description_format or "plain", location=body.location, links=links_json(body.links), starts_at=body.starts_at, ends_at=body.ends_at, starts_on=body.starts_on, ends_on=body.ends_on, version=1)
        session.add(event); set_event_labels(session, event, labels)
        _audit(session, request, "event.created", event.id, {"title": event.title, "labels": [label.name for label in labels]}); return _response(event)
def update_event_for(session_factory: sessionmaker[Session], organization_id: UUID, yearclock_id: UUID, event_id: UUID, body: EventRequest, user: AuthenticatedUser, request: Request | None) -> EventResponse:
    with _access_session(session_factory, organization_id, yearclock_id, user, mutate=True) as session:
        event = _event(session, yearclock_id, event_id)
        if body.expected_version != event.version: raise HTTPException(status_code=409, detail={"latest_version": event.version})
        _lane(session, organization_id, yearclock_id, body.lane_id); _category(session, yearclock_id, body.category_id)
        label_changes = set_event_labels(session, event, resolve_labels(session, organization_id, body.label_ids)) if body.label_ids is not None else {}
        for name in ("lane_id", "category_id", "title", "description", "location", "starts_at", "ends_at", "starts_on", "ends_on"): setattr(event, name, getattr(body, name))
        event.links = links_json(body.links)
        if body.description_format: event.description_format = body.description_format
        summary = {"title": event.title, **{key: value for key, value in label_changes.items() if value}}
        event.version += 1; _audit(session, request, "event.updated", event.id, summary); return _response(event)
def delete_event_for(session_factory: sessionmaker[Session], organization_id: UUID, yearclock_id: UUID, event_id: UUID, expected_version: int, user: AuthenticatedUser, request: Request | None) -> None:
    with _access_session(session_factory, organization_id, yearclock_id, user, mutate=True) as session:
        event = _event(session, yearclock_id, event_id)
        if expected_version != event.version: raise HTTPException(status_code=409, detail={"latest_version": event.version})
        if session.scalar(select(SeriesOccurrence.id).where(SeriesOccurrence.event_id == event.id)) is not None:
            raise HTTPException(status_code=409, detail={"reason": "recurring_occurrence", "message": "skip the Occurrence or end its Series instead"})
        _audit(session, request, "event.deleted", event.id, {"title": event.title}); event.deleted_at = datetime.now(timezone.utc); event.version += 1
def read_event_for(session_factory: sessionmaker[Session], organization_id: UUID, yearclock_id: UUID, event_id: UUID, user: AuthenticatedUser) -> EventResponse:
    with _access_session(session_factory, organization_id, yearclock_id, user, mutate=False) as session:
        event = session.scalar(select(Event).where(Event.id == event_id, Event.yearclock_id == yearclock_id))
        if event is None: raise HTTPException(status_code=404, detail="Event not found")
        occurrence = session.scalar(select(SeriesOccurrence).where(SeriesOccurrence.event_id == event.id))
        return _response(event, occurrence)
from contextlib import contextmanager
@contextmanager
def _access_session(factory: sessionmaker[Session], organization_id: UUID, yearclock_id: UUID, user: AuthenticatedUser, *, mutate: bool):
    with transaction_session(factory, RequestContext(user_account_id=user.account.id)) as session:
        membership = session.scalar(select(OrganizationMembership).where(OrganizationMembership.organization_id == organization_id, OrganizationMembership.user_account_id == user.account.id))
        if membership is None: raise HTTPException(status_code=404, detail="Yearclock not found")
        apply_request_context(session, RequestContext(user_account_id=user.account.id, organization_id=organization_id))
        if mutate:
            require_organization_mutation_access(session, organization_id)
        live_yearclock(session, organization_id, yearclock_id)
        role = role_on(session, membership, yearclock_id)
        if role is None: raise HTTPException(status_code=403, detail="Yearclock access required")
        if mutate and role != "editor": raise HTTPException(status_code=403, detail="Editor access required")
        yield session
def _lane(session: Session, organization_id: UUID, yearclock_id: UUID, lane_id: UUID) -> None:
    lane = session.scalar(select(Lane).where(Lane.id == lane_id, Lane.organization_id == organization_id, Lane.yearclock_id == yearclock_id))
    if lane is None: raise HTTPException(status_code=422, detail="Lane does not belong to Yearclock")
    if lane.source_lane_id is not None: raise HTTPException(status_code=422, detail={"reason": "linked_lane", "message": "Events of a Linked Lane are changed in its source Yearclock"})
def _event(session: Session, yearclock_id: UUID, event_id: UUID) -> Event:
    item = session.scalar(select(Event).where(Event.id == event_id, Event.yearclock_id == yearclock_id).with_for_update())
    if item is None: raise HTTPException(status_code=404, detail="Event not found")
    return item
def _category(session: Session, yearclock_id: UUID, category_id: UUID | None) -> None:
    # RLS keeps the lookup inside the current Organization, so a NULL Yearclock means one of its Organization Categories.
    if category_id is not None and session.scalar(select(Category).where(Category.id == category_id, or_(Category.yearclock_id == yearclock_id, Category.yearclock_id.is_(None)))) is None: raise HTTPException(status_code=422, detail="Category does not belong to Yearclock")
def _response(event: Event, occurrence: SeriesOccurrence | None = None, label_ids: list[UUID] | None = None) -> EventResponse:
    if label_ids is None:
        session = object_session(event)
        label_ids = event_label_ids(session, [event.id]).get(event.id, []) if session is not None else []
    return EventResponse(
        id=event.id, lane_id=event.lane_id, category_id=event.category_id, title=event.title,
        description=event.description, description_format=event.description_format, location=event.location, links=[LinkItem(**item) for item in (event.links or [])], starts_at=time_text(event.starts_at), ends_at=time_text(event.ends_at), starts_on=event.starts_on,
        ends_on=event.ends_on, version=event.version,
        deleted_at=event.deleted_at, purge_after=event.deleted_at + content_retention() if event.deleted_at else None,
        occurrence_id=occurrence.id if occurrence else None,
        series_id=occurrence.series_id if occurrence else None,
        series_date=occurrence.series_date if occurrence else None,
        exception=bool(occurrence and occurrence.overrides),
        skipped=occurrence.skipped if occurrence else False,
        label_ids=label_ids,
    )
def _audit(session: Session, request: Request | None, action: str, target_id: UUID, summary: dict) -> None: record_audit_event(session, AuditEventDraft(action=action, target_type="event", target_id=target_id, request_id=((request.headers.get("X-Request-ID") if request is not None else None) or str(uuid4()))[:120], change_summary=summary))
