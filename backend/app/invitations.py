import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.audit import AuditEventDraft, record_audit_event
from app.database import RequestContext, apply_request_context
from app.notifications import notify_invitation_accepted
from app.models import (
    Group,
    GroupMember,
    InvitationGroup,
    InvitationStatus,
    Organization,
    OrganizationInvitation,
    OrganizationMembership,
    OrganizationRole,
)
from app.work_queue import OutboxMessageDraft, enqueue_outbox_message

INVITATION_LIFETIME = timedelta(days=7)


@dataclass(frozen=True)
class CreatedInvitation:
    invitation: OrganizationInvitation
    token: str


def create_invitation(
    session: Session,
    *,
    organization: Organization,
    invited_by: UUID,
    email: str,
    role: str,
    now: datetime,
    frontend_url: str,
    request_id: str,
    group_ids: list[UUID] | None = None,
) -> CreatedInvitation:
    expire_pending_invitations(
        session, organization=organization, now=now, request_id=request_id
    )
    occupied = session.scalar(
        select(func.count())
        .select_from(OrganizationMembership)
        .where(OrganizationMembership.organization_id == organization.id)
    )
    if occupied + organization.reserved_seats >= organization.purchased_seats:
        raise HTTPException(status_code=409, detail="no Organization Seat is available")
    token = secrets.token_urlsafe(32)
    invitation = OrganizationInvitation(
        id=uuid4(), organization_id=organization.id,
        invited_by_user_account_id=invited_by, email=email.lower(), role=role,
        token_hash=hash_invitation_token(token), status=InvitationStatus.PENDING.value,
        expires_at=now + INVITATION_LIFETIME, accepted_by_user_account_id=None, accepted_at=None,
    )
    organization.reserved_seats += 1
    session.add(invitation)
    session.flush()
    groups = invitation_groups(session, organization.id, group_ids or [])
    for group in groups:
        session.add(InvitationGroup(invitation_id=invitation.id, group_id=group.id, organization_id=organization.id))
    _enqueue(session, invitation, token, organization, frontend_url)
    record_audit_event(session, AuditEventDraft(action="organization.invitation_created", target_type="organization_invitation", target_id=invitation.id, request_id=request_id, change_summary={"email": invitation.email, "role": invitation.role, "expires_at": invitation.expires_at.isoformat(), **({"groups": [group.name for group in groups]} if groups else {})}))
    return CreatedInvitation(invitation, token)


def resend_invitation(session: Session, *, invitation: OrganizationInvitation, organization: Organization, now: datetime, frontend_url: str, request_id: str) -> CreatedInvitation:
    expire_pending_invitations(
        session, organization=organization, now=now, request_id=request_id
    )
    if invitation.status != InvitationStatus.PENDING.value or invitation.expires_at <= now:
        raise HTTPException(status_code=409, detail="invitation is no longer pending")
    invitation.status = InvitationStatus.SUPERSEDED.value
    invitation.version += 1
    token = secrets.token_urlsafe(32)
    replacement = OrganizationInvitation(id=uuid4(), organization_id=organization.id, invited_by_user_account_id=invitation.invited_by_user_account_id, email=invitation.email, role=invitation.role, token_hash=hash_invitation_token(token), status=InvitationStatus.PENDING.value, expires_at=now + INVITATION_LIFETIME, accepted_by_user_account_id=None, accepted_at=None)
    session.add(replacement)
    session.flush()
    for group_id in session.scalars(select(InvitationGroup.group_id).where(InvitationGroup.invitation_id == invitation.id)).all():
        session.add(InvitationGroup(invitation_id=replacement.id, group_id=group_id, organization_id=organization.id))
    _enqueue(session, replacement, token, organization, frontend_url)
    record_audit_event(session, AuditEventDraft(action="organization.invitation_resent", target_type="organization_invitation", target_id=replacement.id, request_id=request_id, change_summary={"superseded_invitation_id": str(invitation.id), "email": replacement.email}))
    return CreatedInvitation(replacement, token)


def revoke_invitation(session: Session, *, invitation: OrganizationInvitation, organization: Organization, now: datetime, request_id: str) -> None:
    expire_pending_invitations(
        session, organization=organization, now=now, request_id=request_id
    )
    if invitation.status != InvitationStatus.PENDING.value:
        raise HTTPException(status_code=409, detail="invitation is no longer pending")
    invitation.status = InvitationStatus.REVOKED.value
    invitation.version += 1
    organization.reserved_seats -= 1
    record_audit_event(session, AuditEventDraft(action="organization.invitation_revoked", target_type="organization_invitation", target_id=invitation.id, request_id=request_id, change_summary={"email": invitation.email}))


