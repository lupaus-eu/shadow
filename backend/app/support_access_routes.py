"""Customer-approved Support Access (ADR-0020, ADR-0022).

Support Agents request and use access under ``/api/v1/platform/support-access``;
Organization Owners and Admins list, approve, reject, and revoke under the
customer Organization path. Using a grant sets ``support_access_id`` in the
request context, so PostgreSQL (migration 0027) refuses any row outside an
approved, unexpired grant of the matching scope, and every audit event records
the grant.
"""

from contextlib import contextmanager
from datetime import UTC, date, datetime, timedelta
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.limits import require_event_capacity
from app.audit import AuditEventDraft, record_audit_event
from app.auth import AuthenticatedUser
from app.auth_routes import AuthenticatedUserDependency
from app.database import RequestContext, apply_request_context, transaction_session
from app.event_labels import event_label_ids, resolve_labels, set_event_labels
from app.event_routes import EventRequest, EventResponse, _category, _event, _lane, _response
from app.notifications import SUPPORT_ACCESS_ENDED, SUPPORT_ACCESS_REQUESTED, notify_managers
from app.event_content import links_json
from app.models import Category, Event, Label, Lane, Organization, OrganizationMembership, OrganizationStatus, SeriesOccurrence, SupportAccessRequest, UserAccount, Yearclock
from app.planning_window import planning_window
from app.platform_routes import SUPPORT_AGENT, require_role
from app.subscription_access import require_organization_mutation_access
from app.time_zone import organization_today

MAX_SUPPORT_HOURS = 24


class SupportRequest(BaseModel):
    organization_id: UUID
    case_reference: str = Field(min_length=1, max_length=200)
    scope: str = "read"
    hours: int = Field(default=1, ge=1, le=MAX_SUPPORT_HOURS)

    @field_validator("case_reference")
    @classmethod
    def reference_not_blank(cls, value: str) -> str:
        if not (value := value.strip()):
            raise ValueError("must not be blank")
        return value

    @field_validator("scope")
    @classmethod
    def valid_scope(cls, value: str) -> str:
        if value not in {"read", "write"}:
            raise ValueError("scope must be read or write")
        return value


class ApprovalRequest(BaseModel):
    hours: int | None = Field(default=None, ge=1, le=MAX_SUPPORT_HOURS)


class SupportResponse(BaseModel):
    id: UUID
    organization_id: UUID
    case_reference: str
    scope: str
    status: str
    requested_hours: int
    requested_by: str
    created_at: datetime
    decided_at: datetime | None
    expires_at: datetime | None


class SupportLane(BaseModel):
    id: UUID
    name: str
    position: int


class SupportCategory(BaseModel):
    id: UUID
    name: str
    color: str | None


class SupportYearclock(BaseModel):
    id: UUID
    name: str
    lanes: list[SupportLane]
    categories: list[SupportCategory]
    labels: list[SupportCategory] = []


