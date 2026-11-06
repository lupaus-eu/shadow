import os
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.auth import AuthenticatedUser
from app.auth_routes import AuthenticatedUserDependency
from app.database import RequestContext, apply_request_context, transaction_session
from app.invitations import (
    accept_invitation,
    create_invitation,
    expire_pending_invitations,
    hash_invitation_token,
    invitation_groups,
    resend_invitation,
    revoke_invitation,
)
from app.models import InvitationStatus, Organization, OrganizationInvitation, OrganizationMembership, OrganizationRole, OrganizationStatus, UserAccount
from app.subscription_access import require_organization_mutation_access


class InvitationRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    role: OrganizationRole = OrganizationRole.MEMBER
    # Groups the person joins on acceptance (Yearclock V2).
    group_ids: list[UUID] = []


BULK_LIMIT = 50


class BulkInvitationRequest(BaseModel):
    emails: list[str] = Field(min_length=1, max_length=BULK_LIMIT)
    role: OrganizationRole = OrganizationRole.MEMBER
    group_ids: list[UUID] = []
    dry_run: bool = True


class SkippedAddress(BaseModel):
    email: str
    reason: str


class BulkInvitationResponse(BaseModel):
    invite: list[str]
    skipped: list[SkippedAddress]
    seats_needed: int
    created: int = 0


class InvitationResponse(BaseModel):
    id: UUID
    email: str
    role: str
    status: str
    expires_at: datetime
    version: int


class AcceptInvitationRequest(BaseModel):
    token: str = Field(min_length=20, max_length=255)


