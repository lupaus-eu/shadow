"""Data transfer: every Organization the user administers as one CSV file, and the file back in (ADR-0040).

One table with a ``type`` column. An import updates rows whose id exists and creates the others; it never deletes,
never creates an Organization, and never changes an Organization's settings. It is previewed first and saved all or
nothing. A preview runs the whole import inside a savepoint and rolls it back, so it meets exactly the checks a save does.
"""
import csv
import io
import json
from collections import defaultdict
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.access import is_manager, membership_of
from app.audit import AuditEventDraft, record_audit_event
from app.auth import AuthenticatedUser
from app.auth_routes import AuthenticatedUserDependency
from app.category_routes import CategoryRequest
from app.database import RequestContext, apply_request_context, transaction_session
from app.event_content import links_json, time_text
from app.event_labels import event_label_ids, series_label_ids, set_event_labels, set_series_labels
from app.event_routes import EventRequest
from app.exchange import file_name
from app.label_routes import LabelRequest
from app.limits import CATEGORIES, EVENTS, LABELS, LABELS_PER_EVENT, LANES, ORGANIZATION_CATEGORIES, SERIES, YEARCLOCKS, Ceiling
from app.models import (
    AuditEvent, Category, Event, EventRevision, EventSeries, Label, Lane, Organization, OrganizationMembership, OrganizationStatus,
    SeriesOccurrence, Yearclock,
)
from app.recurrence import materialization_horizon, materialize_series
from app.revisions import set_revision_reason, write_pending
from app.series_editing import OVERRIDE_FIELDS, _decode, _encode, apply_effective
from app.series_routes import SeriesRequest
from app.subscription_access import require_organization_mutation_access
from app.yearclock_routes import LaneRequest, StructureRequest

FORMAT = "yearclock-data/1"
EXPORT_ACTION, PREVIEW_ACTION, IMPORT_ACTION = "data.export", "data.import_preview", "data.import"
ACTIONS = (EXPORT_ACTION, PREVIEW_ACTION, IMPORT_ACTION)
TRANSFER_ROWS = Ceiling("transfer_rows", "LIMIT_TRANSFER_ROWS", 200_000)
TRANSFER_MAX_BYTES = Ceiling("transfer_max_bytes", "TRANSFER_MAX_BYTES", 100 * 1024 * 1024)
TRANSFERS_PER_HOUR = Ceiling("transfers_per_hour", "LIMIT_TRANSFERS_PER_HOUR", 3)
EXPORTABLE = (OrganizationStatus.ACTIVE.value, OrganizationStatus.PENDING_DELETION.value)
KINDS = ("organization", "label", "yearclock", "lane", "category", "series", "event", "series_exception")
COLUMNS = (
    "type", "id", "organization_id", "yearclock_id", "name", "color", "display_order", "tint", "height", "source_lane_id", "start_month",
    "show_week_ring", "show_quarter_ring", "organization_access", "archived", "lane_id", "category_id", "label_ids", "title", "description",
    "description_format", "location", "links", "starts_on", "ends_on", "starts_at", "ends_at", "frequency", "interval", "until",
    "occurrence_count", "last_day", "effective_from", "series_id", "series_date", "skipped", "overrides",
)
REQUIRED_HEADER = ("type", "id", "organization_id")
FORMULA_STARTS = ("=", "+", "-", "@", "\t", "\r")
RULE_FIELDS = ("starts_on", "frequency", "interval", "until", "occurrence_count", "last_day", "effective_from")


# ── Scope ─────────────────────────────────────────────────────────────────────

def administered_organizations(session: Session, user_account_id: UUID) -> list[Organization]:
    """The Organizations where the user is Owner or Admin (through the single access rule)."""
    memberships = session.scalars(select(OrganizationMembership).where(OrganizationMembership.user_account_id == user_account_id)).all()
    result = []
    for membership in memberships:
        if not is_manager(membership):
            continue
        apply_request_context(session, RequestContext(user_account_id=user_account_id, organization_id=membership.organization_id))
        organization = session.get(Organization, membership.organization_id)
        if organization is not None and organization.status in EXPORTABLE:
            result.append(organization)
    apply_request_context(session, RequestContext(user_account_id=user_account_id))
    return sorted(result, key=lambda item: (item.name.lower(), str(item.id)))


def require_transfer_quota(session: Session, user_account_id: UUID, organization_ids: list[UUID]) -> None:
    """429 when the user already made the hourly allowance of transfers; the Audit Log is the counter (one request id per transfer)."""
    now = session.scalar(select(func.now()))
    since = now.replace(microsecond=0) - timedelta(hours=1)
    seen: dict[str, datetime] = {}
    for organization_id in organization_ids:
        apply_request_context(session, RequestContext(user_account_id=user_account_id, organization_id=organization_id))
        for request_id, occurred_at in session.execute(select(AuditEvent.request_id, AuditEvent.occurred_at).where(AuditEvent.actor_user_account_id == user_account_id, AuditEvent.action.in_(ACTIONS), AuditEvent.occurred_at > since)).all():
            seen[request_id] = min(occurred_at, seen.get(request_id, occurred_at))
    apply_request_context(session, RequestContext(user_account_id=user_account_id))
    if len(seen) >= TRANSFERS_PER_HOUR.maximum:
        ordered = sorted(seen.values())
        retry_after = max(1, int((ordered[len(seen) - TRANSFERS_PER_HOUR.maximum] + timedelta(hours=1) - now).total_seconds()) + 1)
        raise HTTPException(status_code=429, detail={"reason": "rate_limited", "limit": TRANSFERS_PER_HOUR.name, "maximum": TRANSFERS_PER_HOUR.maximum, "retry_after_seconds": retry_after}, headers={"Retry-After": str(retry_after)})


