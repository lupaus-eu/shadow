from datetime import date, time
from urllib.parse import urlparse
from uuid import UUID, uuid4
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import select
from sqlalchemy.orm import object_session, sessionmaker
from app.limits import require_series_capacity
from app.revisions import set_revision_reason
from app.auth import AuthenticatedUser
from app.auth_routes import AuthenticatedUserDependency
from app.event_labels import resolve_labels, series_label_ids, set_series_labels
from app.audit import AuditEventDraft, record_audit_event
from app.database import RequestContext, apply_request_context, transaction_session
from app.event_routes import _access_session, _category, _lane
from app.event_content import LOCATION_MAX, DescriptionFormat, LinkItem, check_links, check_times, clean_location, clean_time, links_json, time_text
from app.models import EventSeries, Organization, SeriesOccurrence
from app.series_editing import SERIES_FIELDS, end_series, split_series
from app.recurrence import materialization_horizon, materialize_series, to_rrule

class SeriesRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    lane_id: UUID
    category_id: UUID | None = None
    description: str | None = Field(default=None, max_length=10_000)
    description_format: DescriptionFormat = "plain"
    location: str | None = Field(default=None, max_length=LOCATION_MAX)
    links: list[LinkItem] = []
    starts_at: time | None = None
    ends_at: time | None = None
    starts_on: date
    frequency: str
    interval: int = Field(default=1, ge=1)
    until: date | None = None
    occurrence_count: int | None = Field(default=None, ge=1)
    last_day: bool = False
    label_ids: list[UUID] = []
    @field_validator("frequency")
    @classmethod
    def valid_frequency(cls, value: str) -> str:
        value = value.upper()
        if value not in {"WEEKLY", "MONTHLY", "YEARLY"}: raise ValueError("frequency must be WEEKLY, MONTHLY, or YEARLY")
        return value
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
    def supported_rule(self):
        check_times(self.starts_on, None, self.starts_at, self.ends_at)
        if self.until is not None and self.occurrence_count is not None: raise ValueError("choose an end date or an occurrence count, not both")
        if self.until is not None and self.until < self.starts_on: raise ValueError("end date must not precede the start date")
        if self.last_day and self.frequency != "MONTHLY": raise ValueError("last day of month applies only to monthly Series")
        return self

class SeriesResponse(BaseModel):
    id: UUID; title: str; description: str | None; description_format: str = "plain"; location: str | None = None; links: list[LinkItem] = []; starts_at: str | None = None; ends_at: str | None = None; lane_id: UUID; category_id: UUID | None
    frequency: str; interval: int; starts_on: date; effective_from: date; until: date | None; occurrence_count: int | None; last_day: bool; rrule: str; version: int
    label_ids: list[UUID] = []


class SeriesChanges(BaseModel):
    """Series-level values for "This and future"; absent fields keep the current values."""

    from_occurrence_id: UUID
    expected_version: int = Field(ge=1)
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=10_000)
    description_format: DescriptionFormat | None = None
    location: str | None = Field(default=None, max_length=LOCATION_MAX)
    links: list[LinkItem] | None = None
    starts_at: time | None = None
    ends_at: time | None = None
    lane_id: UUID | None = None
    category_id: UUID | None = None
    label_ids: list[UUID] | None = None

    @field_validator("starts_at", "ends_at")
    @classmethod
    def whole_minutes(cls, value: time | None) -> time | None:
        return clean_time(value)

    @field_validator("title")
    @classmethod
    def title_not_blank(cls, value: str | None) -> str | None:
        if value is not None and not (value := value.strip()): raise ValueError("must not be blank")
        return value

    @field_validator("location")
    @classmethod
    def trimmed_location(cls, value: str | None) -> str | None: return clean_location(value)

    @field_validator("links")
    @classmethod
    def valid_links(cls, value: list[LinkItem] | None) -> list[LinkItem] | None: return check_links(value)


class SeriesEnd(BaseModel):
    from_occurrence_id: UUID
    expected_version: int = Field(ge=1)


class SeriesEndResponse(BaseModel):
    series: SeriesResponse
    removed_occurrences: int

