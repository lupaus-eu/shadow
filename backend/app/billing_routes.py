import os
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.audit import AuditEventDraft, record_audit_event
from app.auth import AuthenticatedUser
from app.auth_routes import AuthenticatedUserDependency
from app.billing import StripeBilling
from app.database import RequestContext, apply_request_context, transaction_session
from app.models import Organization, OrganizationMembership, OrganizationRole, OrganizationStatus


class PortalResponse(BaseModel):
    url: str


def create_billing_router(*, session_factory: sessionmaker[Session], authenticated_user_dependency: AuthenticatedUserDependency, stripe_billing: StripeBilling) -> APIRouter:
    router = APIRouter(prefix="/api/v1/organizations/{organization_id}/billing", tags=["organization billing"])
    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:8173")

    @router.post("/portal", response_model=PortalResponse)
    def open_portal(organization_id: UUID, request: Request, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> PortalResponse:
        """Owners reach Stripe's Customer Portal even while the Organization is read-only."""
        with transaction_session(session_factory, RequestContext(user_account_id=user.account.id)) as session:
            membership = session.scalar(select(OrganizationMembership).where(OrganizationMembership.organization_id == organization_id, OrganizationMembership.user_account_id == user.account.id))
            if membership is None:
                raise HTTPException(status_code=404, detail="organization not found")
            if membership.role != OrganizationRole.OWNER.value:
                raise HTTPException(status_code=403, detail="Owner required")
            apply_request_context(session, RequestContext(user_account_id=user.account.id, organization_id=organization_id))
            organization = session.get(Organization, organization_id)
            if organization is None or organization.status not in {OrganizationStatus.ACTIVE.value, OrganizationStatus.PENDING_DELETION.value} or not organization.stripe_customer_id:
                raise HTTPException(status_code=409, detail="no Stripe customer for this Organization")
            portal = stripe_billing.create_portal_session(customer_id=organization.stripe_customer_id, return_url=f"{frontend_url.rstrip('/')}/organizations/{organization_id}")
            record_audit_event(session, AuditEventDraft(action="organization.billing_portal_opened", target_type="organization", target_id=organization.id, request_id=(request.headers.get("X-Request-ID") or str(uuid4()))[:120], change_summary={}))
            return PortalResponse(url=portal.url)

    return router
