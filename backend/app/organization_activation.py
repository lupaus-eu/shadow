from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import AuditEventDraft, record_audit_event
from app.billing import StripeEvent
from app.database import RequestContext, apply_request_context
from app.models import (
    Lane,
    Organization,
    OrganizationMembership,
    OrganizationRole,
    OrganizationStatus,
    StripeWebhookEvent,
    Yearclock,
)
from app.seat_capacity import apply_seat_event
from app.subscription_access import SUBSCRIPTION_OUTCOMES, apply_subscription_event, resume_subscription

PENDING_ACTIVATION_LIFETIME = timedelta(hours=24)
PROCESSED_STRIPE_OUTCOMES = {
    "activated",
    "seat_change_applied",
    "seat_change_failed",
    *SUBSCRIPTION_OUTCOMES,
}


@dataclass(frozen=True)
class InitialContent:
    owner_user_account_id: UUID
    yearclock_id: UUID
    yearclock_name: str
    lane_id: UUID
    lane_name: str


def create_pending_organization(
    session: Session,
    *,
    user_account_id: UUID,
    name: str,
    time_zone: str,
    default_locale: str,
    billing_name: str,
    billing_email: str,
    initial_seats: int,
    now: datetime,
    request_id: str,
) -> Organization:
    organization = Organization(
        id=uuid4(),
        name=name,
        time_zone=time_zone,
        default_locale=default_locale,
        status=OrganizationStatus.PENDING_ACTIVATION.value,
        created_by_user_account_id=user_account_id,
        billing_name=billing_name,
        billing_email=billing_email,
        purchased_seats=initial_seats,
        pending_activation_expires_at=now + PENDING_ACTIVATION_LIFETIME,
    )
    session.add(organization)
    session.flush()
    apply_request_context(
        session,
        RequestContext(
            user_account_id=user_account_id,
            organization_id=organization.id,
        ),
    )
    record_audit_event(
        session,
        AuditEventDraft(
            action="organization.signup_started",
            target_type="organization",
            target_id=organization.id,
            request_id=request_id,
            change_summary={
                "status": OrganizationStatus.PENDING_ACTIVATION.value,
                "purchased_seats": initial_seats,
            },
        ),
    )
    return organization


def find_signup_for_creator(
    session: Session,
    *,
    organization_id: UUID,
    user_account_id: UUID,
    now: datetime,
) -> Organization:
    organization = session.scalar(
        select(Organization).where(
            Organization.id == organization_id,
            Organization.created_by_user_account_id == user_account_id,
        )
    )
    if organization is None:
        raise HTTPException(status_code=404, detail="organization signup not found")
    if (
        organization.status == OrganizationStatus.PENDING_ACTIVATION.value
        and organization.pending_activation_expires_at <= now
    ):
        organization.status = OrganizationStatus.EXPIRED.value
    if organization.status == OrganizationStatus.ACTIVE.value:
        membership = session.scalar(
            select(OrganizationMembership).where(
                OrganizationMembership.organization_id == organization.id,
                OrganizationMembership.user_account_id == user_account_id,
            )
        )
        if membership is None:
            raise HTTPException(
                status_code=404,
                detail="organization signup not found",
            )
    return organization


def initial_content(
    session: Session,
    organization: Organization,
) -> InitialContent | None:
    if organization.status != OrganizationStatus.ACTIVE.value:
        return None
    membership = session.scalar(
        select(OrganizationMembership).where(
            OrganizationMembership.organization_id == organization.id,
            OrganizationMembership.role == OrganizationRole.OWNER.value,
        )
    )
    yearclock = session.scalar(
        select(Yearclock).where(Yearclock.organization_id == organization.id)
    )
    if membership is None or yearclock is None:
        raise RuntimeError("active organization is missing initial content")
    lane = session.scalar(
        select(Lane).where(
            Lane.organization_id == organization.id,
            Lane.yearclock_id == yearclock.id,
        )
    )
    if lane is None:
        raise RuntimeError("active organization is missing its General Lane")
    return InitialContent(
        owner_user_account_id=membership.user_account_id,
        yearclock_id=yearclock.id,
        yearclock_name=yearclock.name,
        lane_id=lane.id,
        lane_name=lane.name,
    )


@dataclass(frozen=True)
class WebhookOutcome:
    processed: bool
    duplicate: bool
    outcome: str


