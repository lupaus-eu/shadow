from datetime import datetime, timezone
from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.limits import CATEGORIES, EVENTS, SERIES, require_lane_capacity, require_yearclock_capacity
from app.label_routes import LABEL_COLORS
from app.audit import AuditEventDraft, record_audit_event
from app.auth import AuthenticatedUser
from app.auth_routes import AuthenticatedUserDependency
from app.database import RequestContext, apply_request_context, transaction_session
from app.event_labels import event_label_ids, series_label_ids, set_series_labels
from app.models import Category, Event, EventLabel, EventSeries, Lane, Organization, OrganizationMembership, OrganizationRole, SeriesOccurrence, Yearclock
from app.recurrence import materialization_horizon, materialize_series
from app.access import is_manager, role_on
from app.revisions import set_revision_reason
from app.yearclock_reading import LinkSource, link_sources, readable_yearclock_ids
from app.lifecycle import content_retention
from app.subscription_access import require_organization_mutation_access


class StructureRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    expected_version: int | None = Field(default=None, ge=1)

    @field_validator("name")
    @classmethod
    def non_blank_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value

class OrderRequest(BaseModel):
    ordered_ids: list[UUID]
    expected_version: int = Field(ge=1)

class MoveLaneEventsRequest(BaseModel):
    target_lane_id: UUID
    expected_version: int = Field(ge=1)

class YearclockOrderRequest(BaseModel):
    ordered_ids: list[UUID]
    expected_versions: dict[UUID, int]

class LayoutRequest(BaseModel):
    """Shared Yearclock layout (Yearclock V2); absent fields keep their values."""

    expected_version: int = Field(ge=1)
    start_month: int | None = Field(default=None, ge=1, le=12)
    show_week_ring: bool | None = None
    show_quarter_ring: bool | None = None


class LayoutResponse(BaseModel):
    id: UUID; version: int; start_month: int; show_week_ring: bool = False; show_quarter_ring: bool = False


class LaneRequest(StructureRequest):
    """Lane rename and appearance (Yearclock V2); `tint: null` clears the tint, absent fields keep theirs."""

    tint: str | None = None
    height: Literal["normal", "tall"] | None = None

    @field_validator("tint")
    @classmethod
    def palette_tint(cls, value: str | None) -> str | None:
        if value is not None and value.lower() not in LABEL_COLORS:
            raise ValueError("tint must come from the palette")
        return value.lower() if value else None


class LaneResponse(BaseModel):
    id: UUID; name: str; display_order: int; version: int; tint: str | None = None; height: str = "normal"
    source_lane_id: UUID | None = None
    source: LinkSource | None = None

class LaneLinkRequest(BaseModel):
    source_lane_id: UUID

class LaneCopyRequest(BaseModel):
    source_lane_id: UUID
    include_events: bool = True

class LaneCopyResponse(BaseModel):
    lane: LaneResponse; events: int; series: int; categories_created: int

class MoveLaneEventsResponse(BaseModel):
    moved_events: int; moved_series: int; lane: LaneResponse; target_lane: LaneResponse

class YearclockResponse(BaseModel):
    id: UUID; name: str; display_order: int; version: int; archived_at: datetime | None; deleted_at: datetime | None = None; purge_after: datetime | None = None; lanes: list[LaneResponse]
    organization_access: str = "none"


