"""Owner actions on the subscription (Yearclock V2 P14, ADR-0032).

Cancellation is always at the end of the paid period and can be undone until
then. Stripe is called first; when it fails nothing changes locally. When it
succeeds the local projection is updated from its answer in the same request,
and the webhook that follows leaves it unchanged.
"""
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.audit import AuditEventDraft, record_audit_event
from app.auth import AuthenticatedUser
from app.auth_routes import AuthenticatedUserDependency
from app.billing import InvoiceSummary, ResubscribeRequest, StripeBilling, UpcomingCharge
from app.database import RequestContext, apply_request_context, transaction_session
from app.billing_contact import notice_message
from app.limits import BILLING_CONTACT_CHANGES
from app.models import AuditEvent, Organization, OrganizationMembership, OrganizationRole, OrganizationSeatChange, OrganizationStatus, SeatChangeStatus
from app.work_queue import OutboxMessageDraft, enqueue_outbox_message
from app.notifications import BILLING_CONTACT_CHANGED, SUBSCRIPTION_CANCEL_SCHEDULED, SUBSCRIPTION_CANCEL_UNDONE, notify_managers
from app.seat_capacity import seat_projection
from app.subscription_access import CANCELED, subscription_view

RESUBSCRIBE_LIFETIME = timedelta(hours=12)
REASONS = ("too_expensive", "not_needed", "switching", "other")


class CancelRequest(BaseModel):
    reason: Literal["too_expensive", "not_needed", "switching", "other"] | None = None


class ResubscribeBody(BaseModel):
    seats: int = Field(ge=1, le=10_000)


class ContactBody(BaseModel):
    billing_name: str = Field(min_length=1, max_length=200)
    billing_email: str = Field(min_length=3, max_length=320)

    @field_validator("billing_name")
    @classmethod
    def name_not_blank(cls, value: str) -> str:
        if not (stripped := value.strip()):
            raise ValueError("must not be blank")
        return stripped

    @field_validator("billing_email")
    @classmethod
    def email_has_an_address_shape(cls, value: str) -> str:
        stripped = value.strip()
        local, _, domain = stripped.partition("@")
        if not local or "." not in domain or domain.startswith(".") or domain.endswith(".") or " " in stripped:
            raise ValueError("invalid billing email")
        return stripped


class ContactResponse(BaseModel):
    billing_name: str
    billing_email: str


class CheckoutResponse(BaseModel):
    url: str


class SubscriptionResponse(BaseModel):
    state: str
    writable: bool
    grace_expires_at: datetime | None
    cancel_at_period_end: bool
    current_period_end: datetime | None
    ended: bool = False
    released_seat_decrease: bool = False


class NextChargeResponse(BaseModel):
    status: Literal["scheduled", "none_cancelled", "none_ended", "unavailable"]
    charge_date: datetime | None = None
    amount: int | None = None
    currency: str | None = None
    seats: int | None = None


class InvoiceResponse(BaseModel):
    id: str
    date: datetime
    amount: int
    currency: str
    state: str
    reason: str
    hosted_invoice_url: str | None


class InvoicesResponse(BaseModel):
    status: Literal["ok", "unavailable"]
    invoices: list[InvoiceResponse]


def _request_id(request: Request) -> str:
    return (request.headers.get("X-Request-ID") or str(uuid4()))[:120]


@contextmanager
def owner_session(factory: sessionmaker[Session], organization_id: UUID, user: AuthenticatedUser):
    """An Owner's transaction with the active Organization locked."""
    with transaction_session(factory, RequestContext(user_account_id=user.account.id)) as session:
        membership = session.scalar(select(OrganizationMembership).where(OrganizationMembership.organization_id == organization_id, OrganizationMembership.user_account_id == user.account.id))
        if membership is None:
            raise HTTPException(status_code=404, detail="organization not found")
        if membership.role != OrganizationRole.OWNER.value:
            raise HTTPException(status_code=403, detail="owner role required")
        apply_request_context(session, RequestContext(user_account_id=user.account.id, organization_id=organization_id))
        organization = session.scalar(select(Organization).where(Organization.id == organization_id, Organization.status == OrganizationStatus.ACTIVE.value).with_for_update())
        if organization is None:
            raise HTTPException(status_code=409, detail="Organization is not active")
        yield session, organization


