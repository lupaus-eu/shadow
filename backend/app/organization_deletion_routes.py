"""Owner-controlled Organization deletion with a recovery window (ADR-0008).

Requesting deletion moves an active Organization to Pending Deletion, which
PostgreSQL treats as closed for content (migration 0028). An Owner can restore
it until ``purge_after``; the ``organization.purge`` job then purges it.
Billing is separate: deletion neither cancels nor changes the subscription, and
restoration returns exactly the subscription state that Stripe last reported.
"""

from contextlib import contextmanager
from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.audit import AuditEventDraft, record_audit_event
from app.auth import AuthenticatedUser
from app.auth_routes import AuthenticatedUserDependency
from app.database import RequestContext, apply_request_context, transaction_session
from app.lifecycle import organization_deletion_window, organization_purge_after
from app.notifications import DELETION_SCHEDULED, notify_managers
from app.models import Organization, OrganizationMembership, OrganizationRole, OrganizationStatus


class ConfirmDeletion(BaseModel):
    confirm: bool


class DeletionResponse(BaseModel):
    status: str
    deletion_requested_at: datetime | None
    purge_after: datetime | None


def create_organization_deletion_router(*, session_factory: sessionmaker, authenticated_user_dependency: AuthenticatedUserDependency) -> APIRouter:
    router = APIRouter(prefix="/api/v1/organizations", tags=["Organization deletion"])

    @router.get("/{organization_id}/deletion", response_model=DeletionResponse)
    def deletion_state(organization_id: UUID, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> DeletionResponse:
        with _owner_session(session_factory, organization_id, user) as (session, organization):
            return _response(organization)

    @router.post("/{organization_id}/deletion", response_model=DeletionResponse)
    def request_deletion(organization_id: UUID, body: ConfirmDeletion, request: Request, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> DeletionResponse:
        if not body.confirm:
            raise HTTPException(status_code=422, detail="explicit confirmation required")
        with _owner_session(session_factory, organization_id, user) as (session, organization):
            if organization.status != OrganizationStatus.ACTIVE.value:
                raise HTTPException(status_code=409, detail="Organization is not active")
            # Before the status changes: the Organization policy hides rows of an Organization that is no longer active.
            notify_managers(session, organization_id, DELETION_SCHEDULED, {"purge_after": (datetime.now(UTC) + organization_deletion_window()).isoformat()}, actor_id=user.account.id)
            organization.status = OrganizationStatus.PENDING_DELETION.value
            organization.deletion_requested_at = datetime.now(UTC)
            _audit(session, request, "organization.deletion_requested", organization, {"purge_after": organization_purge_after(organization).isoformat()})
            return _response(organization)

    @router.post("/{organization_id}/deletion/restore", response_model=DeletionResponse)
    def restore(organization_id: UUID, request: Request, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> DeletionResponse:
        with _owner_session(session_factory, organization_id, user) as (session, organization):
            purge_after = organization_purge_after(organization)
            if purge_after is None:
                raise HTTPException(status_code=409, detail="Organization is not pending deletion")
            if purge_after <= datetime.now(UTC):
                raise HTTPException(status_code=409, detail="The recovery window has ended")
            organization.status = OrganizationStatus.ACTIVE.value
            organization.deletion_requested_at = None
            _audit(session, request, "organization.deletion_restored", organization, {})
            return _response(organization)

    return router


@contextmanager
def _owner_session(session_factory: sessionmaker, organization_id: UUID, user: AuthenticatedUser):
    """Check Owner membership before entering the Organization context; Pending Deletion hides memberships inside it."""
    with transaction_session(session_factory, RequestContext(user_account_id=user.account.id)) as session:
        membership = session.scalar(select(OrganizationMembership).where(OrganizationMembership.organization_id == organization_id, OrganizationMembership.user_account_id == user.account.id))
        if membership is None or membership.role != OrganizationRole.OWNER.value:
            raise HTTPException(status_code=403, detail="Owner required")
        apply_request_context(session, RequestContext(user_account_id=user.account.id, organization_id=organization_id))
        organization = session.scalar(select(Organization).where(Organization.id == organization_id).with_for_update())
        if organization is None:
            raise HTTPException(status_code=404, detail="organization not found")
        yield session, organization


def _response(organization: Organization) -> DeletionResponse:
    return DeletionResponse(status=organization.status, deletion_requested_at=organization.deletion_requested_at, purge_after=organization_purge_after(organization))


def _audit(session: Session, request: Request, action: str, organization: Organization, summary: dict) -> None:
    record_audit_event(session, AuditEventDraft(action=action, target_type="organization", target_id=organization.id, request_id=(request.headers.get("X-Request-ID") or str(uuid4()))[:120], change_summary=summary))
