from datetime import date, time
from urllib.parse import urlparse
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session, sessionmaker

from app.audit import AuditEventDraft, record_audit_event
from app.auth import AuthenticatedUser
from app.auth_routes import AuthenticatedUserDependency
from app.event_routes import EventResponse, _access_session, _category, _lane, _response
from app.models import Event, EventSeries, SeriesOccurrence
from app.event_labels import resolve_labels
from app.event_content import LOCATION_MAX, DescriptionFormat, LinkItem, check_links, check_times, clean_location, clean_time, links_json
from app.series_editing import OVERRIDE_FIELDS, effective_values, override_occurrence, restore_series_values
from app.revisions import set_revision_reason


class OccurrenceEdit(BaseModel):
    """Fields present in the request become explicit overrides; absent fields keep inheriting."""

    expected_version: int = Field(ge=1)
    title: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=10_000)
    description_format: DescriptionFormat | None = None
    location: str | None = Field(default=None, max_length=LOCATION_MAX)
    links: list[LinkItem] | None = None
    starts_at: time | None = None
    ends_at: time | None = None
    lane_id: UUID | None = None
    category_id: UUID | None = None
    starts_on: date | None = None
    label_ids: list[UUID] | None = None

    @field_validator("title")
    @classmethod
    def title_not_blank(cls, value: str | None) -> str | None:
        if value is not None and not (value := value.strip()):
            raise ValueError("must not be blank")
        return value

    @field_validator("starts_at", "ends_at")
    @classmethod
    def whole_minutes(cls, value: time | None) -> time | None:
        return clean_time(value)

    @field_validator("location")
    @classmethod
    def trimmed_location(cls, value: str | None) -> str | None:
        return clean_location(value)

    @field_validator("links")
    @classmethod
    def valid_links(cls, value: list[LinkItem] | None) -> list[LinkItem] | None:
        return check_links(value)


def create_occurrence_router(*, session_factory: sessionmaker, authenticated_user_dependency: AuthenticatedUserDependency) -> APIRouter:
    router = APIRouter(prefix="/api/v1/organizations", tags=["Series occurrences"])

    @router.patch("/{organization_id}/yearclocks/{yearclock_id}/occurrences/{occurrence_id}", response_model=EventResponse)
    def edit(organization_id: UUID, yearclock_id: UUID, occurrence_id: UUID, body: OccurrenceEdit, request: Request, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> EventResponse:
        with _access_session(session_factory, organization_id, yearclock_id, user, mutate=True) as session:
            occurrence, event, series = _occurrence(session, yearclock_id, occurrence_id)
            _require_version(event, body.expected_version)
            changes = {field: getattr(body, field) for field in body.model_fields_set if field in OVERRIDE_FIELDS}
            if "label_ids" in changes:
                changes["label_ids"] = [label.id for label in resolve_labels(session, organization_id, changes["label_ids"] or [])]
            if "links" in changes:
                changes["links"] = links_json(changes["links"])
            if changes.get("description_format") is None:
                changes.pop("description_format", None)
            if "starts_at" in changes or "ends_at" in changes:
                effective = effective_values(series, occurrence)
                try:
                    check_times(occurrence.series_date, None, changes["starts_at"] if "starts_at" in changes else effective["starts_at"], changes["ends_at"] if "ends_at" in changes else effective["ends_at"])
                except ValueError as error:
                    raise HTTPException(status_code=422, detail=str(error)) from error
            if "title" in changes and changes["title"] is None:
                raise HTTPException(status_code=422, detail="title must not be removed")
            if changes.get("starts_on") is None: changes.pop("starts_on", None)
            if changes.get("lane_id") is None: changes.pop("lane_id", None)
            if "lane_id" in changes: _lane(session, organization_id, yearclock_id, changes["lane_id"])
            if "category_id" in changes: _category(session, yearclock_id, changes["category_id"])
            set_revision_reason(session, "occurrence_edit")
            override_occurrence(event, series, occurrence, changes)
            _audit(session, request, "occurrence.updated", occurrence.id, {"series_date": occurrence.series_date.isoformat(), "fields": sorted(changes)})
            return _response(event, occurrence)

    @router.post("/{organization_id}/yearclocks/{yearclock_id}/occurrences/{occurrence_id}/skip", response_model=EventResponse)
    def skip(organization_id: UUID, yearclock_id: UUID, occurrence_id: UUID, request: Request, skipped: bool = True, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> EventResponse:
        with _access_session(session_factory, organization_id, yearclock_id, user, mutate=True) as session:
            occurrence, event, _series = _occurrence(session, yearclock_id, occurrence_id)
            set_revision_reason(session, "occurrence_skip" if skipped else "occurrence_unskip")
            if occurrence.skipped != skipped:
                occurrence.skipped = skipped
                event.version += 1
            _audit(session, request, "occurrence.skipped" if skipped else "occurrence.unskipped", occurrence.id, {"series_date": occurrence.series_date.isoformat()})
            return _response(event, occurrence)

    @router.post("/{organization_id}/yearclocks/{yearclock_id}/occurrences/{occurrence_id}/restore", response_model=EventResponse)
    def restore(organization_id: UUID, yearclock_id: UUID, occurrence_id: UUID, request: Request, expected_version: int | None = Query(default=None, ge=1), user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> EventResponse:
        with _access_session(session_factory, organization_id, yearclock_id, user, mutate=True) as session:
            occurrence, event, series = _occurrence(session, yearclock_id, occurrence_id)
            if expected_version is not None:
                _require_version(event, expected_version)
            set_revision_reason(session, "occurrence_restore")
            restore_series_values(event, series, occurrence)
            _audit(session, request, "occurrence.restored", occurrence.id, {"series_date": occurrence.series_date.isoformat()})
            return _response(event, occurrence)

    return router


def _occurrence(session: Session, yearclock_id: UUID, occurrence_id: UUID) -> tuple[SeriesOccurrence, Event, EventSeries]:
    occurrence = session.get(SeriesOccurrence, occurrence_id, with_for_update=True)
    event = session.get(Event, occurrence.event_id, with_for_update=True) if occurrence else None
    if occurrence is None or event is None or event.yearclock_id != yearclock_id:
        raise HTTPException(status_code=404, detail="Occurrence not found")
    series = session.get(EventSeries, occurrence.series_id)
    if series is None:
        raise HTTPException(status_code=404, detail="Occurrence not found")
    return occurrence, event, series


def _require_version(event: Event, expected: int) -> None:
    if event.version != expected:
        raise HTTPException(status_code=409, detail={"latest_version": event.version})


def _audit(session: Session, request: Request, action: str, target_id: UUID, summary: dict) -> None:
    record_audit_event(session, AuditEventDraft(action=action, target_type="series_occurrence", target_id=target_id, request_id=(request.headers.get("X-Request-ID") or str(uuid4()))[:120], change_summary=summary))
