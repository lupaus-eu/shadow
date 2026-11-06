"""Event history (Yearclock V2, P4 ticket 02).

History follows the Event list's read rule: everyone who may read the
Yearclock, and for Linked Lanes everyone who may read the source Yearclock.
Actor names are shown only while the actor is a member of the Organization.
"""
from datetime import date, datetime
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, sessionmaker

from app.auth import AuthenticatedUser
from app.auth_routes import AuthenticatedUserDependency
from app.audit import AuditEventDraft, record_audit_event
from app.event_labels import set_event_labels
from app.event_content import parse_time_text
from app.event_routes import EventResponse, _access_session, _response
from app.models import Category, Event, EventRevision, Label, Lane, OrganizationMembership, SeriesOccurrence, UserAccount
from app.revisions import SNAPSHOT_FIELDS, _normalize, set_revision_reason, snapshot_of
from app.yearclock_reading import readable_links

PAGE_SIZE = 50
# Long text is only reported as changed, to keep each entry short.
SUMMARY_ONLY = {"description", "links"}


class HistoryActor(BaseModel):
    kind: str
    name: str | None = None


class HistoryChange(BaseModel):
    field: str
    before: Any = None
    after: Any = None


class HistoryItem(BaseModel):
    id: UUID
    kind: str
    reason: str
    reason_detail: dict[str, Any]
    actor: HistoryActor
    changes: list[HistoryChange]
    created_at: datetime


class HistoryPage(BaseModel):
    items: list[HistoryItem]
    next_offset: int | None


class ChangeItem(BaseModel):
    event_id: UUID | None = None
    series_id: UUID | None = None
    title: str
    kind: str
    at: datetime
    actor: HistoryActor
    count: int = 1


class ChangesPage(BaseModel):
    items: list[ChangeItem]
    total: int
    more: bool
    latest_at: datetime | None


class RestorePreview(BaseModel):
    changes: list[HistoryChange]
    # Removed items cannot be restored; their names are no longer known.
    category_removed: bool = False
    labels_removed: int = 0
    lane_missing: bool = False


class RestoreRequest(BaseModel):
    expected_version: int = Field(ge=1)
    lane_id: UUID | None = None


class RestorePlan(BaseModel):
    values: dict[str, Any]
    label_ids: list[UUID]
    preview: RestorePreview


def readable_event(session: Session, organization_id: UUID, yearclock_id: UUID, event_id: UUID, user_account_id: UUID) -> Event:
    """The Event if it belongs to this Yearclock or to a Source Lane the user may read through it."""
    event = session.get(Event, event_id)
    if event is None or event.organization_id != organization_id:
        raise HTTPException(status_code=404, detail="Event not found")
    if event.yearclock_id != yearclock_id and event.lane_id not in readable_links(session, organization_id, yearclock_id, user_account_id):
        raise HTTPException(status_code=404, detail="Event not found")
    return event


