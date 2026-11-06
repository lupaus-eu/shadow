"""Operator console API (ADR-0022): Platform Users only, no customer content."""

from dataclasses import asdict
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.audit import AuditEventDraft, record_audit_event
from app.auth import AuthenticatedUser, AuthSettings, Clock, OIDCClient, revoke_session
from app.auth_routes import AuthenticatedUserDependency
from app.database import RequestContext, apply_request_context, transaction_session
from app.models import BackgroundJob, Organization, OrganizationMembership, OutboxMessage, PlatformRole, QueueStatus, StripeWebhookEvent, Yearclock
from app.subscription_access import subscription_view

PLATFORM_ADMIN, SUPPORT_AGENT = "platform_admin", "support_agent"
JobKind = Literal["email", "job"]


class PlatformSession(BaseModel):
    id: UUID
    email: str
    display_name: str
    locale: str
    roles: list[str]


class PlatformSubscription(BaseModel):
    state: str
    writable: bool
    grace_expires_at: datetime | None
    cancel_at_period_end: bool
    current_period_end: datetime | None


class PlatformOrganization(BaseModel):
    id: UUID
    name: str
    status: str
    subscription_access_state: str
    subscription: PlatformSubscription
    purchased_seats: int
    members: int
    yearclocks: int
    activated_at: datetime | None
    deletion_requested_at: datetime | None
    mcp_enabled: bool = True
    mcp_platform_blocked: bool = False


class McpBlockRequest(BaseModel):
    blocked: bool


class QueueCounts(BaseModel):
    pending: int = 0
    processing: int = 0
    completed: int = 0
    failed: int = 0


class PlatformHealth(BaseModel):
    database: str
    email: QueueCounts
    jobs: dict[str, QueueCounts]
    webhooks: dict[str, int]
    organizations: dict[str, int]


class PlatformJob(BaseModel):
    kind: JobKind
    id: UUID
    type: str
    organization_id: UUID | None
    status: str
    attempts: int
    next_attempt_at: datetime | None
    last_error: str | None
    created_at: datetime


def platform_roles(session: Session, user: AuthenticatedUser) -> set[str]:
    return set(session.scalars(select(PlatformRole.role).where(PlatformRole.user_account_id == user.account.id)).all())


def require_role(session: Session, user: AuthenticatedUser, *roles: str) -> set[str]:
    held = platform_roles(session, user)
    if not held & set(roles):
        raise HTTPException(status_code=403, detail="platform role required")
    return held