def create_invitation_router(*, session_factory: sessionmaker[Session], authenticated_user_dependency: AuthenticatedUserDependency, clock) -> APIRouter:
    router = APIRouter(tags=["Organization invitations"])
    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:8173")

    @router.get(
        "/api/v1/organizations/{organization_id}/invitations",
        response_model=list[InvitationResponse],
    )
    def list_invitations(
        organization_id: UUID,
        request: Request,
        authenticated_user: AuthenticatedUser = Depends(authenticated_user_dependency),
    ) -> list[InvitationResponse]:
        with _manager_session(
            session_factory, organization_id, authenticated_user, mutate=False
        ) as (session, organization):
            expire_pending_invitations(
                session,
                organization=organization,
                now=clock(),
                request_id=_request_id(request),
            )
            invitations = session.scalars(
                select(OrganizationInvitation)
                .where(OrganizationInvitation.organization_id == organization.id)
                .order_by(OrganizationInvitation.created_at.desc())
            ).all()
            return [_response(invitation) for invitation in invitations]

    @router.post("/api/v1/organizations/{organization_id}/invitations", response_model=InvitationResponse, status_code=201)
    def invite(organization_id: UUID, body: InvitationRequest, request: Request, authenticated_user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> InvitationResponse:
        email = body.email.strip().lower()
        if "@" not in email or email.startswith("@") or email.endswith("@"):
            raise HTTPException(status_code=422, detail="invalid invitation email")
        with _manager_session(session_factory, organization_id, authenticated_user) as (session, organization):
            membership = session.scalar(
                select(OrganizationMembership).where(
                    OrganizationMembership.organization_id == organization_id,
                    OrganizationMembership.user_account_id == authenticated_user.account.id,
                )
            )
            if body.role == OrganizationRole.OWNER and (
                membership is None or membership.role != OrganizationRole.OWNER.value
            ):
                raise HTTPException(status_code=403, detail="only an Owner can invite another Owner")
            created = create_invitation(session, organization=organization, invited_by=authenticated_user.account.id, email=email, role=body.role.value, now=clock(), frontend_url=frontend_url, request_id=_request_id(request), group_ids=body.group_ids)
            return _response(created.invitation)

    @router.post("/api/v1/organizations/{organization_id}/invitations/bulk", response_model=BulkInvitationResponse)
    def invite_many(organization_id: UUID, body: BulkInvitationRequest, request: Request, authenticated_user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> BulkInvitationResponse:
        """Invite up to 50 people with one role and Groups; nothing is sent without enough seats (V2 P10a)."""
        with _manager_session(session_factory, organization_id, authenticated_user) as (session, organization):
            membership = session.scalar(select(OrganizationMembership).where(OrganizationMembership.organization_id == organization_id, OrganizationMembership.user_account_id == authenticated_user.account.id))
            if body.role == OrganizationRole.OWNER and (membership is None or membership.role != OrganizationRole.OWNER.value):
                raise HTTPException(status_code=403, detail="only an Owner can invite another Owner")
            invitation_groups(session, organization_id, body.group_ids)
            now = clock()
            expire_pending_invitations(session, organization=organization, now=now, request_id=_request_id(request))
            members = set(session.scalars(select(func.lower(UserAccount.email)).join(OrganizationMembership, OrganizationMembership.user_account_id == UserAccount.id).where(OrganizationMembership.organization_id == organization_id)).all())
            pending = set(session.scalars(select(OrganizationInvitation.email).where(OrganizationInvitation.organization_id == organization_id, OrganizationInvitation.status == InvitationStatus.PENDING.value)).all())
            invite: list[str] = []
            skipped: list[SkippedAddress] = []
            for raw in body.emails:
                email = raw.strip().lower()
                if not _valid_email(email): reason = "invalid"
                elif email in invite: reason = "duplicate"
                elif email in members: reason = "member"
                elif email in pending: reason = "invited"
                else:
                    invite.append(email); continue
                skipped.append(SkippedAddress(email=raw.strip(), reason=reason))
            occupied = session.scalar(select(func.count()).select_from(OrganizationMembership).where(OrganizationMembership.organization_id == organization_id)) or 0
            available = max(0, organization.purchased_seats - occupied - organization.reserved_seats)
            seats_needed = max(0, len(invite) - available)
            if body.dry_run:
                return BulkInvitationResponse(invite=invite, skipped=skipped, seats_needed=seats_needed)
            if seats_needed:
                raise HTTPException(status_code=409, detail={"reason": "seats_needed", "seats_needed": seats_needed})
            for email in invite:
                create_invitation(session, organization=organization, invited_by=authenticated_user.account.id, email=email, role=body.role.value, now=now, frontend_url=frontend_url, request_id=_request_id(request), group_ids=body.group_ids)
            return BulkInvitationResponse(invite=invite, skipped=skipped, seats_needed=0, created=len(invite))

    @router.post("/api/v1/organizations/{organization_id}/invitations/{invitation_id}/resend", response_model=InvitationResponse)
    def resend(organization_id: UUID, invitation_id: UUID, request: Request, expected_version: int = Query(ge=1), authenticated_user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> InvitationResponse:
        with _manager_session(session_factory, organization_id, authenticated_user) as (session, organization):
            invitation = session.get(OrganizationInvitation, invitation_id)
            if invitation is None:
                raise HTTPException(status_code=404, detail="invitation not found")
            if expected_version != invitation.version:
                raise HTTPException(status_code=409, detail={"latest_version": invitation.version})
            _require_owner_for_owner_invitation(session, organization_id, authenticated_user, invitation)
            return _response(resend_invitation(session, invitation=invitation, organization=organization, now=clock(), frontend_url=frontend_url, request_id=_request_id(request)).invitation)

    @router.delete("/api/v1/organizations/{organization_id}/invitations/{invitation_id}", status_code=204)
    def revoke(organization_id: UUID, invitation_id: UUID, request: Request, expected_version: int = Query(ge=1), authenticated_user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> None:
        with _manager_session(session_factory, organization_id, authenticated_user) as (session, organization):
            invitation = session.get(OrganizationInvitation, invitation_id)
            if invitation is None:
                raise HTTPException(status_code=404, detail="invitation not found")
            if expected_version != invitation.version:
                raise HTTPException(status_code=409, detail={"latest_version": invitation.version})
            _require_owner_for_owner_invitation(session, organization_id, authenticated_user, invitation)
            revoke_invitation(session, invitation=invitation, organization=organization, now=clock(), request_id=_request_id(request))

    @router.post("/api/v1/invitations/accept", response_model=InvitationResponse)
    def accept(body: AcceptInvitationRequest, request: Request, authenticated_user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> InvitationResponse:
        with transaction_session(
            session_factory,
            RequestContext(
                user_account_id=authenticated_user.account.id,
                invitation_token_hash=hash_invitation_token(body.token),
            ),
        ) as session:
            return _response(
                accept_invitation(
                    session,
                    token=body.token,
                    user_account_id=authenticated_user.account.id,
                    user_email=authenticated_user.account.email,
                    now=clock(),
                    request_id=_request_id(request),
                )
            )
    return router


@contextmanager
def _manager_session(session_factory: sessionmaker[Session], organization_id: UUID, authenticated_user: AuthenticatedUser, *, mutate: bool = True) -> Iterator[tuple[Session, Organization]]:
    with transaction_session(session_factory, RequestContext(user_account_id=authenticated_user.account.id)) as session:
        membership = session.scalar(select(OrganizationMembership).where(OrganizationMembership.organization_id == organization_id, OrganizationMembership.user_account_id == authenticated_user.account.id))
        if membership is None:
            raise HTTPException(status_code=404, detail="organization not found")
        if membership.role not in {OrganizationRole.OWNER.value, OrganizationRole.ADMIN.value}:
            raise HTTPException(status_code=403, detail="Organization management role required")
        apply_request_context(session, RequestContext(user_account_id=authenticated_user.account.id, organization_id=organization_id))
        if mutate:
            require_organization_mutation_access(session, organization_id)
        organization = session.scalar(select(Organization).where(Organization.id == organization_id, Organization.status == OrganizationStatus.ACTIVE.value).with_for_update())
        if organization is None:
            raise HTTPException(status_code=404, detail="organization not found")
        yield session, organization


def _response(invitation: OrganizationInvitation) -> InvitationResponse:
    return InvitationResponse(id=invitation.id, email=invitation.email, role=invitation.role, status=invitation.status, expires_at=invitation.expires_at, version=invitation.version)


def _request_id(request: Request) -> str:
    return (request.headers.get("X-Request-ID") or str(uuid4()))[:120]


def _require_owner_for_owner_invitation(session: Session, organization_id: UUID, user: AuthenticatedUser, invitation: OrganizationInvitation) -> None:
    if invitation.role != OrganizationRole.OWNER.value:
        return
    membership = session.scalar(select(OrganizationMembership).where(OrganizationMembership.organization_id == organization_id, OrganizationMembership.user_account_id == user.account.id))
    if membership is None or membership.role != OrganizationRole.OWNER.value:
        raise HTTPException(status_code=403, detail="only an Owner can manage an Owner invitation")


def _valid_email(email: str) -> bool:
    local, _, domain = email.partition("@")
    return bool(local) and "." in domain and not domain.startswith(".") and not domain.endswith(".") and " " not in email and email.count("@") == 1 and len(email) <= 320