# ── Export ────────────────────────────────────────────────────────────────────

def neutralize(value: str) -> str:
    """A text cell that a spreadsheet could read as a formula gets a leading apostrophe."""
    return "'" + value if value.startswith(FORMULA_STARTS) else value


def restore(value: str) -> str:
    return value[1:] if value.startswith("'") and value[1:].startswith(FORMULA_STARTS) else value


def _cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if isinstance(value, str):
        return neutralize(value)
    return str(value)


def _line(writer: Any, buffer: io.StringIO, row: dict[str, Any]) -> str:
    writer.writerow([_cell(row.get(column)) for column in COLUMNS])
    text = buffer.getvalue()
    buffer.seek(0)
    buffer.truncate(0)
    return text


def _labels_text(ids: list[UUID]) -> str:
    return ";".join(str(item) for item in ids)


def organization_rows(session: Session, organization: Organization) -> Iterator[dict[str, Any]]:
    """The rows of one Organization, one Yearclock at a time so memory stays bounded."""
    organization_id = organization.id
    base = {"organization_id": organization_id}
    yield {"type": "organization", "id": organization_id, "name": organization.name, **base}
    for label in session.scalars(select(Label).order_by(Label.name, Label.id)).all():
        yield {"type": "label", "id": label.id, "name": label.name, "color": label.color, **base}
    for item in session.scalars(select(Category).where(Category.yearclock_id.is_(None)).order_by(Category.display_order, Category.id)).all():
        yield {"type": "category", "id": item.id, "name": item.name, "color": item.color, "display_order": item.display_order, **base}
    clock_ids = session.scalars(select(Yearclock.id).where(Yearclock.deleted_at.is_(None)).order_by(Yearclock.display_order, Yearclock.id)).all()
    for clock_id in clock_ids:
        clock = session.get(Yearclock, clock_id)
        yield {"type": "yearclock", "id": clock.id, "name": clock.name, "display_order": clock.display_order, "start_month": clock.start_month, "show_week_ring": clock.show_week_ring, "show_quarter_ring": clock.show_quarter_ring, "organization_access": clock.organization_access, "archived": clock.archived_at, **base}
        yc = {**base, "yearclock_id": clock.id}
        for lane in session.scalars(select(Lane).where(Lane.yearclock_id == clock.id).order_by(Lane.display_order, Lane.id)).all():
            yield {"type": "lane", "id": lane.id, "name": lane.name, "display_order": lane.display_order, "tint": lane.tint, "height": lane.height, "source_lane_id": lane.source_lane_id, **yc}
        for item in session.scalars(select(Category).where(Category.yearclock_id == clock.id).order_by(Category.display_order, Category.id)).all():
            yield {"type": "category", "id": item.id, "name": item.name, "color": item.color, "display_order": item.display_order, **yc}
        series = session.scalars(select(EventSeries).where(EventSeries.yearclock_id == clock.id).order_by(EventSeries.starts_on, EventSeries.effective_from, EventSeries.id)).all()
        for item in series:
            yield {"type": "series", "id": item.id, "lane_id": item.lane_id, "category_id": item.category_id, "label_ids": _labels_text(series_label_ids(session, item.id)), "title": item.title, "description": item.description, "description_format": item.description_format, "location": item.location, "links": item.links or [], "starts_on": item.starts_on, "starts_at": time_text(item.starts_at), "ends_at": time_text(item.ends_at), "frequency": item.frequency, "interval": item.interval, "until": item.until, "occurrence_count": item.occurrence_count, "last_day": item.last_day, "effective_from": item.effective_from, **yc}
        occurrence_events = select(SeriesOccurrence.event_id)
        events = session.scalars(select(Event).where(Event.yearclock_id == clock.id, Event.deleted_at.is_(None), Event.id.not_in(occurrence_events)).order_by(Event.starts_on, Event.id)).all()
        labels = event_label_ids(session, [event.id for event in events])
        for event in events:
            yield {"type": "event", "id": event.id, "lane_id": event.lane_id, "category_id": event.category_id, "label_ids": _labels_text(labels.get(event.id, [])), "title": event.title, "description": event.description, "description_format": event.description_format, "location": event.location, "links": event.links or [], "starts_on": event.starts_on, "ends_on": event.ends_on, "starts_at": time_text(event.starts_at), "ends_at": time_text(event.ends_at), **yc}
        for occurrence in session.scalars(select(SeriesOccurrence).join(EventSeries, EventSeries.id == SeriesOccurrence.series_id).where(EventSeries.yearclock_id == clock.id).where((SeriesOccurrence.skipped.is_(True)) | (SeriesOccurrence.overrides != {})).order_by(SeriesOccurrence.series_id, SeriesOccurrence.series_date)).all():
            yield {"type": "series_exception", "id": occurrence.id, "series_id": occurrence.series_id, "series_date": occurrence.series_date, "skipped": occurrence.skipped, "overrides": occurrence.overrides or {}, **yc}
        session.expire_all()


# ── Reading the file ──────────────────────────────────────────────────────────

class TransferFileError(Exception):
    def __init__(self, reason: str, **detail: Any) -> None:
        super().__init__(reason)
        self.reason, self.detail = reason, detail