def create_subscription_router(*, session_factory: sessionmaker[Session], authenticated_user_dependency: AuthenticatedUserDependency, stripe_billing: StripeBilling) -> APIRouter:
    router = APIRouter(prefix="/api/v1/organizations/{organization_id}/billing", tags=["organization billing"])

    def _view(organization: Organization, *, released: bool = False) -> SubscriptionResponse:
        view = subscription_view(organization)
        return SubscriptionResponse(state=view.state, writable=view.writable, grace_expires_at=view.grace_expires_at, cancel_at_period_end=view.cancel_at_period_end, current_period_end=view.current_period_end, ended=view.ended, released_seat_decrease=released)

    @router.get("/next-charge", response_model=NextChargeResponse)
    def next_charge(organization_id: UUID, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> NextChargeResponse:
        with owner_session(session_factory, organization_id, user) as (_, organization):
            subscription_id = organization.stripe_subscription_id
            ended = not subscription_id or organization.subscription_access_state == CANCELED
            cancelled = organization.cancel_at_period_end
        if ended:
            return NextChargeResponse(status="none_ended")
        if cancelled:
            return NextChargeResponse(status="none_cancelled")
        try:
            charge: UpcomingCharge = stripe_billing.upcoming_charge(subscription_id=subscription_id)
        except HTTPException:
            return NextChargeResponse(status="unavailable")
        return NextChargeResponse(status="scheduled", charge_date=charge.charge_date, amount=charge.amount, currency=charge.currency, seats=charge.seats)

    @router.get("/invoices", response_model=InvoicesResponse)
    def invoices(organization_id: UUID, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> InvoicesResponse:
        with owner_session(session_factory, organization_id, user) as (_, organization):
            customer_id = organization.stripe_customer_id
        if not customer_id:
            return InvoicesResponse(status="ok", invoices=[])
        try:
            found: list[InvoiceSummary] = stripe_billing.list_invoices(customer_id=customer_id, limit=12)
        except HTTPException:
            return InvoicesResponse(status="unavailable", invoices=[])
        return InvoicesResponse(status="ok", invoices=[InvoiceResponse(id=item.id, date=item.created, amount=item.amount, currency=item.currency, state=item.state, reason=item.reason, hosted_invoice_url=item.hosted_invoice_url) for item in found[:12]])

    @router.post("/cancel", response_model=SubscriptionResponse)
    def cancel(organization_id: UUID, request: Request, body: CancelRequest | None = None, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> SubscriptionResponse:
        with owner_session(session_factory, organization_id, user) as (session, organization):
            if not organization.stripe_subscription_id or organization.subscription_access_state == CANCELED:
                raise HTTPException(status_code=409, detail="the subscription has already ended")
            if organization.cancel_at_period_end:
                raise HTTPException(status_code=409, detail="the cancellation is already scheduled")
            pending = session.scalar(select(OrganizationSeatChange).where(OrganizationSeatChange.organization_id == organization_id, OrganizationSeatChange.status == SeatChangeStatus.SCHEDULED.value).order_by(OrganizationSeatChange.created_at.desc()))
            result = stripe_billing.set_cancel_at_period_end(subscription_id=organization.stripe_subscription_id, cancel=True, schedule_id=pending.stripe_reference if pending else None)
            _apply(organization, result)
            if pending is not None:
                pending.status = SeatChangeStatus.FAILED.value
                organization.seat_version += 1
                record_audit_event(session, AuditEventDraft(action="organization.seat_change_failed", target_type="organization_seat_change", target_id=pending.id, request_id=_request_id(request), change_summary={"from_quantity": pending.from_quantity, "target_quantity": pending.target_quantity, "reason": "subscription_cancel_scheduled"}))
            record_audit_event(session, AuditEventDraft(action="organization.subscription_cancel_scheduled", target_type="organization", target_id=organization.id, request_id=_request_id(request), change_summary={"reason": body.reason if body else None, "current_period_end": organization.current_period_end.isoformat() if organization.current_period_end else None, "released_seat_decrease": pending is not None}))
            notify_managers(session, organization.id, SUBSCRIPTION_CANCEL_SCHEDULED, {"current_period_end": organization.current_period_end.isoformat() if organization.current_period_end else None}, actor_id=user.account.id)
            return _view(organization, released=pending is not None)

    @router.post("/cancel/undo", response_model=SubscriptionResponse)
    def undo(organization_id: UUID, request: Request, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> SubscriptionResponse:
        with owner_session(session_factory, organization_id, user) as (session, organization):
            if not organization.stripe_subscription_id or organization.subscription_access_state == CANCELED:
                raise HTTPException(status_code=409, detail="the subscription has already ended")
            if not organization.cancel_at_period_end:
                raise HTTPException(status_code=409, detail="no cancellation is scheduled")
            result = stripe_billing.set_cancel_at_period_end(subscription_id=organization.stripe_subscription_id, cancel=False)
            _apply(organization, result)
            record_audit_event(session, AuditEventDraft(action="organization.subscription_cancel_undone", target_type="organization", target_id=organization.id, request_id=_request_id(request), change_summary={}))
            notify_managers(session, organization.id, SUBSCRIPTION_CANCEL_UNDONE, {}, actor_id=user.account.id)
            return _view(organization)

    @router.get("/contact", response_model=ContactResponse)
    def read_contact(organization_id: UUID, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> ContactResponse:
        with owner_session(session_factory, organization_id, user) as (_, organization):
            return ContactResponse(billing_name=organization.billing_name, billing_email=organization.billing_email)

    @router.put("/contact", response_model=ContactResponse)
    def write_contact(organization_id: UUID, body: ContactBody, request: Request, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> ContactResponse:
        with owner_session(session_factory, organization_id, user) as (session, organization):
            fields = [name for name, old, new in (("name", organization.billing_name, body.billing_name), ("email", organization.billing_email, body.billing_email)) if old != new]
            if not fields:
                return ContactResponse(billing_name=organization.billing_name, billing_email=organization.billing_email)
            _require_contact_quota(session, organization.id)
            if not organization.stripe_customer_id:
                raise HTTPException(status_code=409, detail="no Stripe customer for this Organization")
            stripe_billing.update_customer(customer_id=organization.stripe_customer_id, name=body.billing_name, email=body.billing_email)
            old_email = organization.billing_email
            organization.billing_name, organization.billing_email = body.billing_name, body.billing_email
            record_audit_event(session, AuditEventDraft(action="organization.billing_contact_changed", target_type="organization", target_id=organization.id, request_id=_request_id(request), change_summary={"fields": fields}))
            if "email" in fields:
                subject, text = notice_message(organization.default_locale, organization.name, body.billing_email)
                enqueue_outbox_message(session, OutboxMessageDraft(topic="billing.contact_changed", payload={"to": old_email, "subject": subject, "text": text}, idempotency_key=f"billing-contact:{uuid4()}"))
            notify_managers(session, organization.id, BILLING_CONTACT_CHANGED, {"fields": fields}, actor_id=user.account.id)
            return ContactResponse(billing_name=organization.billing_name, billing_email=organization.billing_email)

    @router.post("/resubscribe", response_model=CheckoutResponse)
    def resubscribe(organization_id: UUID, body: ResubscribeBody, request: Request, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> CheckoutResponse:
        with owner_session(session_factory, organization_id, user) as (session, organization):
            if organization.subscription_access_state != CANCELED or not organization.stripe_customer_id:
                raise HTTPException(status_code=409, detail="the subscription has not ended")
            needed = seat_projection(session, organization)
            minimum = needed.occupied + needed.reserved
            if body.seats < minimum:
                raise HTTPException(status_code=422, detail={"reason": "too_few_seats", "minimum": minimum})
            now = datetime.now(UTC)
            request_id = _request_id(request)
            checkout = stripe_billing.create_resubscribe_checkout(ResubscribeRequest(organization_id=str(organization.id), customer_id=organization.stripe_customer_id, seats=body.seats, locale=organization.default_locale, expires_at=now + RESUBSCRIBE_LIFETIME, request_id=f"{organization.id}:{uuid4()}"))
            organization.resubscribe_checkout_session_id = checkout.id
            record_audit_event(session, AuditEventDraft(action="organization.resubscribe_started", target_type="organization", target_id=organization.id, request_id=request_id, change_summary={"seats": body.seats}))
            return CheckoutResponse(url=checkout.url)

    return router


def _require_contact_quota(session: Session, organization_id: UUID) -> None:
    """At most a few changes a day per Organization, counted from the Audit Log; a refusal says when to retry."""
    now = session.scalar(select(func.now()))
    since = now - timedelta(hours=24)
    recent = session.scalars(select(AuditEvent.occurred_at).where(AuditEvent.organization_id == organization_id, AuditEvent.action == "organization.billing_contact_changed", AuditEvent.occurred_at > since).order_by(AuditEvent.occurred_at)).all()
    if len(recent) >= BILLING_CONTACT_CHANGES.maximum:
        retry_after = max(1, int((recent[len(recent) - BILLING_CONTACT_CHANGES.maximum] + timedelta(hours=24) - now).total_seconds()) + 1)
        raise HTTPException(status_code=429, detail={"reason": "rate_limited", "limit": BILLING_CONTACT_CHANGES.name, "maximum": BILLING_CONTACT_CHANGES.maximum, "retry_after_seconds": retry_after}, headers={"Retry-After": str(retry_after)})


def _apply(organization: Organization, result) -> None:
    organization.cancel_at_period_end = result.cancel_at_period_end
    if result.current_period_end is not None:
        organization.current_period_end = result.current_period_end
    # Older events still in flight must not undo what Stripe has just confirmed.
    organization.subscription_event_at = datetime.now(UTC)
