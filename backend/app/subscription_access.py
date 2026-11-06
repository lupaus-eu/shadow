"""Subscription access states projected from verified Stripe events (docs/architecture/billing.md).

Stored states: ``active``, ``grace`` (with ``grace_expires_at``), and
``canceled``. The effective state adds ``read_only`` when grace has expired or
the subscription has ended. Cancellation never deletes an Organization.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.audit import AuditEventDraft, record_audit_event
from app.billing import StripeEvent
from app.notifications import BILLING_PROBLEM, SUBSCRIPTION_RESUMED, notify_managers
from app.models import Organization

GRACE_PERIOD = timedelta(days=7)
ACTIVE, GRACE, CANCELED, READ_ONLY = "active", "grace", "canceled", "read_only"
SUBSCRIPTION_OUTCOMES = {"subscription_grace_started", "subscription_recovered", "subscription_updated", "subscription_canceled", "subscription_resumed"}


@dataclass(frozen=True)
class SubscriptionView:
    state: str
    writable: bool
    grace_expires_at: datetime | None
    cancel_at_period_end: bool
    current_period_end: datetime | None
    ended: bool = False


def effective_state(organization: Organization, *, now: datetime) -> str:
    if organization.subscription_access_state == ACTIVE:
        return ACTIVE
    if organization.subscription_access_state == GRACE and organization.grace_expires_at and organization.grace_expires_at > now:
        return GRACE
    return READ_ONLY


def subscription_view(organization: Organization, *, now: datetime | None = None) -> SubscriptionView:
    state = effective_state(organization, now=now or datetime.now(UTC))
    return SubscriptionView(
        state=state,
        writable=state != READ_ONLY,
        grace_expires_at=organization.grace_expires_at if state == GRACE else None,
        cancel_at_period_end=bool(organization.cancel_at_period_end),
        current_period_end=organization.current_period_end,
        ended=organization.subscription_access_state == CANCELED,
    )


def mark_renewal_failed(organization: Organization, *, now: datetime) -> None:
    organization.subscription_access_state = GRACE
    organization.grace_expires_at = now + GRACE_PERIOD


def mark_payment_recovered(organization: Organization) -> None:
    organization.subscription_access_state = ACTIVE
    organization.grace_expires_at = None


def require_mutation_access(organization: Organization, *, now: datetime) -> None:
    if effective_state(organization, now=now) == READ_ONLY:
        raise HTTPException(status_code=403, detail="subscription is read-only")


def require_organization_mutation_access(session: Session, organization_id, *, now: datetime | None = None) -> Organization:
    organization = session.get(Organization, organization_id)
    if organization is None:
        raise HTTPException(status_code=404, detail="organization not found")
    if organization.status != "active":
        raise HTTPException(status_code=409, detail="Organization is not active")
    require_mutation_access(organization, now=now or datetime.now(UTC))
    return organization


def resume_subscription(session: Session, *, organization: Organization, event: StripeEvent, now: datetime, request_id: str) -> str:
    """Take a new subscription for an Organization whose subscription has ended (Yearclock V2 P14, ADR-0032).

    Only the confirmed payment of the Checkout session this Organization started counts. The old subscription id
    is kept, so its late events are ignored, and the content was never touched.
    """
    if (
        organization.subscription_access_state != CANCELED
        or not organization.resubscribe_checkout_session_id
        or event.checkout_session_id != organization.resubscribe_checkout_session_id
        or event.payment_status != "paid"
        or not event.subscription_id
        or event.customer_id != organization.stripe_customer_id
    ):
        return "ignored"
    previous = organization.stripe_subscription_id
    organization.previous_subscription_ids = [*organization.previous_subscription_ids, *([previous] if previous else [])]
    organization.stripe_subscription_id = event.subscription_id
    organization.subscription_access_state = ACTIVE
    organization.grace_expires_at = None
    organization.cancel_at_period_end = False
    organization.current_period_end = None
    organization.resubscribe_checkout_session_id = None
    organization.subscription_event_at = event.created_at or now
    if event.quantity:
        organization.purchased_seats = event.quantity
        organization.seat_version += 1
    record_audit_event(session, AuditEventDraft(
        action="organization.subscription_changed",
        target_type="organization",
        target_id=organization.id,
        request_id=request_id,
        change_summary={"stripe_event": event.type, "state": ACTIVE, "previous_state": CANCELED, "outcome": "subscription_resumed", "purchased_seats": organization.purchased_seats},
    ))
    notify_managers(session, organization.id, SUBSCRIPTION_RESUMED, {})
    return "subscription_resumed"


def apply_subscription_event(session: Session, *, organization: Organization, event: StripeEvent, now: datetime, request_id: str) -> str:
    """Project one verified renewal, payment, or cancellation event; ignore stale or unrelated ones."""
    relevant = event.type in {"invoice.payment_failed", "invoice.paid", "invoice.payment_succeeded", "customer.subscription.updated", "customer.subscription.deleted"}
    if not relevant or not organization.stripe_subscription_id or event.subscription_id != organization.stripe_subscription_id:
        return "ignored"
    occurred = event.created_at or now
    if organization.subscription_event_at and occurred < organization.subscription_event_at:
        return "ignored_stale"
    before = (organization.subscription_access_state, organization.cancel_at_period_end)
    outcome = "ignored"
    renewal = event.seat_change_id is None and event.billing_reason in {None, "subscription_cycle"}
    if event.type == "invoice.payment_failed" and renewal:
        if organization.subscription_access_state == ACTIVE:
            mark_renewal_failed(organization, now=occurred)
            outcome = "subscription_grace_started"
    elif event.type in {"invoice.paid", "invoice.payment_succeeded"} and event.seat_change_id is None:
        if organization.subscription_access_state == GRACE:
            mark_payment_recovered(organization)
            outcome = "subscription_recovered"
    elif event.type == "customer.subscription.updated":
        if event.cancel_at_period_end is not None:
            organization.cancel_at_period_end = event.cancel_at_period_end
        if event.current_period_end is not None:
            organization.current_period_end = event.current_period_end
        outcome = "subscription_updated"
    elif event.type == "customer.subscription.deleted":
        organization.subscription_access_state = CANCELED
        organization.grace_expires_at = None
        organization.cancel_at_period_end = False
        outcome = "subscription_canceled"
    if outcome == "ignored":
        return outcome
    organization.subscription_event_at = occurred
    after = (organization.subscription_access_state, organization.cancel_at_period_end)
    if after != before or outcome != "subscription_updated":
        record_audit_event(session, AuditEventDraft(
            action="organization.subscription_changed",
            target_type="organization",
            target_id=organization.id,
            request_id=request_id,
            change_summary={
                "stripe_event": event.type,
                "state": organization.subscription_access_state,
                "previous_state": before[0],
                "cancel_at_period_end": organization.cancel_at_period_end,
                "grace_expires_at": organization.grace_expires_at.isoformat() if organization.grace_expires_at else None,
            },
        ))
    if outcome in {"subscription_grace_started", "subscription_canceled"}:
        notify_managers(session, organization.id, BILLING_PROBLEM, {"state": "canceled" if outcome == "subscription_canceled" else "grace", "grace_expires_at": organization.grace_expires_at.isoformat() if organization.grace_expires_at else None})
    return outcome