def process_checkout_event(
    session: Session,
    *,
    event: StripeEvent,
    now: datetime,
    request_id: str,
) -> WebhookOutcome:
    if not event.id:
        raise HTTPException(status_code=400, detail="Stripe event id required")

    existing = session.get(StripeWebhookEvent, event.id)
    if existing is not None:
        return _duplicate_outcome(existing)

    organization_id = _organization_id(event.organization_id)
    organization = None
    if organization_id is not None:
        organization = session.scalar(
            select(Organization)
            .where(Organization.id == organization_id)
            .with_for_update()
        )
        existing = session.get(StripeWebhookEvent, event.id)
        if existing is not None:
            return _duplicate_outcome(existing)

    outcome = "ignored"
    processed = False
    if (
        event.type == "checkout.session.completed"
        and event.payment_status == "paid"
        and organization is not None
        and organization.status == OrganizationStatus.PENDING_ACTIVATION.value
        and organization.stripe_checkout_session_id == event.checkout_session_id
        and event.customer_id
        and event.subscription_id
    ):
        if organization.pending_activation_expires_at <= now:
            organization.status = OrganizationStatus.EXPIRED.value
            outcome = "expired"
        else:
            _activate_organization(
                session,
                organization=organization,
                event=event,
                now=now,
                request_id=request_id,
            )
            outcome = "activated"
            processed = True
    elif (
        event.type == "checkout.session.completed"
        and event.purpose == "resubscribe"
        and organization is not None
        and organization.status == OrganizationStatus.ACTIVE.value
    ):
        outcome = resume_subscription(session, organization=organization, event=event, now=now, request_id=request_id)
        processed = outcome == "subscription_resumed"
    elif (
        organization is not None
        and organization.status in {OrganizationStatus.ACTIVE.value, OrganizationStatus.PENDING_DELETION.value}
    ):
        outcome = "ignored"
        if organization.status == OrganizationStatus.ACTIVE.value:
            outcome = apply_seat_event(
                session,
                organization=organization,
                event=event,
                now=now,
                request_id=request_id,
            )
        if outcome == "ignored":
            outcome = apply_subscription_event(
                session,
                organization=organization,
                event=event,
                now=now,
                request_id=request_id,
            )
        processed = outcome in PROCESSED_STRIPE_OUTCOMES

    session.add(
        StripeWebhookEvent(
            event_id=event.id,
            organization_id=organization.id if organization else None,
            event_type=event.type,
            outcome=outcome,
        )
    )
    return WebhookOutcome(
        processed=processed,
        duplicate=False,
        outcome=outcome,
    )


def _activate_organization(
    session: Session,
    *,
    organization: Organization,
    event: StripeEvent,
    now: datetime,
    request_id: str,
) -> None:
    organization.status = OrganizationStatus.ACTIVE.value
    organization.activated_at = now
    organization.stripe_customer_id = event.customer_id
    organization.stripe_subscription_id = event.subscription_id
    membership = OrganizationMembership(
        id=uuid4(),
        organization_id=organization.id,
        user_account_id=organization.created_by_user_account_id,
        role=OrganizationRole.OWNER.value,
    )
    yearclock = Yearclock(
        id=uuid4(),
        organization_id=organization.id,
        name="Vuosikello" if organization.default_locale == "fi" else "Yearclock",
        display_order=0,
    )
    session.add_all([membership, yearclock])
    session.flush()
    lane = Lane(
        id=uuid4(),
        organization_id=organization.id,
        yearclock_id=yearclock.id,
        name="Yleinen" if organization.default_locale == "fi" else "General",
        display_order=0,
    )
    session.add(lane)
    record_audit_event(
        session,
        AuditEventDraft(
            action="organization.activated",
            target_type="organization",
            target_id=organization.id,
            request_id=request_id,
            change_summary={
                "status": OrganizationStatus.ACTIVE.value,
                "purchased_seats": organization.purchased_seats,
            },
        ),
    )


def _organization_id(value: str | None) -> UUID | None:
    if value is None:
        return None
    try:
        return UUID(value)
    except ValueError:
        return None


def _duplicate_outcome(event: StripeWebhookEvent) -> WebhookOutcome:
    return WebhookOutcome(
        processed=event.outcome in PROCESSED_STRIPE_OUTCOMES,
        duplicate=True,
        outcome=event.outcome,
    )