@dataclass
class Row:
    number: int
    kind: str
    cells: dict[str, str]


def read_file(data: bytes) -> tuple[list[Row], datetime | None]:
    """Rows of the file, and the time of the export from its format row."""
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise TransferFileError("not_utf8") from error
    reader = csv.reader(io.StringIO(text, newline=""))
    try:
        header = next(reader)
    except StopIteration as error:
        raise TransferFileError("empty_file") from error
    except csv.Error as error:
        raise TransferFileError("unreadable_file") from error
    header = [item.strip().lower() for item in header]
    missing = [name for name in REQUIRED_HEADER if name not in header]
    if missing:
        raise TransferFileError("missing_column", columns=missing)
    rows: list[Row] = []
    exported_at: datetime | None = None
    saw_format = False
    try:
        for number, record in enumerate(reader, start=2):
            if not any(item.strip() for item in record):
                continue
            if len(rows) >= TRANSFER_ROWS.maximum:
                raise TransferFileError("too_many_rows", maximum=TRANSFER_ROWS.maximum)
            cells = {name: restore(value.strip()) if name not in ("description",) else restore(value) for name, value in zip(header, record) if name in COLUMNS}
            kind = cells.get("type", "").lower()
            if kind == "format":
                if cells.get("id") != FORMAT:
                    raise TransferFileError("unsupported_format", format=cells.get("id", ""))
                saw_format = True
                try:
                    exported_at = datetime.fromisoformat(cells.get("name", ""))
                except ValueError:
                    exported_at = None
                continue
            rows.append(Row(number, kind, cells))
    except csv.Error as error:
        raise TransferFileError("unreadable_file") from error
    if not saw_format:
        raise TransferFileError("missing_format_row", expected=FORMAT)
    return rows, exported_at


# ── Import ────────────────────────────────────────────────────────────────────

class Issue(BaseModel):
    row: int
    type: str | None = None
    column: str | None = None
    reason: str
    value: str | None = None


class KindCounts(BaseModel):
    created: int = 0
    updated: int = 0
    unchanged: int = 0


class OrganizationSummary(BaseModel):
    id: UUID
    name: str | None = None
    kinds: dict[str, KindCounts]
    overwrites_newer: int = 0


class TransferResult(BaseModel):
    rows: int
    organizations: list[OrganizationSummary]
    errors: list[Issue]
    saved: bool = False
    import_id: UUID | None = None


class Stop(Exception):
    """Row-level failure; the reason is reported with its row."""

    def __init__(self, reason: str, column: str | None = None, value: Any = None) -> None:
        super().__init__(reason)
        self.reason, self.column, self.value = reason, column, None if value is None else str(value)[:200]


def _uuid(value: str, column: str, *, required: bool = False) -> UUID | None:
    if not value:
        if required:
            raise Stop("missing_value", column)
        return None
    try:
        return UUID(value)
    except ValueError as error:
        raise Stop("invalid_id", column, value) from error


def _bool(value: str, column: str, default: bool = False) -> bool:
    if value == "":
        return default
    if value.lower() in {"true", "1", "yes", "kyllä"}:
        return True
    if value.lower() in {"false", "0", "no", "ei"}:
        return False
    raise Stop("invalid_boolean", column, value)


def _int(value: str, column: str, default: int | None = None) -> int | None:
    if value == "":
        return default
    try:
        return int(value)
    except ValueError as error:
        raise Stop("invalid_number", column, value) from error


def _text(cells: dict[str, str], column: str) -> str | None:
    return cells.get(column) or None


def _validate(model: type[BaseModel], payload: dict[str, Any]) -> BaseModel:
    try:
        return model.model_validate(payload)
    except ValidationError as error:
        first = error.errors()[0]
        column = str(first["loc"][0]) if first["loc"] else None
        raise Stop("invalid_value:" + str(first["type"]), column, first.get("input")) from error


def _links(cells: dict[str, str]) -> list[Any]:
    raw = cells.get("links", "")
    if not raw:
        return []
    try:
        value = json.loads(raw)
    except ValueError as error:
        raise Stop("invalid_json", "links", raw[:60]) from error
    if not isinstance(value, list):
        raise Stop("invalid_json", "links", raw[:60])
    return value


def _assign(target: Any, values: dict[str, Any]) -> bool:
    changed = False
    for name, value in values.items():
        if getattr(target, name) != value:
            setattr(target, name, value)
            changed = True
    if changed and hasattr(target, "version"):
        target.version = (target.version or 1) + 1
    return changed


@dataclass
class OrganizationState:
    """What an Organization holds before the import, kept current as rows are applied."""
    organization: Organization
    labels: dict[UUID, Label]
    yearclocks: dict[UUID, Yearclock]
    lanes: dict[UUID, Lane]
    categories: dict[UUID, Category]
    series: dict[UUID, EventSeries]
    counts: dict[str, int] = field(default_factory=dict)
    event_counts: dict[UUID, int] = field(default_factory=dict)
    summary: dict[str, KindCounts] = field(default_factory=lambda: defaultdict(KindCounts))
    overwrites_newer: int = 0


def _load_state(session: Session, organization: Organization) -> OrganizationState:
    session.execute(select(Organization.id).where(Organization.id == organization.id).with_for_update())
    state = OrganizationState(
        organization=organization,
        labels={item.id: item for item in session.scalars(select(Label)).all()},
        yearclocks={item.id: item for item in session.scalars(select(Yearclock)).all()},
        lanes={item.id: item for item in session.scalars(select(Lane)).all()},
        categories={item.id: item for item in session.scalars(select(Category)).all()},
        series={item.id: item for item in session.scalars(select(EventSeries)).all()},
    )
    state.event_counts = dict(session.execute(select(Event.yearclock_id, func.count()).where(Event.deleted_at.is_(None)).group_by(Event.yearclock_id)).all())
    return state


