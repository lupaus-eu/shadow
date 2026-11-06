"""Import Events from Excel or CSV (Yearclock V2 P7, ADR-0030).

The file is read again for the preview and for the save, so the server stores
no upload. A save is all or nothing: any row error stops it, and the user
fixes the file. Lanes, Categories, and Labels must already exist.
"""
from datetime import date
from typing import Literal
from urllib.parse import urlparse
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, sessionmaker

from app.audit import AuditEventDraft, record_audit_event
from app.auth import AuthenticatedUser
from app.auth_routes import AuthenticatedUserDependency
from app.event_content import LINK_TITLE_MAX, LINKS_MAX, LOCATION_MAX, host_title
from app.event_labels import set_event_labels
from app.event_routes import _access_session, _audit
from app.exchange import (
    read_time,
    EXPORT_ACTIONS, IMPORT_MAX_BYTES, IMPORT_ROWS, REQUIRED_COLUMNS, HEADERS, ImportFileError, ParsedRow, build_template, cell_text, normalize, read_csv, read_xlsx, require_exchange_quota,
)
from app.limits import EVENTS, EXPORTS_PER_HOUR, LABELS_PER_EVENT, require_event_capacity
from app.models import Category, Event, Label, Lane
from app.revisions import set_revision_reason

TITLE_LIMIT, DESCRIPTION_LIMIT, URL_LIMIT = 200, 10_000, 2048


class ImportRowOut(BaseModel):
    row: int
    title: str
    starts_on: date
    ends_on: date | None
    lane: str
    category: str | None
    labels: list[str]


class ImportSkipped(BaseModel):
    row: int
    title: str
    reason: Literal["duplicate", "series", "linked"]


class ImportIssue(BaseModel):
    row: int
    column: str | None
    reason: str
    value: str | None = None


class ImportResult(BaseModel):
    rows: int
    create: list[ImportRowOut]
    skipped: list[ImportSkipped]
    errors: list[ImportIssue]
    created: int = 0
    import_id: UUID | None = None


async def import_body(request: Request) -> bytes:
    """The raw upload, refused as soon as it passes the size limit."""
    limit = IMPORT_MAX_BYTES.maximum
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > limit:
        raise HTTPException(status_code=413, detail={"reason": "file_too_large", "maximum_bytes": limit})
    data = bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data) > limit:
            raise HTTPException(status_code=413, detail={"reason": "file_too_large", "maximum_bytes": limit})
    return bytes(data)