def create_platform_router(*, session_factory: sessionmaker, platform_user_dependency: AuthenticatedUserDependency, oidc_client: OIDCClient, settings: AuthSettings, clock: Clock) -> APIRouter:
    router = APIRouter(prefix="/api/v1/platform", tags=["Platform operations"])

    @router.get("/session", response_model=PlatformSession)
    def session_info(user: AuthenticatedUser = Depends(platform_user_dependency)) -> PlatformSession:
        with transaction_session(session_factory, RequestContext(user_account_id=user.account.id)) as session:
            roles = sorted(platform_roles(session, user))
        return PlatformSession(id=user.account.id, email=user.account.email, display_name=user.account.display_name, locale=user.account.locale, roles=roles)

    @router.post("/logout")
    def logout(user: AuthenticatedUser = Depends(platform_user_dependency)) -> Response:
        id_token_hint = revoke_session(user, now=clock())
        response = RedirectResponse(oidc_client.end_session_url(post_logout_redirect_uri=f"{settings.frontend_url.rstrip('/')}/platform", id_token_hint=id_token_hint), status_code=303)
        response.delete_cookie(settings.session_cookie_name, path="/")
        return response

    @router.get("/organizations", response_model=list[PlatformOrganization])
    def organizations(user: AuthenticatedUser = Depends(platform_user_dependency)) -> list[PlatformOrganization]:
        with transaction_session(session_factory, RequestContext(user_account_id=user.account.id, worker_scope="enumerate")) as session:
            require_role(session, user, PLATFORM_ADMIN)
            organizations = session.scalars(select(Organization).order_by(Organization.created_at.desc())).all()
            result = []
            for organization in organizations:
                apply_request_context(session, RequestContext(user_account_id=user.account.id, organization_id=organization.id, worker_scope="enumerate"))
                members = session.scalar(select(func.count()).select_from(OrganizationMembership).where(OrganizationMembership.organization_id == organization.id)) or 0
                yearclocks = session.scalar(select(func.count()).select_from(Yearclock).where(Yearclock.organization_id == organization.id, Yearclock.deleted_at.is_(None))) or 0
                result.append(PlatformOrganization(
                    id=organization.id, name=organization.name, status=organization.status,
                    subscription_access_state=organization.subscription_access_state,
                    subscription=PlatformSubscription(**asdict(subscription_view(organization))),
                    purchased_seats=organization.purchased_seats, members=members, yearclocks=yearclocks,
                    activated_at=organization.activated_at, deletion_requested_at=organization.deletion_requested_at,
                    mcp_enabled=organization.mcp_enabled, mcp_platform_blocked=organization.mcp_platform_blocked,
                ))
            return result

    @router.patch("/organizations/{organization_id}/mcp-block", response_model=PlatformOrganization)
    def mcp_block(organization_id: UUID, body: McpBlockRequest, request: Request, user: AuthenticatedUser = Depends(platform_user_dependency)) -> PlatformOrganization:
        """Block or unblock MCP traffic for one Organization; its Owners and Admins cannot lift the block."""
        with transaction_session(session_factory, RequestContext(user_account_id=user.account.id)) as session:
            require_role(session, user, PLATFORM_ADMIN)
            apply_request_context(session, RequestContext(user_account_id=user.account.id, organization_id=organization_id))
            organization = session.get(Organization, organization_id, with_for_update=True)
            if organization is None:
                raise HTTPException(status_code=404, detail="organization not found")
            if organization.mcp_platform_blocked != body.blocked:
                organization.mcp_platform_blocked = body.blocked
                record_audit_event(session, AuditEventDraft(action="platform.mcp_blocked" if body.blocked else "platform.mcp_unblocked", target_type="organization", target_id=organization_id, request_id=(request.headers.get("X-Request-ID") or str(uuid4()))[:120], change_summary={}))
            members = session.scalar(select(func.count()).select_from(OrganizationMembership).where(OrganizationMembership.organization_id == organization_id)) or 0
            yearclocks = session.scalar(select(func.count()).select_from(Yearclock).where(Yearclock.organization_id == organization_id, Yearclock.deleted_at.is_(None))) or 0
            return PlatformOrganization(
                id=organization.id, name=organization.name, status=organization.status,
                subscription_access_state=organization.subscription_access_state,
                subscription=PlatformSubscription(**asdict(subscription_view(organization))),
                purchased_seats=organization.purchased_seats, members=members, yearclocks=yearclocks,
                activated_at=organization.activated_at, deletion_requested_at=organization.deletion_requested_at,
                mcp_enabled=organization.mcp_enabled, mcp_platform_blocked=organization.mcp_platform_blocked,
            )

    @router.get("/health", response_model=PlatformHealth)
    def health(user: AuthenticatedUser = Depends(platform_user_dependency)) -> PlatformHealth:
        with transaction_session(session_factory, RequestContext(user_account_id=user.account.id, worker_scope="enumerate")) as session:
            require_role(session, user, PLATFORM_ADMIN, SUPPORT_AGENT)
            email = QueueCounts(**{status: count for status, count in session.execute(select(OutboxMessage.status, func.count()).group_by(OutboxMessage.status)).all()})
            jobs: dict[str, QueueCounts] = {}
            for job_type, status, count in session.execute(select(BackgroundJob.job_type, BackgroundJob.status, func.count()).group_by(BackgroundJob.job_type, BackgroundJob.status)).all():
                setattr(jobs.setdefault(job_type, QueueCounts()), status, count)
            webhooks = {outcome: count for outcome, count in session.execute(select(StripeWebhookEvent.outcome, func.count()).group_by(StripeWebhookEvent.outcome)).all()}
            organizations = {status: count for status, count in session.execute(select(Organization.status, func.count()).group_by(Organization.status)).all()}
            return PlatformHealth(database="ready", email=email, jobs=jobs, webhooks=webhooks, organizations=organizations)

    @router.get("/jobs", response_model=list[PlatformJob])
    def jobs(status: str = "failed", user: AuthenticatedUser = Depends(platform_user_dependency)) -> list[PlatformJob]:
        if status not in {item.value for item in QueueStatus}:
            raise HTTPException(status_code=422, detail="unknown status")
        with transaction_session(session_factory, RequestContext(user_account_id=user.account.id)) as session:
            require_role(session, user, PLATFORM_ADMIN, SUPPORT_AGENT)
            emails = session.scalars(select(OutboxMessage).where(OutboxMessage.status == status).order_by(OutboxMessage.created_at.desc()).limit(200)).all()
            background = session.scalars(select(BackgroundJob).where(BackgroundJob.status == status).order_by(BackgroundJob.created_at.desc()).limit(200)).all()
            return [_job("email", item, item.topic) for item in emails] + [_job("job", item, item.job_type) for item in background]

    @router.post("/jobs/{kind}/{job_id}/replay", response_model=PlatformJob)
    def replay(kind: JobKind, job_id: UUID, request: Request, user: AuthenticatedUser = Depends(platform_user_dependency)) -> PlatformJob:
        """Return a failed job to the queue; replaying any other state is a no-op."""
        model = OutboxMessage if kind == "email" else BackgroundJob
        with transaction_session(session_factory, RequestContext(user_account_id=user.account.id)) as session:
            require_role(session, user, PLATFORM_ADMIN)
            item = session.get(model, job_id, with_for_update=True)
            if item is None:
                raise HTTPException(status_code=404, detail="job not found")
            job_type = item.topic if kind == "email" else item.job_type
            if item.status == QueueStatus.FAILED.value:
                item.status = QueueStatus.PENDING.value
                item.attempts = 0
                item.available_at = datetime.now(UTC)
                apply_request_context(session, RequestContext(user_account_id=user.account.id, organization_id=item.organization_id))
                record_audit_event(session, AuditEventDraft(action="platform.job_replayed", target_type=f"{kind}_job", target_id=item.id, request_id=(request.headers.get("X-Request-ID") or str(uuid4()))[:120], change_summary={"type": job_type, "previous_error": (item.last_error or "")[:200]}))
            return _job(kind, item, job_type)

    return router


def _job(kind: JobKind, item: OutboxMessage | BackgroundJob, job_type: str) -> PlatformJob:
    return PlatformJob(
        kind=kind, id=item.id, type=job_type, organization_id=item.organization_id, status=item.status,
        attempts=item.attempts, next_attempt_at=item.available_at if item.status == QueueStatus.PENDING.value else None,
        last_error=(item.last_error or None) and item.last_error[:300], created_at=item.created_at,
    )