def create_series_router(*, session_factory: sessionmaker, authenticated_user_dependency: AuthenticatedUserDependency) -> APIRouter:
    router = APIRouter(prefix="/api/v1/organizations", tags=["Event Series"])
    @router.post("/{organization_id}/yearclocks/{yearclock_id}/series", response_model=SeriesResponse, status_code=201)
    def create(organization_id: UUID, yearclock_id: UUID, body: SeriesRequest, request: Request, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> SeriesResponse:
        with _access_session(session_factory, organization_id, yearclock_id, user, mutate=True) as session:
            _lane(session, organization_id, yearclock_id, body.lane_id)
            _category(session, yearclock_id, body.category_id)
            labels = resolve_labels(session, organization_id, body.label_ids)
            require_series_capacity(session, yearclock_id)
            series = EventSeries(id=uuid4(), organization_id=organization_id, yearclock_id=yearclock_id, lane_id=body.lane_id, category_id=body.category_id, title=body.title, description=body.description, description_format=body.description_format, location=body.location, links=links_json(body.links), starts_at=body.starts_at, ends_at=body.ends_at, starts_on=body.starts_on, effective_from=body.starts_on, frequency=body.frequency, interval=body.interval, until=body.until, occurrence_count=body.occurrence_count, last_day=body.last_day, version=1)
            session.add(series); session.flush()
            set_series_labels(session, series, [label.id for label in labels])
            organization = session.get(Organization, organization_id)
            if organization is None:
                raise HTTPException(status_code=404, detail="Organization not found")
            materialize_series(session, series, through=materialization_horizon(organization.time_zone), reason="series_created")
            record_audit_event(session, AuditEventDraft(action="series.created", target_type="event_series", target_id=series.id, request_id=(request.headers.get("X-Request-ID") or str(uuid4()))[:120], change_summary={"frequency": series.frequency, "starts_on": series.starts_on.isoformat()}))
            return _series_response(series)

    @router.get("/{organization_id}/yearclocks/{yearclock_id}/series/{series_id}", response_model=SeriesResponse)
    def detail(organization_id: UUID, yearclock_id: UUID, series_id: UUID, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> SeriesResponse:
        with _access_session(session_factory, organization_id, yearclock_id, user, mutate=False) as session:
            return _series_response(_series(session, yearclock_id, series_id))

    @router.post("/{organization_id}/yearclocks/{yearclock_id}/series/{series_id}/split", response_model=SeriesResponse)
    def split(organization_id: UUID, yearclock_id: UUID, series_id: UUID, body: SeriesChanges, request: Request, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> SeriesResponse:
        with _access_session(session_factory, organization_id, yearclock_id, user, mutate=True) as session:
            series = _series(session, yearclock_id, series_id, lock=True)
            occurrence = _owned_occurrence(session, series, body.from_occurrence_id)
            if body.expected_version != series.version: raise HTTPException(status_code=409, detail={"latest_version": series.version})
            changes = {field: getattr(body, field) for field in body.model_fields_set if field in SERIES_FIELDS}
            if "title" in changes and changes["title"] is None: raise HTTPException(status_code=422, detail="title must not be removed")
            if "links" in changes: changes["links"] = links_json(changes["links"])
            if changes.get("description_format") is None: changes.pop("description_format", None)
            try: check_times(series.starts_on, None, changes["starts_at"] if "starts_at" in changes else series.starts_at, changes["ends_at"] if "ends_at" in changes else series.ends_at)
            except ValueError as error: raise HTTPException(status_code=422, detail=str(error)) from error
            if changes.get("lane_id") is None: changes.pop("lane_id", None)
            if "lane_id" in changes: _lane(session, organization_id, yearclock_id, changes["lane_id"])
            if "category_id" in changes: _category(session, yearclock_id, changes["category_id"])
            if "label_ids" in body.model_fields_set and body.label_ids is not None:
                changes["label_ids"] = [label.id for label in resolve_labels(session, organization_id, body.label_ids)]
            set_revision_reason(session, "series_changed", {"title": changes.get("title", series.title)})
            successor = split_series(session, series, occurrence.series_date, changes)
            record_audit_event(session, AuditEventDraft(action="series.split" if successor.id != series.id else "series.updated", target_type="event_series", target_id=successor.id, request_id=_request_id(request), change_summary={"from_series_id": str(series.id), "from_series_date": occurrence.series_date.isoformat(), "fields": sorted(changes)}))
            return _series_response(successor)

    @router.post("/{organization_id}/yearclocks/{yearclock_id}/series/{series_id}/end", response_model=SeriesEndResponse)
    def end(organization_id: UUID, yearclock_id: UUID, series_id: UUID, body: SeriesEnd, request: Request, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> SeriesEndResponse:
        with _access_session(session_factory, organization_id, yearclock_id, user, mutate=True) as session:
            series = _series(session, yearclock_id, series_id, lock=True)
            occurrence = _owned_occurrence(session, series, body.from_occurrence_id)
            if body.expected_version != series.version: raise HTTPException(status_code=409, detail={"latest_version": series.version})
            at = occurrence.series_date
            removed = end_series(session, series, at)
            record_audit_event(session, AuditEventDraft(action="series.ended", target_type="event_series", target_id=series.id, request_id=_request_id(request), change_summary={"ended_before": at.isoformat(), "removed_occurrences": removed}))
            return SeriesEndResponse(series=_series_response(series), removed_occurrences=removed)
    return router


def _series(session, yearclock_id: UUID, series_id: UUID, *, lock: bool = False) -> EventSeries:
    series = session.get(EventSeries, series_id, with_for_update=lock)
    if series is None or series.yearclock_id != yearclock_id: raise HTTPException(status_code=404, detail="Series not found")
    return series


def _owned_occurrence(session, series: EventSeries, occurrence_id: UUID) -> SeriesOccurrence:
    occurrence = session.get(SeriesOccurrence, occurrence_id)
    if occurrence is None or occurrence.series_id != series.id: raise HTTPException(status_code=422, detail="the Occurrence does not belong to this Series")
    return occurrence


def _request_id(request: Request) -> str:
    return (request.headers.get("X-Request-ID") or str(uuid4()))[:120]


def _series_response(series: EventSeries) -> SeriesResponse:
    session = object_session(series)
    return SeriesResponse(
        label_ids=series_label_ids(session, series.id) if session is not None else [],
        id=series.id, title=series.title, description=series.description, description_format=series.description_format, location=series.location, links=[LinkItem(**item) for item in (series.links or [])], starts_at=time_text(series.starts_at), ends_at=time_text(series.ends_at), lane_id=series.lane_id, category_id=series.category_id,
        frequency=series.frequency, interval=series.interval, starts_on=series.starts_on, effective_from=series.effective_from,
        until=series.until, occurrence_count=series.occurrence_count, last_day=series.last_day, version=series.version,
        rrule=to_rrule(starts_on=series.starts_on, frequency=series.frequency, interval=series.interval, until=series.until, count=series.occurrence_count, last_day=series.last_day),
    )