def accept_invitation(
    session: Session,
    *,
    token: str,
    user_account_id: UUID,
    user_email: str,
    now: datetime,
    request_id: str,
) -> OrganizationInvitation:
    invitation = session.scalar(
        select(OrganizationInvitation).where(
            OrganizationInvitation.token_hash == hash_invitation_token(token)
        )
    )
    if invitation is None:
        raise HTTPException(status_code=404, detail="invitation not found")
    if invitation.email != user_email.strip().lower():
        raise HTTPException(status_code=404, detail="invitation not found")
    apply_request_context(session, RequestContext(user_account_id=user_account_id, organization_id=invitation.organization_id))
    invitation = session.scalar(
        select(OrganizationInvitation)
        .where(OrganizationInvitation.id == invitation.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if invitation is None:
        raise HTTPException(status_code=404, detail="invitation not found")
    organization = session.scalar(select(Organization).where(Organization.id == invitation.organization_id).with_for_update())
    if organization is None:
        raise HTTPException(status_code=404, detail="invitation not found")
    expire_pending_invitations(
        session, organization=organization, now=now, request_id=request_id
    )
    if invitation.status != InvitationStatus.PENDING.value:
        raise HTTPException(status_code=409, detail="invitation is no longer pending")
    existing = session.scalar(select(OrganizationMembership).where(OrganizationMembership.organization_id == organization.id, OrganizationMembership.user_account_id == user_account_id))
    if existing is not None:
        raise HTTPException(status_code=409, detail="Organization membership already exists")
    membership = OrganizationMembership(id=uuid4(), organization_id=organization.id, user_account_id=user_account_id, role=invitation.role)
    session.add(membership)
    session.flush()
    # Groups chosen at invitation; a Group deleted since then has cascaded away.
    for group_id in session.scalars(select(InvitationGroup.group_id).where(InvitationGroup.invitation_id == invitation.id)).all():
        session.add(GroupMember(group_id=group_id, membership_id=membership.id, organization_id=organization.id))
    invitation.status = InvitationStatus.ACCEPTED.value
    invitation.version += 1
    invitation.accepted_by_user_account_id = user_account_id
    invitation.accepted_at = now
    organization.reserved_seats -= 1
    notify_invitation_accepted(session, organization.id, inviter_id=invitation.invited_by_user_account_id, accepted_by=user_account_id, role=invitation.role)
    record_audit_event(session, AuditEventDraft(action="organization.invitation_accepted", target_type="organization_invitation", target_id=invitation.id, request_id=request_id, change_summary={"role": invitation.role}))
    return invitation


def invitation_groups(session: Session, organization_id: UUID, group_ids: list[UUID]) -> list[Group]:
    """The chosen Groups, refused when any is not a Group of this Organization."""
    wanted = list(dict.fromkeys(group_ids))
    groups = session.scalars(select(Group).where(Group.organization_id == organization_id, Group.id.in_(wanted))).all() if wanted else []
    if len(groups) != len(wanted):
        raise HTTPException(status_code=422, detail="Group not found in this Organization")
    return list(groups)


def expire_pending_invitations(
    session: Session,
    *,
    organization: Organization,
    now: datetime,
    request_id: str,
) -> None:
    invitations = session.scalars(select(OrganizationInvitation).where(OrganizationInvitation.organization_id == organization.id, OrganizationInvitation.status == InvitationStatus.PENDING.value, OrganizationInvitation.expires_at <= now).with_for_update()).all()
    for invitation in invitations:
        invitation.status = InvitationStatus.EXPIRED.value
        invitation.version += 1
        organization.reserved_seats = max(0, organization.reserved_seats - 1)
        record_audit_event(
            session,
            AuditEventDraft(
                action="organization.invitation_expired",
                target_type="organization_invitation",
                target_id=invitation.id,
                request_id=request_id,
                change_summary={"email": invitation.email},
            ),
        )


INVITATION_EMAIL = {
    "en": ("Invitation to {organization}", "You have been invited to {organization} on Yearclock.\n\nAccept your invitation: {url}\n\nThe invitation expires in seven days.\n\nPrivacy notice: {privacy_url}\nYearclock is a service of Lupaus Palvelut Oy."),
    "fi": ("Kutsu organisaatioon {organization}", "Sinut on kutsuttu organisaatioon {organization} Yearclockissa.\n\nHyväksy kutsu: {url}\n\nKutsu vanhenee seitsemässä päivässä.\n\nTietosuojaseloste: {privacy_url}\nYearclock on Lupaus Palvelut Oy:n palvelu."),
}


def _enqueue(session: Session, invitation: OrganizationInvitation, token: str, organization: Organization, frontend_url: str) -> None:
    """Queue the Invitation email in the Organization's default language (the invitee has no account yet)."""
    accept_url = f"{frontend_url.rstrip('/')}/invitations/{token}"
    subject, body = INVITATION_EMAIL.get(organization.default_locale, INVITATION_EMAIL["en"])
    payload = {"to": invitation.email, "subject": subject.format(organization=organization.name), "text": body.format(organization=organization.name, url=accept_url, privacy_url=f"{frontend_url.rstrip('/')}/legal/privacy"), "accept_url": accept_url}
    enqueue_outbox_message(session, OutboxMessageDraft(topic="organization.invitation", payload=payload, idempotency_key=f"invitation:{invitation.id}:email"))


def hash_invitation_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
