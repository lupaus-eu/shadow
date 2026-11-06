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

from app.audit import AuditEventDraft, record_audit_event
from app.auth import AuthenticatedUser
from app.auth_routes import AuthenticatedUserDependency
from app.database import RequestContext, apply_request_context, transaction_session
from app.notifications import SUPPORT_ACCESS_ENDED, SUPPORT_ACCESS_REQUESTED, notify_managers
from app.models import Organization, OrganizationMembership, OrganizationStatus, SupportAccessRequest, UserAccount
from app.platform_routes import SUPPORT_AGENT, require_role
from app.subscription_access import require_organization_mutation_access

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


def _support_response(session: Session, item: SupportAccessRequest) -> SupportResponse:
    requester = session.get(UserAccount, item.requested_by_user_account_id)
    return SupportResponse(
        id=item.id, organization_id=item.organization_id, case_reference=item.case_reference, scope=item.scope,
        status=item.status, requested_hours=item.requested_hours, requested_by=requester.display_name if requester else "Platform support",
        created_at=item.created_at, decided_at=item.decided_at, expires_at=item.expires_at,
    )


def _audit(session: Session, request: Request, action: str, target_id: UUID, summary: dict, *, target_type: str = "support_access_request") -> None:
    record_audit_event(session, AuditEventDraft(action=action, target_type=target_type, target_id=target_id, request_id=(request.headers.get("X-Request-ID") or str(uuid4()))[:120], change_summary=summary))