def _capacity(state: OrganizationState, ceiling: Ceiling, key: str, current: int) -> None:
    used = state.counts.setdefault(key, current)
    if used >= ceiling.maximum:
        raise Stop("limit_reached:" + ceiling.name)
    state.counts[key] = used + 1


def _bump(state: OrganizationState, kind: str, outcome: str) -> None:
    setattr(state.summary[kind], outcome, getattr(state.summary[kind], outcome) + 1)


def _clock_of(state: OrganizationState, cells: dict[str, str]) -> Yearclock:
    clock = state.yearclocks.get(_uuid(cells.get("yearclock_id", ""), "yearclock_id", required=True))
    if clock is None:
        raise Stop("unknown_parent", "yearclock_id", cells.get("yearclock_id"))
    if clock.deleted_at is not None:
        raise Stop("deleted_in_database", "yearclock_id", cells.get("yearclock_id"))
    return clock


def _apply_label(session: Session, state: OrganizationState, row: Row) -> None:
    cells = row.cells
    item_id = _uuid(cells["id"], "id", required=True)
    body = _validate(LabelRequest, {"name": cells.get("name", ""), "color": cells.get("color", "")})
    existing = state.labels.get(item_id)
    if existing is not None:
        _bump(state, "label", "updated" if _assign(existing, {"name": body.name, "color": body.color}) else "unchanged")
        return
    _capacity(state, LABELS, "labels", len(state.labels))
    item = Label(id=item_id, organization_id=state.organization.id, name=body.name, color=body.color, version=1)
    session.add(item)
    state.labels[item_id] = item
    _bump(state, "label", "created")


def _apply_yearclock(session: Session, state: OrganizationState, row: Row) -> None:
    cells = row.cells
    item_id = _uuid(cells["id"], "id", required=True)
    body = _validate(StructureRequest, {"name": cells.get("name", "")})
    month, order = _int(cells.get("start_month", ""), "start_month", 1), _int(cells.get("display_order", ""), "display_order", 0)
    if month is None or not 1 <= month <= 12:
        raise Stop("invalid_number", "start_month", cells.get("start_month"))
    access = cells.get("organization_access") or "none"
    if access not in {"none", "viewer", "editor"}:
        raise Stop("invalid_value", "organization_access", access)
    archived = cells.get("archived", "")
    try:
        archived_at = datetime.fromisoformat(archived) if archived else None
    except ValueError as error:
        raise Stop("invalid_date", "archived", archived) from error
    if archived_at is not None and archived_at.tzinfo is None:
        archived_at = archived_at.replace(tzinfo=timezone.utc)
    values = {"name": body.name, "display_order": order, "start_month": month, "show_week_ring": _bool(cells.get("show_week_ring", ""), "show_week_ring"), "show_quarter_ring": _bool(cells.get("show_quarter_ring", ""), "show_quarter_ring"), "organization_access": access}
    existing = state.yearclocks.get(item_id)
    if existing is not None:
        if existing.deleted_at is not None:
            raise Stop("deleted_in_database", "id", item_id)
        changed = _assign(existing, values)
        if (existing.archived_at is None) != (archived_at is None):
            existing.archived_at = archived_at
            if not changed:
                existing.version += 1
            changed = True
        _bump(state, "yearclock", "updated" if changed else "unchanged")
        return
    _capacity(state, YEARCLOCKS, "yearclocks", sum(1 for clock in state.yearclocks.values() if clock.deleted_at is None))
    item = Yearclock(id=item_id, organization_id=state.organization.id, version=1, archived_at=archived_at, **values)
    session.add(item)
    state.yearclocks[item_id] = item
    _bump(state, "yearclock", "created")


def _apply_lane(session: Session, state: OrganizationState, row: Row) -> None:
    cells = row.cells
    item_id = _uuid(cells["id"], "id", required=True)
    clock = _clock_of(state, cells)
    source_id = _uuid(cells.get("source_lane_id", ""), "source_lane_id")
    order = _int(cells.get("display_order", ""), "display_order", 0)
    existing = state.lanes.get(item_id)
    if source_id is not None:
        source = state.lanes.get(source_id)
        if source is None or source.source_lane_id is not None or source.yearclock_id == clock.id:
            raise Stop("unknown_source_lane", "source_lane_id", source_id)
        values = {"name": source.name, "display_order": order}
        body = _validate(StructureRequest, {"name": cells.get("name") or source.name})
        values["name"] = body.name
    else:
        body = _validate(LaneRequest, {"name": cells.get("name", ""), "tint": cells.get("tint") or None, "height": cells.get("height") or "normal"})
        values = {"name": body.name, "display_order": order, "tint": body.tint, "height": body.height or "normal"}
    if existing is not None:
        if existing.yearclock_id != clock.id or existing.source_lane_id != source_id:
            raise Stop("wrong_parent", "yearclock_id", cells.get("yearclock_id"))
        _bump(state, "lane", "updated" if _assign(existing, values) else "unchanged")
        return
    _capacity(state, LANES, f"lanes:{clock.id}", sum(1 for lane in state.lanes.values() if lane.yearclock_id == clock.id))
    item = Lane(id=item_id, organization_id=state.organization.id, yearclock_id=clock.id, version=1, source_lane_id=source_id, **values)
    session.add(item)
    state.lanes[item_id] = item
    _bump(state, "lane", "created")


