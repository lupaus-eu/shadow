"""Export a Yearclock's Events to Excel, CSV, or calendar file (Yearclock V2 P7, P8, ADR-0030).

Anyone who may read the Yearclock can export it, and the file holds only what
they may see (Linked Lanes follow the access rule of their source). Every
export is recorded in the Audit Log without content and counted against an
hourly limit.
"""
from datetime import date, time
from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, sessionmaker

from app.audit import AuditEventDraft, record_audit_event
from app.auth import AuthenticatedUser
from app.auth_routes import AuthenticatedUserDependency
from app.event_labels import event_label_ids
from app.event_routes import _access_session
from app.rich_text import plain_text
from app.exchange import EXPORT_ACTIONS, ExportRow, build_csv, build_ics, build_xlsx, file_name, require_exchange_quota, series_text
from app.limits import EXPORTS_PER_HOUR
from app.models import Category, Event, EventSeries, Label, Lane, Organization, SeriesOccurrence, Yearclock
from app.planning_window import WINDOW_LENGTHS, planning_window
from app.recurrence import materialization_horizon, materialize_series
from app.time_zone import organization_today
from app.yearclock_reading import readable_links


class ExportFilters(BaseModel):
    """The Filters of the planner: nothing chosen means everything; categories may hold ``"none"``."""
    lanes: list[UUID] = []
    categories: list[str] = []
    labels: list[UUID] = []


class ExportRequest(BaseModel):
    format: Literal["xlsx", "csv", "ics"]
    scope: Literal["window", "all"] = "window"
    window_start: date | None = None
    length: int = Field(default=12)
    filters: ExportFilters = ExportFilters()
    locale: Literal["en", "fi"] = "en"