def create_yearclock_router(*, session_factory: sessionmaker[Session], authenticated_user_dependency: AuthenticatedUserDependency) -> APIRouter:
    router = APIRouter(prefix="/api/v1/organizations", tags=["Yearclock structure"])

    @router.get("/{organization_id}/yearclocks", response_model=list[YearclockResponse])
    def list_yearclocks(organization_id: UUID, include_archived: bool = False, include_deleted: bool = False, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> list[YearclockResponse]:
        with _session(session_factory, organization_id, user, mutate=False) as session:
            stmt = select(Yearclock).where(Yearclock.organization_id == organization_id)
            if not include_archived: stmt = stmt.where(Yearclock.archived_at.is_(None))
            if not include_deleted: stmt = stmt.where(Yearclock.deleted_at.is_(None))
            return [_response(session, item) for item in session.scalars(stmt.order_by(Yearclock.display_order)).all()]

    @router.post("/{organization_id}/yearclocks", response_model=YearclockResponse, status_code=201)
    def create(organization_id: UUID, body: StructureRequest, request: Request, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> YearclockResponse:
        with _session(session_factory, organization_id, user) as session:
            require_yearclock_capacity(session, organization_id)
            clock = Yearclock(id=uuid4(), organization_id=organization_id, name=body.name.strip(), display_order=session.scalar(select(func.count()).select_from(Yearclock).where(Yearclock.organization_id == organization_id)) or 0, version=1, archived_at=None)
            session.add(clock)
            session.flush()
            lane = Lane(id=uuid4(), organization_id=organization_id, yearclock_id=clock.id, name="General", display_order=0, version=1)
            session.add(lane); session.flush(); _audit(session, request, "yearclock.created", clock.id, {"name": clock.name})
            return _response(session, clock)

    @router.patch("/{organization_id}/yearclocks/{yearclock_id}", response_model=YearclockResponse)
    def update(organization_id: UUID, yearclock_id: UUID, body: StructureRequest, request: Request, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> YearclockResponse:
        with _session(session_factory, organization_id, user) as session:
            clock = _clock(session, organization_id, yearclock_id)
            _version(clock.version, body.expected_version); clock.name = body.name.strip(); clock.version += 1; _audit(session, request, "yearclock.renamed", clock.id, {"name": clock.name}); return _response(session, clock)

    @router.post("/{organization_id}/yearclocks/{yearclock_id}/archive", response_model=YearclockResponse)
    def archive(organization_id: UUID, yearclock_id: UUID, body: StructureRequest, request: Request, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> YearclockResponse:
        with _session(session_factory, organization_id, user) as session:
            clock = _clock(session, organization_id, yearclock_id); _version(clock.version, body.expected_version); clock.archived_at = datetime.now(timezone.utc); clock.version += 1; _audit(session, request, "yearclock.archived", clock.id, {}); return _response(session, clock)

    @router.post("/{organization_id}/yearclocks/{yearclock_id}/restore", response_model=YearclockResponse)
    def restore(organization_id: UUID, yearclock_id: UUID, body: StructureRequest, request: Request, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> YearclockResponse:
        with _session(session_factory, organization_id, user) as session:
            clock = _clock(session, organization_id, yearclock_id); _version(clock.version, body.expected_version); clock.archived_at = None; clock.version += 1; _audit(session, request, "yearclock.restored", clock.id, {}); return _response(session, clock)

    @router.delete("/{organization_id}/yearclocks/{yearclock_id}", status_code=204)
    def delete_yearclock(organization_id: UUID, yearclock_id: UUID, request: Request, expected_version: int = Query(ge=1), user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> None:
        """Recoverably delete a Yearclock with all its content for the retention period."""
        with _session(session_factory, organization_id, user) as session:
            clock = _clock(session, organization_id, yearclock_id); _version(clock.version, expected_version)
            clock.deleted_at = datetime.now(timezone.utc); clock.version += 1
            _audit(session, request, "yearclock.deleted", clock.id, {"name": clock.name})

    @router.post("/{organization_id}/yearclocks/{yearclock_id}/recover", response_model=YearclockResponse)
    def recover_yearclock(organization_id: UUID, yearclock_id: UUID, request: Request, expected_version: int = Query(ge=1), user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> YearclockResponse:
        with _session(session_factory, organization_id, user) as session:
            clock = _clock(session, organization_id, yearclock_id, include_deleted=True); _version(clock.version, expected_version)
            if clock.deleted_at is None: raise HTTPException(status_code=409, detail={"reason": "not_deleted"})
            clock.deleted_at = None; clock.version += 1
            _audit(session, request, "yearclock.recovered", clock.id, {"name": clock.name})
            return _response(session, clock)

    @router.patch("/{organization_id}/yearclocks/{yearclock_id}/layout", response_model=LayoutResponse)
    def update_layout(organization_id: UUID, yearclock_id: UUID, body: LayoutRequest, request: Request, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> LayoutResponse:
        with _lane_editor_session(session_factory, organization_id, yearclock_id, user) as session:
            clock = _clock(session, organization_id, yearclock_id)
            _version(clock.version, body.expected_version)
            changes = {field: getattr(body, field) for field in body.model_fields_set if field != "expected_version" and getattr(body, field) is not None and getattr(clock, field) != getattr(body, field)}
            for field, value in changes.items():
                setattr(clock, field, value)
            if changes:
                clock.version += 1
                _audit(session, request, "yearclock.layout_changed", clock.id, changes)
            return _layout_response(clock)

    @router.post("/{organization_id}/yearclocks/{yearclock_id}/lanes", response_model=LaneResponse, status_code=201)
    def create_lane(organization_id: UUID, yearclock_id: UUID, body: StructureRequest, request: Request, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> LaneResponse:
        with _lane_editor_session(session_factory, organization_id, yearclock_id, user) as session:
            _clock(session, organization_id, yearclock_id)
            require_lane_capacity(session, yearclock_id)
            order = session.scalar(select(func.count()).select_from(Lane).where(Lane.yearclock_id == yearclock_id)) or 0
            lane = Lane(id=uuid4(), organization_id=organization_id, yearclock_id=yearclock_id, name=body.name, display_order=order, version=1)
            session.add(lane); _audit(session, request, "lane.created", lane.id, {"name": lane.name}); return _lane_response(lane)

    @router.post("/{organization_id}/yearclocks/{yearclock_id}/lanes/copy", response_model=LaneCopyResponse, status_code=201)
    def copy_lane(organization_id: UUID, yearclock_id: UUID, body: LaneCopyRequest, request: Request, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> LaneCopyResponse:
        """Copy a readable Lane, optionally with its single Events and Series, into this Yearclock (V2 P3)."""
        with _lane_editor_session(session_factory, organization_id, yearclock_id, user) as session:
            _clock(session, organization_id, yearclock_id)
            source = session.scalar(select(Lane).where(Lane.id == body.source_lane_id, Lane.organization_id == organization_id))
            if source is not None and source.source_lane_id is not None and source.yearclock_id in readable_yearclock_ids(session, organization_id, user.account.id):
                source = session.get(Lane, source.source_lane_id)
            if source is None or source.yearclock_id not in readable_yearclock_ids(session, organization_id, user.account.id):
                raise HTTPException(status_code=404, detail="Source Lane not found")
            require_lane_capacity(session, yearclock_id)
            recurring = select(SeriesOccurrence.event_id)
            events = session.scalars(select(Event).where(Event.lane_id == source.id, Event.deleted_at.is_(None), Event.id.not_in(recurring)).order_by(Event.starts_on, Event.id)).all() if body.include_events else []
            series = session.scalars(select(EventSeries).where(EventSeries.lane_id == source.id).order_by(EventSeries.starts_on, EventSeries.id)).all() if body.include_events else []
            used = {item.category_id for item in [*events, *series] if item.category_id}
            source_categories = session.scalars(select(Category).where(Category.id.in_(used))).all() if used else []
            own = {name.lower(): category_id for category_id, name in session.execute(select(Category.id, Category.name).where(Category.yearclock_id == yearclock_id)).all()}
            mapping: dict[UUID, UUID] = {}
            missing = []
            for category in source_categories:
                if category.yearclock_id is None or category.yearclock_id == yearclock_id: mapping[category.id] = category.id
                elif category.name.lower() in own: mapping[category.id] = own[category.name.lower()]
                else: missing.append(category)
            unique_missing = list({category.name.lower(): category for category in missing}.values())
            counts = {
                CATEGORIES: (session.scalar(select(func.count()).select_from(Category).where(Category.yearclock_id == yearclock_id)) or 0) + len(unique_missing),
                EVENTS: (session.scalar(select(func.count()).select_from(Event).where(Event.yearclock_id == yearclock_id, Event.deleted_at.is_(None))) or 0) + len(events),
                SERIES: (session.scalar(select(func.count()).select_from(EventSeries).where(EventSeries.yearclock_id == yearclock_id)) or 0) + len(series),
            }
            for ceiling, count in counts.items():
                if count > ceiling.maximum: raise HTTPException(status_code=409, detail={"reason": "limit_reached", "limit": ceiling.name, "maximum": ceiling.maximum})
            order = session.scalar(select(func.count()).select_from(Lane).where(Lane.yearclock_id == yearclock_id)) or 0
            lane = Lane(id=uuid4(), organization_id=organization_id, yearclock_id=yearclock_id, name=source.name, display_order=order, version=1, tint=source.tint, height=source.height or "normal")
            session.add(lane)
            category_order = session.scalar(select(func.count()).select_from(Category).where(Category.yearclock_id == yearclock_id)) or 0
            created_by_name: dict[str, UUID] = {}
            for category in missing:
                key = category.name.lower()
                if key not in created_by_name:
                    created = Category(id=uuid4(), organization_id=organization_id, yearclock_id=yearclock_id, name=category.name, color=category.color, display_order=category_order, version=1)
                    session.add(created); category_order += 1; created_by_name[key] = created.id
                mapping[category.id] = created_by_name[key]
            session.flush()
            labels = event_label_ids(session, [event.id for event in events])
            source_clock = session.get(Yearclock, source.yearclock_id)
            set_revision_reason(session, "lane_copy", {"yearclock_name": source_clock.name if source_clock else None})
            for event in events:
                copy = Event(id=uuid4(), organization_id=organization_id, yearclock_id=yearclock_id, lane_id=lane.id, category_id=mapping.get(event.category_id) if event.category_id else None, title=event.title, description=event.description, description_format=event.description_format, location=event.location, links=list(event.links or []), starts_at=event.starts_at, ends_at=event.ends_at, starts_on=event.starts_on, ends_on=event.ends_on, version=1)
                session.add(copy); session.flush()
                for label_id in labels.get(event.id, []): session.add(EventLabel(event_id=copy.id, label_id=label_id, organization_id=organization_id))
            organization = session.get(Organization, organization_id)
            for item in series:
                copy = EventSeries(id=uuid4(), organization_id=organization_id, yearclock_id=yearclock_id, lane_id=lane.id, category_id=mapping.get(item.category_id) if item.category_id else None, title=item.title, description=item.description, description_format=item.description_format, location=item.location, links=list(item.links or []), starts_at=item.starts_at, ends_at=item.ends_at, starts_on=item.starts_on, effective_from=item.effective_from, frequency=item.frequency, interval=item.interval, until=item.until, occurrence_count=item.occurrence_count, last_day=item.last_day, version=1)
                session.add(copy); session.flush()
                set_series_labels(session, copy, series_label_ids(session, item.id))
                materialize_series(session, copy, through=materialization_horizon(organization.time_zone), reason="lane_copy")
            _audit(session, request, "lane.copied", lane.id, {"name": lane.name, "source_yearclock_id": str(source.yearclock_id), "source_lane_id": str(source.id), "events": len(events), "series": len(series), "categories_created": sorted(category.name for category in unique_missing)})
            session.flush()
            return LaneCopyResponse(lane=_lane_response(lane), events=len(events), series=len(series), categories_created=len(unique_missing))

    @router.post("/{organization_id}/yearclocks/{yearclock_id}/lanes/link", response_model=LaneResponse, status_code=201)
    def link_lane(organization_id: UUID, yearclock_id: UUID, body: LaneLinkRequest, request: Request, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> LaneResponse:
        """Show another Yearclock's own Lane here, live and read only (V2 P3 Linked Lane)."""
        with _lane_editor_session(session_factory, organization_id, yearclock_id, user) as session:
            clock = _clock(session, organization_id, yearclock_id)
            source = session.scalar(select(Lane).where(Lane.id == body.source_lane_id, Lane.organization_id == organization_id))
            if source is None or source.yearclock_id not in readable_yearclock_ids(session, organization_id, user.account.id):
                raise HTTPException(status_code=404, detail="Source Lane not found")
            if source.yearclock_id == yearclock_id: raise HTTPException(status_code=422, detail={"reason": "same_yearclock"})
            if source.source_lane_id is not None: raise HTTPException(status_code=422, detail={"reason": "linked_source", "message": "a Linked Lane cannot be linked again"})
            if session.scalar(select(Lane.id).where(Lane.yearclock_id == yearclock_id, Lane.source_lane_id == source.id)) is not None:
                raise HTTPException(status_code=409, detail={"reason": "already_linked"})
            require_lane_capacity(session, yearclock_id)
            order = session.scalar(select(func.count()).select_from(Lane).where(Lane.yearclock_id == yearclock_id)) or 0
            lane = Lane(id=uuid4(), organization_id=organization_id, yearclock_id=yearclock_id, name=source.name, display_order=order, version=1, height="normal", source_lane_id=source.id)
            session.add(lane); clock.version += 1
            _audit(session, request, "lane.linked", lane.id, {"name": source.name, "yearclock_id": str(yearclock_id), "source_yearclock_id": str(source.yearclock_id), "source_lane_id": str(source.id)})
            _audit(session, request, "lane.linked_elsewhere", source.id, {"name": source.name, "yearclock_id": str(source.yearclock_id), "linked_into_yearclock_id": str(yearclock_id), "linked_into_yearclock_name": clock.name})
            session.flush()
            return _linked_response(session, lane, organization_id, user)

    @router.patch("/{organization_id}/yearclocks/{yearclock_id}/lanes/{lane_id}", response_model=LaneResponse)
    def rename_lane(organization_id: UUID, yearclock_id: UUID, lane_id: UUID, body: LaneRequest, request: Request, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> LaneResponse:
        with _lane_editor_session(session_factory, organization_id, yearclock_id, user) as session:
            lane = _lane(session, organization_id, yearclock_id, lane_id); _version(lane.version, body.expected_version)
            appearance = {field: getattr(body, field) for field in ("tint", "height") if field in body.model_fields_set and (field == "tint" or getattr(body, field) is not None) and getattr(lane, field) != getattr(body, field)}
            # A Linked Lane shows its source's name; only its appearance belongs to this Yearclock.
            renamed = lane.source_lane_id is None and lane.name != body.name
            if renamed: lane.name = body.name
            for field, value in appearance.items(): setattr(lane, field, value)
            lane.version += 1
            if renamed or (not appearance and lane.source_lane_id is None): _audit(session, request, "lane.renamed", lane.id, {"name": lane.name})
            if appearance: _audit(session, request, "lane.updated", lane.id, appearance)
            return _linked_response(session, lane, organization_id, user)

    @router.post("/{organization_id}/yearclocks/{yearclock_id}/lanes/{lane_id}/move-events", response_model=MoveLaneEventsResponse)
    def move_lane_events(organization_id: UUID, yearclock_id: UUID, lane_id: UUID, body: MoveLaneEventsRequest, request: Request, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> MoveLaneEventsResponse:
        """Explicitly move every Event and Series of a Lane, including recoverably deleted ones."""
        with _lane_editor_session(session_factory, organization_id, yearclock_id, user) as session:
            lane = _lane(session, organization_id, yearclock_id, lane_id); _version(lane.version, body.expected_version)
            if body.target_lane_id == lane_id: raise HTTPException(status_code=422, detail="target Lane must differ")
            target = _lane(session, organization_id, yearclock_id, body.target_lane_id)
            if target.source_lane_id is not None: raise HTTPException(status_code=422, detail={"reason": "linked_lane"})
            events = session.scalars(select(Event).where(Event.organization_id == organization_id, Event.lane_id == lane_id).with_for_update()).all()
            series = session.scalars(select(EventSeries).where(EventSeries.organization_id == organization_id, EventSeries.lane_id == lane_id).with_for_update()).all()
            set_revision_reason(session, "lane_moved", {"lane_name": lane.name})
            for event in events: event.lane_id = target.id; event.version += 1
            for item in series: item.lane_id = target.id
            lane.version += 1; target.version += 1
            _audit(session, request, "lane.events_moved", lane.id, {"target_lane_id": str(target.id), "events": len(events), "series": len(series)})
            return MoveLaneEventsResponse(moved_events=len(events), moved_series=len(series), lane=_lane_response(lane), target_lane=_lane_response(target))

    @router.delete("/{organization_id}/yearclocks/{yearclock_id}/lanes/{lane_id}", status_code=204)
    def delete_lane(organization_id: UUID, yearclock_id: UUID, lane_id: UUID, request: Request, expected_version: int = Query(ge=1), user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> None:
        with _lane_editor_session(session_factory, organization_id, yearclock_id, user) as session:
            clock = _clock(session, organization_id, yearclock_id)
            lane = _lane(session, organization_id, yearclock_id, lane_id); _version(lane.version, expected_version)
            if (session.scalar(select(func.count()).select_from(Lane).where(Lane.yearclock_id == yearclock_id)) or 0) <= 1:
                raise HTTPException(status_code=409, detail={"reason": "last_lane"})
            if lane.source_lane_id is None:
                events = session.scalar(select(func.count()).select_from(Event).where(Event.organization_id == organization_id, Event.lane_id == lane_id)) or 0
                series = session.scalar(select(func.count()).select_from(EventSeries).where(EventSeries.organization_id == organization_id, EventSeries.lane_id == lane_id)) or 0
                if events or series:
                    raise HTTPException(status_code=409, detail={"reason": "lane_has_events", "events": events, "series": series})
            else:
                source = session.get(Lane, lane.source_lane_id)
                _audit(session, request, "lane.unlinked", lane.id, {"name": lane.name, "yearclock_id": str(yearclock_id), "source_lane_id": str(lane.source_lane_id)})
                if source is not None: _audit(session, request, "lane.unlinked_elsewhere", source.id, {"name": source.name, "yearclock_id": str(source.yearclock_id), "unlinked_from_yearclock_id": str(yearclock_id), "unlinked_from_yearclock_name": clock.name})
            session.delete(lane); session.flush()
            for index, remaining in enumerate(session.scalars(select(Lane).where(Lane.yearclock_id == yearclock_id).order_by(Lane.display_order, Lane.id)).all()):
                if remaining.display_order != index: remaining.display_order = index; remaining.version += 1
            clock.version += 1
            if lane.source_lane_id is None: _audit(session, request, "lane.removed", lane.id, {"name": lane.name})

    @router.put("/{organization_id}/yearclocks/{yearclock_id}/lanes/order", response_model=list[LaneResponse])
    def reorder_lanes(organization_id: UUID, yearclock_id: UUID, body: OrderRequest, request: Request, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> list[LaneResponse]:
        with _lane_editor_session(session_factory, organization_id, yearclock_id, user) as session:
            clock = _clock(session, organization_id, yearclock_id); _version(clock.version, body.expected_version)
            lanes = session.scalars(select(Lane).where(Lane.yearclock_id == yearclock_id).with_for_update()).all()
            if len(body.ordered_ids) != len(set(body.ordered_ids)) or set(body.ordered_ids) != {lane.id for lane in lanes}: raise HTTPException(status_code=422, detail="ordered_ids must contain every Lane once")
            by_id = {lane.id: lane for lane in lanes}
            for index, lane_id in enumerate(body.ordered_ids): by_id[lane_id].display_order = index; by_id[lane_id].version += 1
            clock.version += 1; _audit(session, request, "lane.reordered", clock.id, {}); return [_lane_response(by_id[item]) for item in body.ordered_ids]

    @router.put("/{organization_id}/yearclocks/order", response_model=list[YearclockResponse])
    def reorder_yearclocks(organization_id: UUID, body: YearclockOrderRequest, request: Request, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> list[YearclockResponse]:
        with _session(session_factory, organization_id, user) as session:
            clocks = session.scalars(select(Yearclock).where(Yearclock.organization_id == organization_id, Yearclock.archived_at.is_(None), Yearclock.deleted_at.is_(None)).with_for_update()).all()
            if len(body.ordered_ids) != len(set(body.ordered_ids)) or set(body.ordered_ids) != {clock.id for clock in clocks}: raise HTTPException(status_code=422, detail="ordered_ids must contain every active Yearclock once")
            by_id = {clock.id: clock for clock in clocks}
            stale = {str(clock.id): clock.version for clock in clocks if body.expected_versions.get(clock.id) != clock.version}
            if stale: raise HTTPException(status_code=409, detail={"latest_versions": stale})
            for index, clock_id in enumerate(body.ordered_ids): by_id[clock_id].display_order = index; by_id[clock_id].version += 1
            _audit(session, request, "yearclock.reordered", body.ordered_ids[0], {"ordered_ids": [str(item) for item in body.ordered_ids]}); return [_response(session, by_id[item]) for item in body.ordered_ids]

    return router

from contextlib import contextmanager
@contextmanager
def _session(factory: sessionmaker[Session], organization_id: UUID, user: AuthenticatedUser, *, mutate: bool = True):
    with transaction_session(factory, RequestContext(user_account_id=user.account.id)) as session:
        membership = session.scalar(select(OrganizationMembership).where(OrganizationMembership.organization_id == organization_id, OrganizationMembership.user_account_id == user.account.id))
        if membership is None or membership.role not in {OrganizationRole.OWNER.value, OrganizationRole.ADMIN.value}: raise HTTPException(status_code=403, detail="Yearclock management role required")
        apply_request_context(session, RequestContext(user_account_id=user.account.id, organization_id=organization_id));
        if mutate:
            require_organization_mutation_access(session, organization_id)
        yield session


@contextmanager
def _lane_editor_session(
    factory: sessionmaker[Session],
    organization_id: UUID,
    yearclock_id: UUID,
    user: AuthenticatedUser,
):
    with transaction_session(factory, RequestContext(user_account_id=user.account.id)) as session:
        membership = session.scalar(select(OrganizationMembership).where(OrganizationMembership.organization_id == organization_id, OrganizationMembership.user_account_id == user.account.id))
        if membership is None:
            raise HTTPException(status_code=403, detail="Yearclock Editor role required")
        apply_request_context(session, RequestContext(user_account_id=user.account.id, organization_id=organization_id))
        require_organization_mutation_access(session, organization_id)
        # Owners and Admins pass here; a missing or foreign Yearclock is then a 404 from _clock.
        if not is_manager(membership) and role_on(session, membership, yearclock_id, include_deleted=True) != "editor":
            raise HTTPException(status_code=403, detail="Yearclock Editor role required")
        yield session

def _clock(session: Session, organization_id: UUID, yearclock_id: UUID, *, include_deleted: bool = False) -> Yearclock:
    statement = select(Yearclock).where(Yearclock.id == yearclock_id, Yearclock.organization_id == organization_id)
    if not include_deleted: statement = statement.where(Yearclock.deleted_at.is_(None))
    item = session.scalar(statement.with_for_update())
    if item is None: raise HTTPException(status_code=404, detail="Yearclock not found")
    return item
def _layout_response(clock: Yearclock) -> LayoutResponse:
    return LayoutResponse(id=clock.id, version=clock.version, start_month=clock.start_month or 1, show_week_ring=bool(clock.show_week_ring), show_quarter_ring=bool(clock.show_quarter_ring))


def _version(actual: int, expected: int | None) -> None:
    if expected != actual: raise HTTPException(status_code=409, detail={"latest_version": actual})
def _response(session: Session, clock: Yearclock) -> YearclockResponse:
    lanes = session.scalars(select(Lane).where(Lane.yearclock_id == clock.id).order_by(Lane.display_order)).all()
    return YearclockResponse(id=clock.id, name=clock.name, display_order=clock.display_order, version=clock.version, archived_at=clock.archived_at, deleted_at=clock.deleted_at, purge_after=clock.deleted_at + content_retention() if clock.deleted_at else None, organization_access=clock.organization_access or "none", lanes=[LaneResponse(id=x.id, name=x.name, display_order=x.display_order, version=x.version) for x in lanes])
def _lane(session: Session, organization_id: UUID, yearclock_id: UUID, lane_id: UUID) -> Lane:
    lane = session.scalar(select(Lane).where(Lane.id == lane_id, Lane.organization_id == organization_id, Lane.yearclock_id == yearclock_id).with_for_update())
    if lane is None: raise HTTPException(status_code=404, detail="Lane not found")
    return lane
def _lane_response(lane: Lane, source: LinkSource | None = None) -> LaneResponse:
    return LaneResponse(id=lane.id, name=lane.name, display_order=lane.display_order, version=lane.version, tint=lane.tint, height=lane.height or "normal", source_lane_id=lane.source_lane_id, source=source)
def _linked_response(session: Session, lane: Lane, organization_id: UUID, user: AuthenticatedUser) -> LaneResponse:
    return _lane_response(lane, link_sources(session, organization_id, user.account.id, [lane]).get(lane.id))
def _audit(session: Session, request: Request, action: str, target_id: UUID, summary: dict) -> None:
    record_audit_event(session, AuditEventDraft(action=action, target_type="yearclock", target_id=target_id, request_id=(request.headers.get("X-Request-ID") or str(uuid4()))[:120], change_summary=summary))