def _apply_category(session: Session, state: OrganizationState, row: Row) -> None:
    cells = row.cells
    item_id = _uuid(cells["id"], "id", required=True)
    clock_id = None
    if cells.get("yearclock_id"):
        clock_id = _clock_of(state, cells).id
    body = _validate(CategoryRequest, {"name": cells.get("name", ""), "color": cells.get("color") or None})
    values = {"name": body.name, "color": body.color, "display_order": _int(cells.get("display_order", ""), "display_order", 0)}
    existing = state.categories.get(item_id)
    if existing is not None:
        if existing.yearclock_id != clock_id:
            raise Stop("wrong_parent", "yearclock_id", cells.get("yearclock_id"))
        _bump(state, "category", "updated" if _assign(existing, values) else "unchanged")
        return
    if clock_id is None:
        _capacity(state, ORGANIZATION_CATEGORIES, "organization_categories", sum(1 for item in state.categories.values() if item.yearclock_id is None))
    else:
        _capacity(state, CATEGORIES, f"categories:{clock_id}", sum(1 for item in state.categories.values() if item.yearclock_id == clock_id))
    item = Category(id=item_id, organization_id=state.organization.id, yearclock_id=clock_id, version=1, **values)
    session.add(item)
    state.categories[item_id] = item
    _bump(state, "category", "created")


def _references(state: OrganizationState, clock: Yearclock, cells: dict[str, str]) -> tuple[UUID, UUID | None, list[Label]]:
    lane_id = _uuid(cells.get("lane_id", ""), "lane_id", required=True)
    lane = state.lanes.get(lane_id)
    if lane is None or lane.yearclock_id != clock.id:
        raise Stop("unknown_lane", "lane_id", lane_id)
    if lane.source_lane_id is not None:
        raise Stop("linked_lane", "lane_id", lane_id)
    category_id = _uuid(cells.get("category_id", ""), "category_id")
    if category_id is not None:
        category = state.categories.get(category_id)
        if category is None or category.yearclock_id not in (None, clock.id):
            raise Stop("unknown_category", "category_id", category_id)
    labels: list[Label] = []
    for part in [item.strip() for item in cells.get("label_ids", "").split(";") if item.strip()]:
        label = state.labels.get(_uuid(part, "label_ids"))
        if label is None:
            raise Stop("unknown_label", "label_ids", part)
        if label not in labels:
            labels.append(label)
    if len(labels) > LABELS_PER_EVENT.maximum:
        raise Stop("limit_reached:" + LABELS_PER_EVENT.name, "label_ids", len(labels))
    return lane_id, category_id, labels


def _content(cells: dict[str, str], lane_id: UUID, category_id: UUID | None, labels: list[Label], extra: dict[str, Any]) -> dict[str, Any]:
    return {"title": cells.get("title", ""), "lane_id": lane_id, "category_id": category_id, "description": _text(cells, "description"), "description_format": cells.get("description_format") or None, "location": _text(cells, "location"), "links": _links(cells), "starts_at": _text(cells, "starts_at"), "ends_at": _text(cells, "ends_at"), "label_ids": [label.id for label in labels], **extra}


def _apply_series(session: Session, state: OrganizationState, row: Row, due: dict[UUID, date], horizon: date) -> None:
    cells = row.cells
    item_id = _uuid(cells["id"], "id", required=True)
    clock = _clock_of(state, cells)
    lane_id, category_id, labels = _references(state, clock, cells)
    payload = _content(cells, lane_id, category_id, labels, {"starts_on": cells.get("starts_on", ""), "frequency": cells.get("frequency", ""), "interval": cells.get("interval") or 1, "until": cells.get("until") or None, "occurrence_count": cells.get("occurrence_count") or None, "last_day": _bool(cells.get("last_day", ""), "last_day")})
    payload["description_format"] = payload["description_format"] or "plain"
    body = _validate(SeriesRequest, payload)
    effective_from = date.fromisoformat(cells["effective_from"]) if cells.get("effective_from") else body.starts_on
    content = {"title": body.title, "lane_id": lane_id, "category_id": category_id, "description": body.description, "description_format": body.description_format, "location": body.location, "links": links_json(body.links), "starts_at": body.starts_at, "ends_at": body.ends_at}
    rule = {"starts_on": body.starts_on, "frequency": body.frequency, "interval": body.interval, "until": body.until, "occurrence_count": body.occurrence_count, "last_day": body.last_day, "effective_from": effective_from}
    existing = state.series.get(item_id)
    label_ids = [label.id for label in labels]
    if existing is not None:
        if existing.yearclock_id != clock.id:
            raise Stop("wrong_parent", "yearclock_id", cells.get("yearclock_id"))
        if any(getattr(existing, name) != value for name, value in rule.items()):
            raise Stop("series_rule_changed", "frequency")
        changed = _assign(existing, content)
        if set(series_label_ids(session, item_id)) != set(label_ids):
            set_series_labels(session, existing, label_ids)
            changed = True
            existing.version += 1
        if changed:
            session.flush()
            for occurrence, event in session.execute(select(SeriesOccurrence, Event).join(Event, Event.id == SeriesOccurrence.event_id).where(SeriesOccurrence.series_id == item_id)).all():
                apply_effective(event, existing, occurrence)
        _bump(state, "series", "updated" if changed else "unchanged")
        return
    _capacity(state, SERIES, f"series:{clock.id}", sum(1 for item in state.series.values() if item.yearclock_id == clock.id))
    item = EventSeries(id=item_id, organization_id=state.organization.id, yearclock_id=clock.id, version=1, **content, **rule)
    session.add(item)
    session.flush()
    set_series_labels(session, item, label_ids)
    state.series[item_id] = item
    due[item_id] = horizon
    _bump(state, "series", "created")