def create_export_router(*, session_factory: sessionmaker[Session], authenticated_user_dependency: AuthenticatedUserDependency) -> APIRouter:
    router = APIRouter(prefix="/api/v1/organizations", tags=["Export"])

    @router.post("/{organization_id}/yearclocks/{yearclock_id}/export")
    def export_events(organization_id: UUID, yearclock_id: UUID, body: ExportRequest, request: Request, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> Response:
        if body.scope == "window" and body.length not in WINDOW_LENGTHS:
            raise HTTPException(status_code=422, detail=f"length must be one of {list(WINDOW_LENGTHS)}")
        with _access_session(session_factory, organization_id, yearclock_id, user, mutate=False) as session:
            require_exchange_quota(session, user.account.id, organization_id, EXPORT_ACTIONS, EXPORTS_PER_HOUR)
            organization = session.get(Organization, organization_id)
            yearclock = session.get(Yearclock, yearclock_id)
            rows = _rows(session, organization, yearclock_id, user, body)
            if body.format == "ics":
                exported = build_ics(rows, yearclock.name, session.scalar(select(func.now())), organization.time_zone)
            else:
                exported = (build_xlsx if body.format == "xlsx" else build_csv)(rows, body.locale)
            record_audit_event(session, AuditEventDraft(action="yearclock.export", target_type="yearclock", target_id=yearclock_id, request_id=(request.headers.get("X-Request-ID") or str(uuid4()))[:120], change_summary={"format": body.format, "scope": body.scope, "rows": exported.rows, "locale": body.locale}))
            suffix = "all" if body.scope == "all" else f"{_window_start(organization, body).isoformat()}-{body.length}m"
            name = file_name(yearclock.name, suffix, exported.extension)
        return Response(content=exported.content, media_type=exported.media_type, headers={"Content-Disposition": f'attachment; filename="{name}"', "Cache-Control": "no-store"})

    return router


def _window_start(organization: Organization, body: ExportRequest) -> date:
    return planning_window(body.window_start, today=organization_today(organization.time_zone), months=body.length)[0]


def _keep(body: ExportRequest, lane_id: UUID, category_id: UUID | None, label_ids: list[UUID]) -> bool:
    filters = body.filters
    if filters.lanes and lane_id not in filters.lanes:
        return False
    if filters.categories and not ((category_id is None and "none" in filters.categories) or (category_id is not None and str(category_id) in filters.categories)):
        return False
    return not filters.labels or any(label in filters.labels for label in label_ids)


def _rows(session: Session, organization: Organization, yearclock_id: UUID, user: AuthenticatedUser, body: ExportRequest) -> list[ExportRow]:
    links = readable_links(session, organization.id, yearclock_id, user.account.id)
    horizon = materialization_horizon(organization.time_zone)
    if body.scope == "window":
        start, end = planning_window(body.window_start, today=organization_today(organization.time_zone), months=body.length)
        through = max(end, horizon)
        bounds = (Event.starts_on <= end, func.coalesce(Event.ends_on, Event.starts_on) >= start)
    else:
        through, bounds = horizon, ()
    for series in session.scalars(select(EventSeries).where(or_(EventSeries.yearclock_id == yearclock_id, EventSeries.lane_id.in_(links.keys())))).all():
        materialize_series(session, series, through=through)
    session.flush()
    live = (Event.deleted_at.is_(None), *bounds)
    own = session.scalars(select(Event).where(Event.yearclock_id == yearclock_id, *live).order_by(Event.starts_on, Event.id)).all()
    linked = session.scalars(select(Event).where(Event.lane_id.in_(links.keys()), *live).order_by(Event.starts_on, Event.id)).all() if links else []
    events = [*own, *linked]
    ids = [event.id for event in events]
    occurrences = {item.event_id: item for item in session.scalars(select(SeriesOccurrence).where(SeriesOccurrence.event_id.in_(ids))).all()} if ids else {}
    series_by_id = {item.id: item for item in session.scalars(select(EventSeries).where(EventSeries.id.in_({item.series_id for item in occurrences.values()}))).all()} if occurrences else {}
    label_ids = event_label_ids(session, ids) if ids else {}
    lane_names = {lane.id: lane.name for lane in session.scalars(select(Lane).where(Lane.yearclock_id == yearclock_id)).all()}
    category_names = {item.id: item.name for item in session.scalars(select(Category).where(Category.id.in_({event.category_id for event in events if event.category_id}))).all()} if events else {}
    all_labels = {label.id: label.name for label in session.scalars(select(Label).where(Label.id.in_({label for labels in label_ids.values() for label in labels}))).all()} if label_ids else {}
    source_names = {clock.id: clock.name for clock in session.scalars(select(Yearclock).where(Yearclock.id.in_({source for _, source in links.values()}))).all()} if links else {}
    rows: list[ExportRow] = []
    for event, is_linked in [*[(event, False) for event in own], *[(event, True) for event in linked]]:
        occurrence = occurrences.get(event.id)
        if occurrence is not None and occurrence.skipped:
            continue
        lane_id = links[event.lane_id][0] if is_linked else event.lane_id
        labels = label_ids.get(event.id, [])
        if not _keep(body, lane_id, event.category_id, labels):
            continue
        series = series_by_id.get(occurrence.series_id) if occurrence else None
        rows.append(ExportRow(
            title=event.title, starts_on=event.starts_on, ends_on=event.ends_on, lane=lane_names.get(lane_id, ""),
            category=category_names.get(event.category_id, ""), labels=tuple(sorted(all_labels[label] for label in labels if label in all_labels)),
            starts_at=event.starts_at, ends_at=event.ends_at, description=plain_text(event.description, event.description_format), location=event.location or "", links=tuple((item["title"], item["url"]) for item in event.links or []),
            series=series_text(body.locale, series.frequency, series.interval, series.last_day) if series else "",
            source=source_names.get(links[event.lane_id][1], "") if is_linked else "",
            uid=f"{event.id}@yearclock" if occurrence is None else f"{event.id}-{occurrence.series_date:%Y%m%d}@yearclock", version=event.version,
        ))
    rows.sort(key=lambda row: (row.starts_on, row.starts_at is not None, row.starts_at or time.min, row.lane, row.title))
    return rows