def create_support_access_router(*, session_factory: sessionmaker, authenticated_user_dependency: AuthenticatedUserDependency) -> APIRouter:
    """Customer side: Owners and Admins decide on requests for their Organization."""
    router = APIRouter(prefix="/api/v1/organizations", tags=["Support access"])

    @router.get("/{organization_id}/support-access", response_model=list[SupportResponse])
    def list_requests(organization_id: UUID, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> list[SupportResponse]:
        expire_due_grants(session_factory, organization_id)
        with _manager_session(session_factory, organization_id, user) as session:
            items = session.scalars(select(SupportAccessRequest).where(SupportAccessRequest.organization_id == organization_id).order_by(SupportAccessRequest.created_at.desc())).all()
            return [_support_response(session, item) for item in items]

    @router.post("/{organization_id}/support-access/{request_id}/approve", response_model=SupportResponse)
    def approve(organization_id: UUID, request_id: UUID, request: Request, body: ApprovalRequest | None = None, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> SupportResponse:
        with _manager_session(session_factory, organization_id, user) as session:
            item = _locked(session, organization_id, request_id)
            if item.status != "pending":
                raise HTTPException(status_code=409, detail="Support request is not pending")
            hours = item.requested_hours if body is None or body.hours is None else body.hours
            if hours > item.requested_hours:
                raise HTTPException(status_code=422, detail="Approval cannot exceed the requested duration")
            now = datetime.now(UTC)
            item.status, item.approved_by_user_account_id, item.decided_at = "approved", user.account.id, now
            item.expires_at = now + timedelta(hours=min(hours, MAX_SUPPORT_HOURS))
            _audit(session, request, "support_access.approved", item.id, {"scope": item.scope, "hours": hours, "case_reference": item.case_reference})
            return _support_response(session, item)

    @router.post("/{organization_id}/support-access/{request_id}/reject", response_model=SupportResponse)
    def reject(organization_id: UUID, request_id: UUID, request: Request, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> SupportResponse:
        with _manager_session(session_factory, organization_id, user) as session:
            item = _locked(session, organization_id, request_id)
            if item.status != "pending":
                raise HTTPException(status_code=409, detail="Support request is not pending")
            item.status, item.decided_at = "rejected", datetime.now(UTC)
            _audit(session, request, "support_access.rejected", item.id, {"case_reference": item.case_reference})
            return _support_response(session, item)

    @router.post("/{organization_id}/support-access/{request_id}/revoke", response_model=SupportResponse)
    def revoke(organization_id: UUID, request_id: UUID, request: Request, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> SupportResponse:
        expire_due_grants(session_factory, organization_id)
        with _manager_session(session_factory, organization_id, user) as session:
            item = _locked(session, organization_id, request_id)
            if item.status != "approved":
                raise HTTPException(status_code=409, detail="Support Access is not active")
            now = datetime.now(UTC)
            item.status, item.revoked_at, item.expires_at = "revoked", now, now
            _audit(session, request, "support_access.revoked", item.id, {"case_reference": item.case_reference})
            notify_managers(session, organization_id, SUPPORT_ACCESS_ENDED, {"case_reference": item.case_reference, "how": "revoked"}, actor_id=user.account.id)
            return _support_response(session, item)

    return router


def create_platform_support_access_router(*, session_factory: sessionmaker, platform_user_dependency: AuthenticatedUserDependency) -> APIRouter:
    """Platform side: Support Agents request grants and use approved ones."""
    router = APIRouter(prefix="/api/v1/platform/support-access", tags=["Support access"])

    @router.post("", response_model=SupportResponse, status_code=201)
    def request_access(body: SupportRequest, request: Request, user: AuthenticatedUser = Depends(platform_user_dependency)) -> SupportResponse:
        try:
            with transaction_session(session_factory, RequestContext(user_account_id=user.account.id)) as session:
                require_role(session, user, SUPPORT_AGENT)
                apply_request_context(session, RequestContext(user_account_id=user.account.id, organization_id=body.organization_id))
                organization = session.get(Organization, body.organization_id)
                if organization is None or organization.status != OrganizationStatus.ACTIVE.value:
                    raise HTTPException(status_code=404, detail="Organization not found")
                item = SupportAccessRequest(id=uuid4(), organization_id=body.organization_id, requested_by_user_account_id=user.account.id, case_reference=body.case_reference, scope=body.scope, requested_hours=body.hours, status="pending", created_at=datetime.now(UTC))
                session.add(item)
                session.flush()
                _audit(session, request, "support_access.requested", item.id, {"scope": item.scope, "hours": item.requested_hours, "case_reference": item.case_reference})
                notify_managers(session, body.organization_id, SUPPORT_ACCESS_REQUESTED, {"case_reference": item.case_reference, "scope": item.scope})
                return _support_response(session, item)
        except IntegrityError as error:
            raise HTTPException(status_code=404, detail="Organization not found") from error

    @router.get("", response_model=list[SupportResponse])
    def my_requests(user: AuthenticatedUser = Depends(platform_user_dependency)) -> list[SupportResponse]:
        with transaction_session(session_factory, RequestContext(user_account_id=user.account.id)) as session:
            require_role(session, user, SUPPORT_AGENT)
            organization_ids = set(session.scalars(select(SupportAccessRequest.organization_id).where(SupportAccessRequest.requested_by_user_account_id == user.account.id, SupportAccessRequest.status == "approved")).all())
        for organization_id in organization_ids:
            expire_due_grants(session_factory, organization_id)
        with transaction_session(session_factory, RequestContext(user_account_id=user.account.id)) as session:
            items = session.scalars(select(SupportAccessRequest).where(SupportAccessRequest.requested_by_user_account_id == user.account.id).order_by(SupportAccessRequest.created_at.desc())).all()
            return [_support_response(session, item) for item in items]

    @router.get("/{request_id}/yearclocks", response_model=list[SupportYearclock])
    def yearclocks(request_id: UUID, request: Request, user: AuthenticatedUser = Depends(platform_user_dependency)) -> list[SupportYearclock]:
        with _support_session(session_factory, request_id, user, write=False) as (session, grant):
            clocks = session.scalars(select(Yearclock).where(Yearclock.organization_id == grant.organization_id, Yearclock.deleted_at.is_(None)).order_by(Yearclock.display_order, Yearclock.id)).all()
            labels = [SupportCategory(id=item.id, name=item.name, color=item.color) for item in session.scalars(select(Label).where(Label.organization_id == grant.organization_id).order_by(func.lower(Label.name))).all()]
            result = [
                SupportYearclock(
                    id=clock.id,
                    name=clock.name,
                    lanes=[SupportLane(id=lane.id, name=lane.name, position=lane.display_order) for lane in session.scalars(select(Lane).where(Lane.yearclock_id == clock.id).order_by(Lane.display_order, Lane.id)).all()],
                    categories=[SupportCategory(id=item.id, name=item.name, color=item.color) for item in session.scalars(select(Category).where(or_(Category.yearclock_id == clock.id, Category.yearclock_id.is_(None))).order_by(Category.yearclock_id.is_not(None), Category.display_order, Category.id)).all()],
                    labels=labels,
                )
                for clock in clocks
            ]
            _audit(session, request, "support_access.content_read", grant.organization_id, {"resource": "yearclocks"}, target_type="organization")
            return result

    @router.get("/{request_id}/yearclocks/{yearclock_id}/events", response_model=list[EventResponse])
    def events(request_id: UUID, yearclock_id: UUID, request: Request, window_start: date | None = None, user: AuthenticatedUser = Depends(platform_user_dependency)) -> list[EventResponse]:
        with _support_session(session_factory, request_id, user, write=False) as (session, grant):
            _yearclock(session, grant.organization_id, yearclock_id)
            organization = session.get(Organization, grant.organization_id)
            start, end = planning_window(window_start, today=organization_today(organization.time_zone))
            items = session.scalars(select(Event).where(Event.yearclock_id == yearclock_id, Event.deleted_at.is_(None), Event.starts_on <= end, func.coalesce(Event.ends_on, Event.starts_on) >= start).order_by(Event.starts_on, Event.id)).all()
            occurrences = {item.event_id: item for item in session.scalars(select(SeriesOccurrence).where(SeriesOccurrence.event_id.in_([event.id for event in items]))).all()}
            _audit(session, request, "support_access.content_read", yearclock_id, {"resource": "events"}, target_type="yearclock")
            labels = event_label_ids(session, [item.id for item in items])
            return [_response(item, occurrences.get(item.id), labels.get(item.id, [])) for item in items if not (occurrences.get(item.id) and occurrences[item.id].skipped)]

    @router.post("/{request_id}/yearclocks/{yearclock_id}/events", response_model=EventResponse, status_code=201)
    def create_event(request_id: UUID, yearclock_id: UUID, body: EventRequest, request: Request, user: AuthenticatedUser = Depends(platform_user_dependency)) -> EventResponse:
        with _support_session(session_factory, request_id, user, write=True) as (session, grant):
            _yearclock(session, grant.organization_id, yearclock_id)
            _lane(session, grant.organization_id, yearclock_id, body.lane_id)
            _category(session, yearclock_id, body.category_id)
            labels = resolve_labels(session, grant.organization_id, body.label_ids or [])
            require_event_capacity(session, yearclock_id)
            event = Event(id=uuid4(), organization_id=grant.organization_id, yearclock_id=yearclock_id, lane_id=body.lane_id, category_id=body.category_id, title=body.title, description=body.description, description_format=body.description_format or "plain", location=body.location, links=links_json(body.links), starts_at=body.starts_at, ends_at=body.ends_at, starts_on=body.starts_on, ends_on=body.ends_on, version=1)
            session.add(event)
            set_event_labels(session, event, labels)
            _audit(session, request, "event.created", event.id, {"title": event.title, "labels": [label.name for label in labels]}, target_type="event")
            return _response(event)

    @router.patch("/{request_id}/yearclocks/{yearclock_id}/events/{event_id}", response_model=EventResponse)
    def update_event(request_id: UUID, yearclock_id: UUID, event_id: UUID, body: EventRequest, request: Request, user: AuthenticatedUser = Depends(platform_user_dependency)) -> EventResponse:
        with _support_session(session_factory, request_id, user, write=True) as (session, grant):
            _yearclock(session, grant.organization_id, yearclock_id)
            event = _event(session, yearclock_id, event_id)
            if session.scalar(select(SeriesOccurrence.id).where(SeriesOccurrence.event_id == event.id)) is not None:
                raise HTTPException(status_code=409, detail={"reason": "recurring_occurrence", "message": "Support Access edits single Events only"})
            if body.expected_version != event.version:
                raise HTTPException(status_code=409, detail={"latest_version": event.version})
            _lane(session, grant.organization_id, yearclock_id, body.lane_id)
            _category(session, yearclock_id, body.category_id)
            label_changes = set_event_labels(session, event, resolve_labels(session, grant.organization_id, body.label_ids)) if body.label_ids is not None else {}
            for name in ("lane_id", "category_id", "title", "description", "location", "starts_at", "ends_at", "starts_on", "ends_on"):
                setattr(event, name, getattr(body, name))
            event.links = links_json(body.links)
            if body.description_format: event.description_format = body.description_format
            event.version += 1
            _audit(session, request, "event.updated", event.id, {"title": event.title, **{key: value for key, value in label_changes.items() if value}}, target_type="event")
            return _response(event)

    return router


def expire_due_grants(session_factory: sessionmaker[Session], organization_id: UUID, *, now: datetime | None = None) -> int:
    """Mark approved grants past their expiry as expired and audit each one."""
    now = now or datetime.now(UTC)
    with transaction_session(session_factory, RequestContext(organization_id=organization_id)) as session:
        due = session.scalars(select(SupportAccessRequest).where(SupportAccessRequest.organization_id == organization_id, SupportAccessRequest.status == "approved", SupportAccessRequest.expires_at <= now).with_for_update(skip_locked=True)).all()
        for item in due:
            item.status = "expired"
            record_audit_event(session, AuditEventDraft(action="support_access.expired", target_type="support_access_request", target_id=item.id, request_id=f"expiry:{item.id}", change_summary={"case_reference": item.case_reference}))
            notify_managers(session, organization_id, SUPPORT_ACCESS_ENDED, {"case_reference": item.case_reference, "how": "expired"})
        return len(due)


def expire_support_access(session_factory: sessionmaker[Session], *, now: datetime | None = None) -> int:
    """Worker sweep: expire due grants in every active Organization."""
    with transaction_session(session_factory, RequestContext(worker_scope="enumerate")) as session:
        organization_ids = session.scalars(select(Organization.id).where(Organization.status == OrganizationStatus.ACTIVE.value)).all()
    return sum(expire_due_grants(session_factory, organization_id, now=now) for organization_id in organization_ids)


@contextmanager
def _manager_session(session_factory: sessionmaker, organization_id: UUID, user: AuthenticatedUser):
    with transaction_session(session_factory, RequestContext(user_account_id=user.account.id)) as session:
        membership = session.scalar(select(OrganizationMembership).where(OrganizationMembership.organization_id == organization_id, OrganizationMembership.user_account_id == user.account.id))
        if membership is None or membership.role not in {"owner", "admin"}:
            raise HTTPException(status_code=403, detail="Owner or Admin required")
        apply_request_context(session, RequestContext(user_account_id=user.account.id, organization_id=organization_id))
        yield session


@contextmanager
def _support_session(session_factory: sessionmaker, request_id: UUID, user: AuthenticatedUser, *, write: bool):
    """Open a transaction that carries the grant; refuse anything but an active grant of the right scope."""
    with transaction_session(session_factory, RequestContext(user_account_id=user.account.id)) as session:
        require_role(session, user, SUPPORT_AGENT)
        grant = session.scalar(select(SupportAccessRequest).where(SupportAccessRequest.id == request_id, SupportAccessRequest.requested_by_user_account_id == user.account.id))
        if grant is None:
            raise HTTPException(status_code=404, detail="Support Access not found")
        organization_id = grant.organization_id
    expire_due_grants(session_factory, organization_id)
    context = RequestContext(user_account_id=user.account.id, organization_id=organization_id, support_access_id=request_id)
    with transaction_session(session_factory, context) as session:
        grant = session.get(SupportAccessRequest, request_id)
        if grant is None or grant.status != "approved" or grant.expires_at is None or grant.expires_at <= datetime.now(UTC):
            raise HTTPException(status_code=403, detail="Support Access is not active")
        if write and grant.scope != "write":
            raise HTTPException(status_code=403, detail="Support Access is read-only")
        organization = session.get(Organization, organization_id)
        if organization is None or organization.status != OrganizationStatus.ACTIVE.value:
            raise HTTPException(status_code=403, detail="Support Access is not active")
        if write:
            require_organization_mutation_access(session, organization_id)
        yield session, grant


def _locked(session: Session, organization_id: UUID, request_id: UUID) -> SupportAccessRequest:
    item = session.scalar(select(SupportAccessRequest).where(SupportAccessRequest.id == request_id, SupportAccessRequest.organization_id == organization_id).with_for_update())
    if item is None:
        raise HTTPException(status_code=404, detail="Support request not found")
    return item


def _yearclock(session: Session, organization_id: UUID, yearclock_id: UUID) -> Yearclock:
    clock = session.scalar(select(Yearclock).where(Yearclock.id == yearclock_id, Yearclock.organization_id == organization_id, Yearclock.deleted_at.is_(None)))
    if clock is None:
        raise HTTPException(status_code=404, detail="Yearclock not found")
    return clock


def _support_response(session: Session, item: SupportAccessRequest) -> SupportResponse:
    requester = session.get(UserAccount, item.requested_by_user_account_id)
    return SupportResponse(
        id=item.id, organization_id=item.organization_id, case_reference=item.case_reference, scope=item.scope,
        status=item.status, requested_hours=item.requested_hours, requested_by=requester.display_name if requester else "Platform support",
        created_at=item.created_at, decided_at=item.decided_at, expires_at=item.expires_at,
    )


def _audit(session: Session, request: Request, action: str, target_id: UUID, summary: dict, *, target_type: str = "support_access_request") -> None:
    record_audit_event(session, AuditEventDraft(action=action, target_type=target_type, target_id=target_id, request_id=(request.headers.get("X-Request-ID") or str(uuid4()))[:120], change_summary=summary))