def _apply_events(session: Session, state: OrganizationState, rows: list[Row], issues: list[Issue], exported_at: datetime | None) -> None:
    for start in range(0, len(rows), 500):
        chunk = rows[start:start + 500]
        ids = [row.cells.get("id", "") for row in chunk]
        valid_ids = []
        for value in ids:
            try:
                valid_ids.append(UUID(value))
            except ValueError:
                pass
        existing = {item.id: item for item in session.scalars(select(Event).where(Event.id.in_(valid_ids)).with_for_update()).all()} if valid_ids else {}
        recurring = set(session.scalars(select(SeriesOccurrence.event_id).where(SeriesOccurrence.event_id.in_(list(existing)))).all()) if existing else set()
        current_labels = event_label_ids(session, list(existing)) if existing else {}
        newer: dict[UUID, datetime] = dict(session.execute(select(EventRevision.event_id, func.max(EventRevision.created_at)).where(EventRevision.event_id.in_(list(existing))).group_by(EventRevision.event_id)).all()) if existing and exported_at else {}
        for row in chunk:
            try:
                _apply_event(session, state, row, existing, recurring, current_labels, newer, exported_at)
            except Stop as stop:
                issues.append(Issue(row=row.number, type=row.kind, column=stop.column, reason=stop.reason, value=stop.value))


def _apply_event(session: Session, state: OrganizationState, row: Row, existing: dict[UUID, Event], recurring: set[UUID], current_labels: dict[UUID, list[UUID]], newer: dict[UUID, datetime], exported_at: datetime | None) -> None:
    cells = row.cells
    item_id = _uuid(cells["id"], "id", required=True)
    clock = _clock_of(state, cells)
    lane_id, category_id, labels = _references(state, clock, cells)
    body = _validate(EventRequest, _content(cells, lane_id, category_id, labels, {"starts_on": cells.get("starts_on", ""), "ends_on": cells.get("ends_on") or None}))
    values = {"title": body.title, "lane_id": lane_id, "category_id": category_id, "description": body.description, "description_format": body.description_format or "plain", "location": body.location, "links": links_json(body.links), "starts_at": body.starts_at, "ends_at": body.ends_at, "starts_on": body.starts_on, "ends_on": body.ends_on}
    event = existing.get(item_id)
    label_ids = [label.id for label in labels]
    if event is not None:
        if event.yearclock_id != clock.id:
            raise Stop("wrong_parent", "yearclock_id", cells.get("yearclock_id"))
        if event.deleted_at is not None:
            raise Stop("deleted_in_database", "id", item_id)
        if item_id in recurring:
            raise Stop("recurring_occurrence", "id", item_id)
        changed = _assign(event, values)
        if set(current_labels.get(item_id, [])) != set(label_ids):
            set_event_labels(session, event, labels)
            if not changed:
                event.version += 1
            changed = True
        if changed and exported_at is not None and newer.get(item_id) is not None and newer[item_id] > exported_at:
            state.overwrites_newer += 1
        _bump(state, "event", "updated" if changed else "unchanged")
        return
    used = state.event_counts.get(clock.id, 0)
    if used >= EVENTS.maximum:
        raise Stop("limit_reached:" + EVENTS.name)
    state.event_counts[clock.id] = used + 1
    event = Event(id=item_id, organization_id=state.organization.id, yearclock_id=clock.id, version=1, **values)
    session.add(event)
    existing[item_id] = event
    set_event_labels(session, event, labels)
    _bump(state, "event", "created")


def _apply_exceptions(session: Session, state: OrganizationState, rows: list[Row], issues: list[Issue]) -> None:
    for row in rows:
        try:
            _apply_exception(session, state, row)
        except Stop as stop:
            issues.append(Issue(row=row.number, type=row.kind, column=stop.column, reason=stop.reason, value=stop.value))


def _apply_exception(session: Session, state: OrganizationState, row: Row) -> None:
    cells = row.cells
    series_id = _uuid(cells.get("series_id", ""), "series_id", required=True)
    series = state.series.get(series_id)
    if series is None:
        raise Stop("unknown_parent", "series_id", series_id)
    try:
        series_date = date.fromisoformat(cells.get("series_date", ""))
    except ValueError as error:
        raise Stop("invalid_date", "series_date", cells.get("series_date")) from error
    occurrence = session.scalar(select(SeriesOccurrence).where(SeriesOccurrence.series_id == series_id, SeriesOccurrence.series_date == series_date).with_for_update())
    if occurrence is None:
        raise Stop("unknown_occurrence", "series_date", series_date)
    raw = cells.get("overrides", "")
    try:
        overrides = json.loads(raw) if raw else {}
    except ValueError as error:
        raise Stop("invalid_json", "overrides", raw[:60]) from error
    if not isinstance(overrides, dict) or any(key not in OVERRIDE_FIELDS for key in overrides):
        raise Stop("invalid_json", "overrides", raw[:60])
    try:
        decoded = {key: _decode(key, value) for key, value in overrides.items()}
        for key in ("lane_id", "category_id"):
            if decoded.get(key) is not None and (state.lanes if key == "lane_id" else state.categories).get(decoded[key]) is None:
                raise Stop("unknown_lane" if key == "lane_id" else "unknown_category", "overrides", decoded[key])
        for label_id in decoded.get("label_ids") or []:
            if label_id not in state.labels:
                raise Stop("unknown_label", "overrides", label_id)
    except (ValueError, TypeError, AttributeError) as error:
        raise Stop("invalid_json", "overrides", raw[:60]) from error
    overrides = {key: _encode(key, value) for key, value in decoded.items()}
    skipped = _bool(cells.get("skipped", ""), "skipped")
    if (occurrence.overrides or {}) == overrides and occurrence.skipped == skipped:
        _bump(state, "series_exception", "unchanged")
        return
    occurrence.overrides, occurrence.skipped = overrides, skipped
    event = session.get(Event, occurrence.event_id)
    if not apply_effective(event, series, occurrence):
        event.version += 1
    _bump(state, "series_exception", "updated")