def create_history_router(*, session_factory: sessionmaker[Session], authenticated_user_dependency: AuthenticatedUserDependency) -> APIRouter:
    router = APIRouter(prefix="/api/v1/organizations", tags=["Event history"])

    @router.get("/{organization_id}/yearclocks/{yearclock_id}/events/{event_id}/history", response_model=HistoryPage)
    def history(organization_id: UUID, yearclock_id: UUID, event_id: UUID, offset: int = Query(default=0, ge=0), user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> HistoryPage:
        with _access_session(session_factory, organization_id, yearclock_id, user, mutate=False) as session:
            readable_event(session, organization_id, yearclock_id, event_id, user.account.id)
            # One extra row gives the "before" state of the page's oldest entry.
            rows = session.scalars(select(EventRevision).where(EventRevision.event_id == event_id).order_by(EventRevision.created_at.desc(), EventRevision.id.desc()).offset(offset).limit(PAGE_SIZE + 2)).all()
            page, more = rows[:PAGE_SIZE], len(rows) > PAGE_SIZE
            names = _names(session, organization_id, rows)
            items = [_item(row, rows[index + 1] if index + 1 < len(rows) else None, names) for index, row in enumerate(page)]
            return HistoryPage(items=items, next_offset=offset + PAGE_SIZE if more else None)

    @router.get("/{organization_id}/yearclocks/{yearclock_id}/changes", response_model=ChangesPage)
    def changes(organization_id: UUID, yearclock_id: UUID, since: datetime, limit: int = Query(default=200, ge=1, le=200), user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> ChangesPage:
        """What others changed since ``since``: one item per Event, a Series change once per Series (V2 P4)."""
        with _access_session(session_factory, organization_id, yearclock_id, user, mutate=False) as session:
            links = readable_links(session, organization_id, yearclock_id, user.account.id)
            mine = (EventRevision.actor_kind == "member") & (EventRevision.actor_account_id == user.account.id)
            rows = session.scalars(
                select(EventRevision).join(Event, Event.id == EventRevision.event_id)
                .where(or_(EventRevision.yearclock_id == yearclock_id, Event.lane_id.in_(links.keys())), EventRevision.created_at > since, EventRevision.reason != "series", ~mine)
                .order_by(EventRevision.created_at.desc(), EventRevision.id.desc())
            ).all()
            latest: dict[UUID, EventRevision] = {}
            created: set[UUID] = set()
            for row in rows:
                latest.setdefault(row.event_id, row)
                if row.kind == "created": created.add(row.event_id)
            names = _names(session, organization_id, list(latest.values()))
            items: list[ChangeItem] = []
            series_items: dict[UUID, ChangeItem] = {}
            for event_id, row in latest.items():
                actor = _item(row, None, names).actor
                if row.reason == "series_changed" and row.series_id and event_id not in created:
                    grouped = series_items.get(row.series_id)
                    if grouped: grouped.count += 1; continue
                    series_items[row.series_id] = ChangeItem(series_id=row.series_id, title=row.snapshot.get("title", ""), kind="series_changed", at=row.created_at, actor=actor)
                    items.append(series_items[row.series_id]); continue
                kind = "deleted" if row.snapshot.get("deleted") else "new" if event_id in created else "changed"
                items.append(ChangeItem(event_id=event_id, series_id=row.series_id, title=row.snapshot.get("title", ""), kind=kind, at=row.created_at, actor=actor))
            return ChangesPage(items=items[:limit], total=len(items), more=len(items) > limit, latest_at=rows[0].created_at if rows else None)

    @router.get("/{organization_id}/yearclocks/{yearclock_id}/events/{event_id}/history/{revision_id}/restore-preview", response_model=RestorePreview)
    def restore_preview(organization_id: UUID, yearclock_id: UUID, event_id: UUID, revision_id: UUID, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> RestorePreview:
        with _access_session(session_factory, organization_id, yearclock_id, user, mutate=True) as session:
            event, revision = _restorable(session, organization_id, yearclock_id, event_id, revision_id, user.account.id)
            return _plan(session, organization_id, yearclock_id, event, revision, None).preview

    @router.post("/{organization_id}/yearclocks/{yearclock_id}/events/{event_id}/history/{revision_id}/restore", response_model=EventResponse)
    def restore(organization_id: UUID, yearclock_id: UUID, event_id: UUID, revision_id: UUID, body: RestoreRequest, request: Request, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> EventResponse:
        """Return an Event to an earlier version; the result is a new version (V2 P4)."""
        with _access_session(session_factory, organization_id, yearclock_id, user, mutate=True) as session:
            event, revision = _restorable(session, organization_id, yearclock_id, event_id, revision_id, user.account.id)
            if body.expected_version != event.version: raise HTTPException(status_code=409, detail={"latest_version": event.version})
            plan = _plan(session, organization_id, yearclock_id, event, revision, body.lane_id)
            if plan.preview.lane_missing and body.lane_id is None: raise HTTPException(status_code=422, detail={"reason": "lane_required"})
            set_revision_reason(session, "restore", {"revision_at": revision.created_at.isoformat()})
            for field, value in plan.values.items(): setattr(event, field, value)
            set_event_labels(session, event, session.scalars(select(Label).where(Label.id.in_(plan.label_ids))).all())
            event.version += 1
            record_audit_event(session, AuditEventDraft(action="event.version_restored", target_type="event", target_id=event.id, request_id=(request.headers.get("X-Request-ID") or str(uuid4()))[:120], change_summary={"title": event.title, "revision_at": revision.created_at.isoformat(), "fields": [change.field for change in plan.preview.changes]}))
            session.flush()
            return _response(event)

    return router


def _names(session: Session, organization_id: UUID, rows: list[EventRevision]) -> dict[str, dict]:
    lanes, categories, labels, accounts = set(), set(), set(), set()
    for row in rows:
        snapshot = row.snapshot
        lanes.add(snapshot.get("lane_id"))
        categories.add(snapshot.get("category_id"))
        labels.update(snapshot.get("label_ids") or [])
        if row.actor_account_id:
            accounts.add(row.actor_account_id)
    ids = lambda values: [UUID(value) for value in values if value]
    members = set(session.scalars(select(OrganizationMembership.user_account_id).where(OrganizationMembership.organization_id == organization_id, OrganizationMembership.user_account_id.in_(accounts))).all()) if accounts else set()
    return {
        "lane": {str(key): name for key, name in session.execute(select(Lane.id, Lane.name).where(Lane.id.in_(ids(lanes)))).all()},
        "category": {str(key): name for key, name in session.execute(select(Category.id, Category.name).where(Category.id.in_(ids(categories)))).all()},
        "label": {str(key): name for key, name in session.execute(select(Label.id, Label.name).where(Label.id.in_(ids(labels)))).all()},
        "actor": {key: name for key, name in session.execute(select(UserAccount.id, UserAccount.display_name).where(UserAccount.id.in_(members))).all()} if members else {},
    }


def _display(field: str, value: Any, names: dict[str, dict]) -> Any:
    """Readable values: names for references (None when the item no longer exists)."""
    if field == "lane_id":
        return {"id": value, "name": names["lane"].get(value)} if value else None
    if field == "category_id":
        return {"id": value, "name": names["category"].get(value)} if value else None
    if field == "label_ids":
        return [{"id": item, "name": names["label"].get(item)} for item in value or []]
    return value


def _item(row: EventRevision, previous: EventRevision | None, names: dict[str, dict]) -> HistoryItem:
    after = _normalize(row.snapshot)
    before = _normalize(previous.snapshot) if previous else None
    fields = [field for field in SNAPSHOT_FIELDS if before is not None and before[field] != after[field]] if before else []
    changes = [HistoryChange(field=field) if field in SUMMARY_ONLY else HistoryChange(field=field, before=_display(field, before[field], names), after=_display(field, after[field], names)) for field in fields]
    if row.actor_kind == "member":
        actor = HistoryActor(kind="member", name=names["actor"].get(row.actor_account_id))
    else:
        actor = HistoryActor(kind=row.actor_kind)
    return HistoryItem(id=row.id, kind=row.kind, reason=row.reason, reason_detail=row.reason_detail or {}, actor=actor, changes=changes, created_at=row.created_at)


def _restorable(session: Session, organization_id: UUID, yearclock_id: UUID, event_id: UUID, revision_id: UUID, user_account_id: UUID) -> tuple[Event, EventRevision]:
    event = readable_event(session, organization_id, yearclock_id, event_id, user_account_id)
    session.refresh(event, with_for_update=True)
    if event.yearclock_id != yearclock_id: raise HTTPException(status_code=422, detail={"reason": "linked_event", "message": "restore it in its own Yearclock"})
    if session.scalar(select(SeriesOccurrence.id).where(SeriesOccurrence.event_id == event.id)) is not None:
        raise HTTPException(status_code=422, detail={"reason": "recurring_occurrence", "message": "use Restore Series values for an occurrence"})
    if event.deleted_at is not None: raise HTTPException(status_code=409, detail={"reason": "deleted", "message": "restore the deleted Event first"})
    revision = session.get(EventRevision, revision_id)
    if revision is None or revision.event_id != event.id: raise HTTPException(status_code=404, detail="Version not found")
    return event, revision


def _plan(session: Session, organization_id: UUID, yearclock_id: UUID, event: Event, revision: EventRevision, lane_choice: UUID | None) -> RestorePlan:
    """What restoring ``revision`` would write, leaving out references that no longer exist."""
    target = _normalize(revision.snapshot)
    lane_ok = lambda lane_id: lane_id and session.scalar(select(Lane.id).where(Lane.id == UUID(lane_id), Lane.yearclock_id == yearclock_id, Lane.source_lane_id.is_(None))) is not None
    lane_missing = not lane_ok(target["lane_id"])
    if lane_missing and lane_choice is not None:
        if not lane_ok(str(lane_choice)): raise HTTPException(status_code=422, detail="Lane does not belong to Yearclock")
        target["lane_id"] = str(lane_choice)
    category_removed = False
    if target["category_id"] and session.scalar(select(Category.id).where(Category.id == UUID(target["category_id"]), or_(Category.yearclock_id == yearclock_id, Category.yearclock_id.is_(None)))) is None:
        category_removed = True
        target["category_id"] = None
    existing = {str(item) for item in session.scalars(select(Label.id).where(Label.organization_id == organization_id, Label.id.in_([UUID(item) for item in target["label_ids"]]))).all()} if target["label_ids"] else set()
    missing_labels = [item for item in target["label_ids"] if item not in existing]
    target["label_ids"] = [item for item in target["label_ids"] if item in existing]
    current = _normalize(snapshot_of(session, [event])[event.id])
    fields = [field for field in SNAPSHOT_FIELDS if field not in {"deleted", "skipped"} and current[field] != target[field] and not (field == "lane_id" and lane_missing and lane_choice is None)]
    names = _names(session, organization_id, [_Fake(current), _Fake(target)])
    changes = [HistoryChange(field=field) if field in SUMMARY_ONLY else HistoryChange(field=field, before=_display(field, current[field], names), after=_display(field, target[field], names)) for field in fields]
    values = {
        "title": target["title"], "description": target["description"], "description_format": target["description_format"], "location": target["location"], "links": target["links"], "starts_at": parse_time_text(target["starts_at"]), "ends_at": parse_time_text(target["ends_at"]),
        "starts_on": date.fromisoformat(target["starts_on"]), "ends_on": date.fromisoformat(target["ends_on"]) if target["ends_on"] else None,
        "category_id": UUID(target["category_id"]) if target["category_id"] else None,
    }
    if not lane_missing or lane_choice is not None: values["lane_id"] = UUID(target["lane_id"])
    return RestorePlan(values=values, label_ids=[UUID(item) for item in target["label_ids"]], preview=RestorePreview(changes=changes, category_removed=category_removed, labels_removed=len(missing_labels), lane_missing=lane_missing))


class _Fake:
    """A snapshot in the shape ``_names`` reads."""
    def __init__(self, snapshot: dict[str, Any]) -> None:
        self.snapshot, self.actor_account_id = snapshot, None