def create_import_router(*, session_factory: sessionmaker[Session], authenticated_user_dependency: AuthenticatedUserDependency) -> APIRouter:
    router = APIRouter(prefix="/api/v1/organizations", tags=["Import"])

    @router.get("/{organization_id}/yearclocks/{yearclock_id}/import/template")
    def template(organization_id: UUID, yearclock_id: UUID, locale: Literal["en", "fi"] = "en", user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> Response:
        with _access_session(session_factory, organization_id, yearclock_id, user, mutate=False) as session:
            lanes = [lane.name for lane in session.scalars(select(Lane).where(Lane.yearclock_id == yearclock_id, Lane.source_lane_id.is_(None)).order_by(Lane.display_order)).all()]
            categories = [item.name for item in session.scalars(select(Category).where(or_(Category.yearclock_id == yearclock_id, Category.yearclock_id.is_(None))).order_by(Category.name)).all()]
            labels = [item.name for item in session.scalars(select(Label).order_by(Label.name)).all()]
            content = build_template(locale, lanes, categories, labels)
        return Response(content=content, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": f'attachment; filename="yearclock-import-template-{locale}.xlsx"', "Cache-Control": "no-store"})

    @router.post("/{organization_id}/yearclocks/{yearclock_id}/import", response_model=ImportResult)
    def import_events(organization_id: UUID, yearclock_id: UUID, request: Request, format: Literal["xlsx", "csv"] = Query(), dry_run: bool = Query(default=True), user: AuthenticatedUser = Depends(authenticated_user_dependency), body: bytes = Depends(import_body)) -> ImportResult:
        with _access_session(session_factory, organization_id, yearclock_id, user, mutate=True) as session:
            require_exchange_quota(session, user.account.id, organization_id, EXPORT_ACTIONS, EXPORTS_PER_HOUR)
            try:
                header, parsed = (read_xlsx if format == "xlsx" else read_csv)(body)
            except ImportFileError as error:
                raise HTTPException(status_code=422, detail={"reason": error.reason, **error.detail}) from error
            result, planned = _check(session, organization_id, yearclock_id, header, parsed)
            request_id = (request.headers.get("X-Request-ID") or str(uuid4()))[:120]
            summary = {"format": format, "rows": result.rows, "create": len(result.create), "skipped": len(result.skipped), "errors": len(result.errors)}
            if dry_run:
                record_audit_event(session, AuditEventDraft(action="yearclock.import_preview", target_type="yearclock", target_id=yearclock_id, request_id=request_id, change_summary=summary))
                return result
            if result.errors:
                raise HTTPException(status_code=422, detail={"reason": "errors", "errors": [issue.model_dump() for issue in result.errors]})
            if result.create:
                require_event_capacity(session, yearclock_id)
                current = session.scalar(select(func.count()).select_from(Event).where(Event.yearclock_id == yearclock_id, Event.deleted_at.is_(None))) or 0
                if current + len(result.create) > EVENTS.maximum:
                    raise HTTPException(status_code=409, detail={"reason": "limit_reached", "limit": EVENTS.name, "maximum": EVENTS.maximum})
            import_id = uuid4()
            _save(session, request, organization_id, yearclock_id, planned, import_id)
            result.created, result.import_id = len(result.create), import_id
            record_audit_event(session, AuditEventDraft(action="yearclock.import", target_type="yearclock", target_id=yearclock_id, request_id=request_id, change_summary={**summary, "import_id": str(import_id), "created": result.created}))
            return result

    return router


def _parse_date(value: object) -> date | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if isinstance(value, date):
        return value.date() if hasattr(value, "date") else value
    text = str(value).strip()
    try:
        return date.fromisoformat(text)
    except ValueError:
        pass
    parts = text.replace("/", ".").split(".")
    if len(parts) == 3 and all(part.isdigit() for part in parts):
        day, month, year = (int(part) for part in parts)
        try:
            return date(year, month, day)
        except ValueError:
            return None
    return None


def _parse_links(cell: str, add) -> list[dict[str, str]]:
    """``Title | address`` per line; a bare address (the old Link column) is titled with its host name."""
    links: list[dict[str, str]] = []
    for line in [part.strip() for part in cell.replace("\r", "").split("\n") if part.strip()]:
        title, separator, url = line.rpartition(" | ")
        if not separator:
            title, url = "", line
        url, title = url.strip(), title.strip()
        if len(url) > URL_LIMIT: add("links", "link_too_long", f"{len(url)}"); continue
        if urlparse(url).scheme not in {"http", "https"} or not urlparse(url).netloc: add("links", "invalid_link", url); continue
        title = title or host_title(url)
        if len(title) > LINK_TITLE_MAX: add("links", "link_title_too_long", f"{len(title)}"); continue
        if any(item["url"] == url for item in links): add("links", "duplicate_link", url); continue
        links.append({"title": title, "url": url})
    if len(links) > LINKS_MAX: add("links", "too_many_links", f"{len(links)}")
    return links


def _check(session: Session, organization_id: UUID, yearclock_id: UUID, header: list[str | None], parsed: list[ParsedRow]) -> tuple[ImportResult, list[tuple]]:
    errors: list[ImportIssue] = []
    present = {key for key in header if key}
    missing = [key for key in REQUIRED_COLUMNS if key not in present]
    if missing:
        names = ", ".join(HEADERS["en"][key] for key in missing)
        return ImportResult(rows=len(parsed), create=[], skipped=[], errors=[ImportIssue(row=1, column=names, reason="missing_column")]), []
    own_lanes = {normalize(lane.name): lane for lane in session.scalars(select(Lane).where(Lane.yearclock_id == yearclock_id, Lane.source_lane_id.is_(None))).all()}
    linked_lanes = {normalize(lane.name) for lane in session.scalars(select(Lane).where(Lane.yearclock_id == yearclock_id, Lane.source_lane_id.is_not(None))).all()}
    categories: dict[str, Category] = {}
    for item in session.scalars(select(Category).where(or_(Category.yearclock_id == yearclock_id, Category.yearclock_id.is_(None)))).all():
        key = normalize(item.name)
        if key not in categories or item.yearclock_id is not None:
            categories[key] = item
    labels = {normalize(item.name): item for item in session.scalars(select(Label)).all()}
    existing = {(lane_id, normalize(title), starts_on, ends_on or starts_on, starts_at) for lane_id, title, starts_on, ends_on, starts_at in session.execute(select(Event.lane_id, Event.title, Event.starts_on, Event.ends_on, Event.starts_at).where(Event.yearclock_id == yearclock_id, Event.deleted_at.is_(None))).all()}
    create: list[ImportRowOut] = []
    planned: list[tuple] = []
    skipped: list[ImportSkipped] = []
    seen: dict[tuple, int] = {}
    for row in parsed:
        text = lambda key: cell_text(row.cells.get(key))
        title = text("title")
        problems: list[ImportIssue] = []
        add = lambda column, reason, value=None: problems.append(ImportIssue(row=row.number, column=column, reason=reason, value=value))
        if text("series"):
            skipped.append(ImportSkipped(row=row.number, title=title, reason="series")); continue
        if text("source"):
            skipped.append(ImportSkipped(row=row.number, title=title, reason="linked")); continue
        if not title: add("title", "missing_title")
        elif len(title) > TITLE_LIMIT: add("title", "title_too_long", f"{len(title)}")
        starts_raw, ends_raw = row.cells.get("starts"), row.cells.get("ends")
        starts_on, ends_on = _parse_date(starts_raw), _parse_date(ends_raw)
        if starts_raw is None or text("starts") == "": add("starts", "missing_start")
        elif starts_on is None: add("starts", "invalid_date", text("starts"))
        if ends_raw is not None and text("ends") != "" and ends_on is None: add("ends", "invalid_date", text("ends"))
        if starts_on and ends_on and ends_on < starts_on: add("ends", "end_before_start", text("ends"))
        starts_at, bad_start = read_time(row.cells.get("start_time"))
        ends_at, bad_end = read_time(row.cells.get("end_time"))
        if bad_start: add("start_time", "invalid_time", text("start_time"))
        if bad_end: add("end_time", "invalid_time", text("end_time"))
        if ends_at is not None and starts_at is None and not bad_start: add("end_time", "end_time_without_start", text("end_time"))
        elif starts_at is not None and ends_at is not None and starts_on and (ends_on is None or ends_on == starts_on) and ends_at <= starts_at: add("end_time", "end_time_before_start", text("end_time"))
        lane_name = text("lane")
        lane = own_lanes.get(normalize(lane_name)) if lane_name else None
        if not lane_name: add("lane", "missing_lane")
        elif lane is None: add("lane", "linked_lane" if normalize(lane_name) in linked_lanes else "unknown_lane", lane_name)
        category = None
        if text("category"):
            category = categories.get(normalize(text("category")))
            if category is None: add("category", "unknown_category", text("category"))
        chosen: list[Label] = []
        for name in [part.strip() for part in text("labels").replace(";", ",").split(",") if part.strip()]:
            label = labels.get(normalize(name))
            if label is None: add("labels", "unknown_label", name)
            elif label not in chosen: chosen.append(label)
        if len(chosen) > LABELS_PER_EVENT.maximum: add("labels", "too_many_labels", f"{len(chosen)}")
        description = text("description") or None
        if description and len(description) > DESCRIPTION_LIMIT: add("description", "description_too_long", f"{len(description)}")
        location = text("location") or None
        if location and len(location) > LOCATION_MAX: add("location", "location_too_long", f"{len(location)}")
        links = _parse_links(text("links"), add)
        if problems:
            errors.extend(problems); continue
        key = (lane.id, normalize(title), starts_on, ends_on or starts_on, starts_at)
        if key in seen:
            errors.append(ImportIssue(row=row.number, column="title", reason="duplicate_in_file", value=f"{seen[key]}")); continue
        seen[key] = row.number
        if key in existing:
            skipped.append(ImportSkipped(row=row.number, title=title, reason="duplicate")); continue
        planned.append((lane, category, chosen, title, starts_on, ends_on, description, location, links, starts_at, ends_at))
        create.append(ImportRowOut(row=row.number, title=title, starts_on=starts_on, ends_on=ends_on, lane=lane.name, category=category.name if category else None, labels=sorted(label.name for label in chosen)))
    return ImportResult(rows=len(parsed), create=create, skipped=skipped, errors=errors), planned


def _save(session: Session, request: Request, organization_id: UUID, yearclock_id: UUID, planned: list[tuple], import_id: UUID) -> None:
    set_revision_reason(session, "import", {"import_id": str(import_id)})
    for lane, category, chosen, title, starts_on, ends_on, description, location, links, starts_at, ends_at in planned:
        event = Event(id=uuid4(), organization_id=organization_id, yearclock_id=yearclock_id, lane_id=lane.id, category_id=category.id if category else None, title=title, description=description, location=location, links=links, starts_at=starts_at, ends_at=ends_at, starts_on=starts_on, ends_on=ends_on, version=1)
        session.add(event)
        set_event_labels(session, event, chosen)
        _audit(session, request, "event.created", event.id, {"title": title, "labels": [label.name for label in chosen], "import_id": str(import_id)})