def _apply_organization(session: Session, state: OrganizationState, rows: dict[str, list[Row]], issues: list[Issue], exported_at: datetime | None) -> None:
    def each(kind: str, apply: Any) -> None:
        for row in rows.get(kind, []):
            try:
                apply(row)
            except Stop as stop:
                issues.append(Issue(row=row.number, type=row.kind, column=stop.column, reason=stop.reason, value=stop.value))

    each("label", lambda row: _apply_label(session, state, row))
    each("yearclock", lambda row: _apply_yearclock(session, state, row))
    each("category", lambda row: _apply_category(session, state, row) if not row.cells.get("yearclock_id") else None)
    session.flush()
    # Lanes first, Linked Lanes after the Lanes they show.
    each("lane", lambda row: _apply_lane(session, state, row) if not row.cells.get("source_lane_id") else None)
    session.flush()
    each("lane", lambda row: _apply_lane(session, state, row) if row.cells.get("source_lane_id") else None)
    each("category", lambda row: _apply_category(session, state, row) if row.cells.get("yearclock_id") else None)
    session.flush()
    horizon = materialization_horizon(state.organization.time_zone)
    due: dict[UUID, date] = {}
    each("series", lambda row: _apply_series(session, state, row, due, horizon))
    session.flush()
    _apply_events(session, state, rows.get("event", []), issues, exported_at)
    session.flush()
    exceptions = rows.get("series_exception", [])
    for row in exceptions:
        try:
            series_id, series_date = UUID(row.cells.get("series_id", "")), date.fromisoformat(row.cells.get("series_date", ""))
        except ValueError:
            continue
        if series_id in state.series:
            due[series_id] = max(due.get(series_id, series_date), series_date)
    for series_id, through in due.items():
        materialize_series(session, state.series[series_id], through=through, reason="import")
    session.flush()
    _apply_exceptions(session, state, exceptions, issues)
    session.flush()


def run_import(session: Session, user_account_id: UUID, rows: list[Row], exported_at: datetime | None, import_id: UUID) -> tuple[list[OrganizationSummary], list[Issue]]:
    issues: list[Issue] = []
    by_organization: dict[UUID, dict[str, list[Row]]] = {}
    for row in rows:
        if row.kind not in KINDS:
            issues.append(Issue(row=row.number, type=row.kind or None, column="type", reason="unknown_type", value=row.kind or None))
            continue
        try:
            organization_id = _uuid(row.cells.get("organization_id", ""), "organization_id", required=True)
        except Stop as stop:
            issues.append(Issue(row=row.number, type=row.kind, column=stop.column, reason=stop.reason, value=stop.value))
            continue
        if row.kind not in ("organization", "series_exception"):
            if not row.cells.get("id"):
                issues.append(Issue(row=row.number, type=row.kind, column="id", reason="missing_value"))
                continue
        by_organization.setdefault(organization_id, defaultdict(list))[row.kind].append(row)
    summaries: list[OrganizationSummary] = []
    for organization_id, groups in by_organization.items():
        apply_request_context(session, RequestContext(user_account_id=user_account_id))
        membership = membership_of(session, organization_id, user_account_id)
        file_rows = [row for group in groups.values() for row in group]
        if membership is None or not is_manager(membership):
            issues.extend(Issue(row=row.number, type=row.kind, column="organization_id", reason="not_administrator", value=str(organization_id)) for row in file_rows)
            continue
        apply_request_context(session, RequestContext(user_account_id=user_account_id, organization_id=organization_id))
        try:
            organization = require_organization_mutation_access(session, organization_id)
        except HTTPException as error:
            reason = "organization_not_active" if "not active" in str(error.detail) else "organization_read_only"
            issues.extend(Issue(row=row.number, type=row.kind, column="organization_id", reason=reason, value=str(organization_id)) for row in file_rows)
            continue
        state = _load_state(session, organization)
        set_revision_reason(session, "import", {"import_id": str(import_id)})
        _apply_organization(session, state, groups, issues, exported_at)
        session.flush()
        write_pending(session)  # Event Revisions are written under this Organization's context
        summaries.append(OrganizationSummary(id=organization_id, name=organization.name, kinds={kind: counts for kind, counts in state.summary.items()}, overwrites_newer=state.overwrites_newer))
    apply_request_context(session, RequestContext(user_account_id=user_account_id))
    return summaries, issues


# ── Routes ────────────────────────────────────────────────────────────────────

class OrganizationOut(BaseModel):
    id: UUID
    name: str
    role: str


class ScopeOut(BaseModel):
    organizations: list[OrganizationOut]


async def transfer_body(request: Request) -> bytes:
    limit = TRANSFER_MAX_BYTES.maximum
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > limit:
        raise HTTPException(status_code=413, detail={"reason": "file_too_large", "maximum_bytes": limit})
    data = bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data) > limit:
            raise HTTPException(status_code=413, detail={"reason": "file_too_large", "maximum_bytes": limit})
    return bytes(data)


def _request_id(request: Request) -> str:
    return (request.headers.get("X-Request-ID") or str(uuid4()))[:120]


def create_data_transfer_router(*, session_factory: sessionmaker[Session], authenticated_user_dependency: AuthenticatedUserDependency) -> APIRouter:
    router = APIRouter(prefix="/api/v1/data-transfer", tags=["Data transfer"])

    @router.get("/organizations", response_model=ScopeOut)
    def scope(user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> ScopeOut:
        with transaction_session(session_factory, RequestContext(user_account_id=user.account.id)) as session:
            roles = {item.organization_id: item.role for item in session.scalars(select(OrganizationMembership).where(OrganizationMembership.user_account_id == user.account.id)).all()}
            return ScopeOut(organizations=[OrganizationOut(id=item.id, name=item.name, role=roles[item.id]) for item in administered_organizations(session, user.account.id)])

    @router.get("/export")
    def export(request: Request, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> StreamingResponse:
        with transaction_session(session_factory, RequestContext(user_account_id=user.account.id)) as session:
            organizations = administered_organizations(session, user.account.id)
            if not organizations:
                raise HTTPException(status_code=403, detail="owner or admin role required")
            ids = [item.id for item in organizations]
            require_transfer_quota(session, user.account.id, ids)
            exported_at = session.scalar(select(func.now()))
            request_id = _request_id(request)
            for organization in organizations:
                apply_request_context(session, RequestContext(user_account_id=user.account.id, organization_id=organization.id))
                record_audit_event(session, AuditEventDraft(action=EXPORT_ACTION, target_type="organization", target_id=organization.id, request_id=request_id, change_summary={"format": FORMAT, "organizations": len(ids)}))
                session.flush()
            apply_request_context(session, RequestContext(user_account_id=user.account.id))
        name = file_name("yearclock", f"data-{exported_at.date().isoformat()}", "csv")

        def stream() -> Iterator[bytes]:
            buffer = io.StringIO()
            writer = csv.writer(buffer, lineterminator="\r\n")
            yield "﻿".encode()
            yield _line(writer, buffer, {"type": "type"} | {column: column for column in COLUMNS}).encode()
            yield _line(writer, buffer, {"type": "format", "id": FORMAT, "name": exported_at.isoformat()}).encode()
            for organization_id in ids:
                with transaction_session(session_factory, RequestContext(user_account_id=user.account.id, organization_id=organization_id)) as inner:
                    organization = inner.get(Organization, organization_id)
                    if organization is None:
                        continue
                    for row in organization_rows(inner, organization):
                        yield _line(writer, buffer, row).encode()

        return StreamingResponse(stream(), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="{name}"', "Cache-Control": "no-store"})

    @router.post("/import", response_model=TransferResult)
    def import_file(request: Request, dry_run: bool = Query(default=True), user: AuthenticatedUser = Depends(authenticated_user_dependency), body: bytes = Depends(transfer_body)) -> TransferResult:
        try:
            rows, exported_at = read_file(body)
        except TransferFileError as error:
            raise HTTPException(status_code=422, detail={"reason": error.reason, **error.detail}) from error
        import_id = uuid4()
        with transaction_session(session_factory, RequestContext(user_account_id=user.account.id)) as session:
            organizations = administered_organizations(session, user.account.id)
            if not organizations:
                raise HTTPException(status_code=403, detail="owner or admin role required")
            require_transfer_quota(session, user.account.id, [item.id for item in organizations])
            nested = session.begin_nested()
            try:
                summaries, issues = run_import(session, user.account.id, rows, exported_at, import_id)
            except IntegrityError as error:
                nested.rollback()
                raise HTTPException(status_code=422, detail={"reason": "id_conflict", "message": "an id in the file belongs to another Organization"}) from error
            commit = not dry_run and not issues
            if commit:
                nested.commit()
            else:
                nested.rollback()
            result = TransferResult(rows=len(rows), organizations=summaries, errors=sorted(issues, key=lambda item: item.row)[:1000], saved=commit, import_id=import_id if commit else None)
            request_id = _request_id(request)
            for summary in summaries:
                apply_request_context(session, RequestContext(user_account_id=user.account.id, organization_id=summary.id))
                record_audit_event(session, AuditEventDraft(action=IMPORT_ACTION if commit else PREVIEW_ACTION, target_type="organization", target_id=summary.id, request_id=request_id, change_summary={"format": FORMAT, "import_id": str(import_id), "errors": len(issues), "created": sum(item.created for item in summary.kinds.values()), "updated": sum(item.updated for item in summary.kinds.values()), "unchanged": sum(item.unchanged for item in summary.kinds.values())}))
                session.flush()
            apply_request_context(session, RequestContext(user_account_id=user.account.id))
        if not dry_run and issues:
            raise HTTPException(status_code=422, detail={"reason": "errors", "errors": [item.model_dump(mode="json") for item in result.errors]})
        return result

    return router
