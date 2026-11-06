from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.audit import AuditEventDraft, record_audit_event
from app.billing import (
    SeatChangeRequest,
    SeatChangeResult,
    SeatIncreasePreviewRequest,
    StripeBilling,
    StripeEvent,
)
from app.models import (
    Organization,
    OrganizationMembership,
    OrganizationSeatChange,
    OrganizationSeatPreview,
    SeatChangeKind,
    SeatChangeStatus,
)

SEAT_PREVIEW_LIFETIME = timedelta(minutes=30)


@dataclass(frozen=True)
class SeatProjection:
    purchased: int
    occupied: int
    reserved: int
    available: int
    version: int
    pending_change: OrganizationSeatChange | None


def seat_projection(session: Session, organization: Organization) -> SeatProjection:
    occupied = session.scalar(
        select(func.count())
        .select_from(OrganizationMembership)
        .where(OrganizationMembership.organization_id == organization.id)
    ) or 0
    pending_change = session.scalar(
        select(OrganizationSeatChange)
        .where(
            OrganizationSeatChange.organization_id == organization.id,
            OrganizationSeatChange.status.in_(
                [
                    SeatChangeStatus.PENDING_PAYMENT.value,
                    SeatChangeStatus.SCHEDULED.value,
                ]
            ),
        )
        .order_by(OrganizationSeatChange.created_at.desc())
    )
    effective_capacity = organization.purchased_seats
    if (
        pending_change is not None
        and pending_change.status == SeatChangeStatus.SCHEDULED.value
    ):
        effective_capacity = min(
            effective_capacity,
            pending_change.target_quantity,
        )
    available = effective_capacity - occupied - organization.reserved_seats
    return SeatProjection(
        purchased=organization.purchased_seats,
        occupied=occupied,
        reserved=organization.reserved_seats,
        available=max(available, 0),
        version=organization.seat_version,
        pending_change=pending_change,
    )


def preview_increase(
    session: Session,
    *,
    organization: Organization,
    target_seats: int,
    expected_version: int,
    now: datetime,
    stripe: StripeBilling,
) -> OrganizationSeatPreview:
    _validate_version_and_no_open_change(
        session,
        organization=organization,
        expected_version=expected_version,
    )
    if target_seats <= organization.purchased_seats:
        raise HTTPException(
            status_code=422,
            detail="increase preview requires a higher seat quantity",
        )
    if not organization.stripe_subscription_id:
        raise HTTPException(status_code=409, detail="subscription is not active")
    stripe_preview = stripe.preview_seat_increase(
        SeatIncreasePreviewRequest(
            organization_id=str(organization.id),
            subscription_id=organization.stripe_subscription_id,
            current_seats=organization.purchased_seats,
            target_seats=target_seats,
            proration_date=now,
        )
    )
    preview = OrganizationSeatPreview(
        id=uuid4(),
        organization_id=organization.id,
        seat_version=organization.seat_version,
        from_quantity=organization.purchased_seats,
        target_quantity=target_seats,
        amount_due=stripe_preview.amount_due,
        currency=stripe_preview.currency,
        proration_date=stripe_preview.proration_date,
        expires_at=now + SEAT_PREVIEW_LIFETIME,
        consumed_at=None,
    )
    session.add(preview)
    session.flush()
    return preview


def request_change(
    session: Session,
    *,
    organization: Organization,
    requested_by_user_account_id: UUID,
    target_seats: int,
    expected_version: int,
    preview_id: str | None,
    now: datetime,
    request_id: str,
    stripe: StripeBilling,
) -> SeatProjection:
    _validate_version_and_no_open_change(
        session,
        organization=organization,
        expected_version=expected_version,
    )
    projection = seat_projection(session, organization)
    if target_seats < projection.occupied + projection.reserved:
        raise HTTPException(
            status_code=409,
            detail=(
                "seat capacity cannot be lower than occupied plus reserved seats"
            ),
        )
    if target_seats == organization.purchased_seats:
        raise HTTPException(status_code=422, detail="seat quantity is unchanged")
    if not organization.stripe_subscription_id:
        raise HTTPException(status_code=409, detail="subscription is not active")

    kind = (
        SeatChangeKind.INCREASE
        if target_seats > organization.purchased_seats
        else SeatChangeKind.DECREASE
    )
    preview = None
    if kind is SeatChangeKind.INCREASE:
        preview = _confirmed_preview(
            session,
            organization=organization,
            preview_id=preview_id,
            target_seats=target_seats,
            now=now,
        )
    change = OrganizationSeatChange(
        id=uuid4(),
        organization_id=organization.id,
        requested_by_user_account_id=requested_by_user_account_id,
        kind=kind.value,
        status=(
            SeatChangeStatus.PENDING_PAYMENT.value
            if kind is SeatChangeKind.INCREASE
            else SeatChangeStatus.SCHEDULED.value
        ),
        from_quantity=organization.purchased_seats,
        target_quantity=target_seats,
        stripe_reference=None,
        effective_at=None,
    )
    session.add(change)
    session.flush()
    provider_request = SeatChangeRequest(
        change_id=str(change.id),
        organization_id=str(organization.id),
        subscription_id=organization.stripe_subscription_id,
        current_seats=organization.purchased_seats,
        target_seats=target_seats,
        proration_date=preview.proration_date if preview else None,
    )
    result: SeatChangeResult
    if kind is SeatChangeKind.INCREASE:
        result = stripe.request_seat_increase(provider_request)
    else:
        result = stripe.schedule_seat_decrease(provider_request)
    change.stripe_reference = result.reference
    change.effective_at = result.effective_at
    if preview is not None:
        preview.consumed_at = now
    organization.seat_version += 1
    record_audit_event(
        session,
        AuditEventDraft(
            action="organization.seat_change_requested",
            target_type="organization_seat_change",
            target_id=change.id,
            request_id=request_id,
            change_summary={
                "kind": change.kind,
                "from_quantity": change.from_quantity,
                "target_quantity": change.target_quantity,
                "status": change.status,
                "preview_id": preview_id,
            },
        ),
    )
    return seat_projection(session, organization)


def apply_seat_event(
    session: Session,
    *,
    organization: Organization,
    event: StripeEvent,
    now: datetime,
    request_id: str,
) -> str:
    try:
        change_id = UUID(event.seat_change_id or "")
    except ValueError:
        return "ignored"
    change = session.scalar(
        select(OrganizationSeatChange)
        .where(
            OrganizationSeatChange.id == change_id,
            OrganizationSeatChange.organization_id == organization.id,
        )
        .with_for_update()
    )
    if change is None or change.status not in {
        SeatChangeStatus.PENDING_PAYMENT.value,
        SeatChangeStatus.SCHEDULED.value,
    }:
        return "ignored"
    if event.subscription_id != organization.stripe_subscription_id:
        return "ignored"
    if event.type == "customer.subscription.pending_update_expired":
        if change.status != SeatChangeStatus.PENDING_PAYMENT.value:
            return "ignored"
        change.status = SeatChangeStatus.FAILED.value
        organization.seat_version += 1
        record_audit_event(
            session,
            AuditEventDraft(
                action="organization.seat_change_failed",
                target_type="organization_seat_change",
                target_id=change.id,
                request_id=request_id,
                change_summary={
                    "from_quantity": change.from_quantity,
                    "target_quantity": change.target_quantity,
                    "reason": "stripe_pending_update_expired",
                },
            ),
        )
        return "seat_change_failed"
    if (
        event.type
        not in {
            "customer.subscription.updated",
            "customer.subscription.pending_update_applied",
        }
        or event.payment_status != "paid"
        or event.quantity != change.target_quantity
    ):
        return "ignored"
    projection = seat_projection(session, organization)
    if change.target_quantity < projection.occupied + projection.reserved:
        return "ignored"
    if (
        change.status == SeatChangeStatus.SCHEDULED.value
        and change.effective_at is not None
        and (event.created_at is None or event.created_at < change.effective_at)
    ):
        return "ignored"
    organization.purchased_seats = change.target_quantity
    organization.seat_version += 1
    change.status = SeatChangeStatus.APPLIED.value
    change.applied_at = now
    record_audit_event(
        session,
        AuditEventDraft(
            action="organization.seat_change_applied",
            target_type="organization_seat_change",
            target_id=change.id,
            request_id=request_id,
            change_summary={
                "from_quantity": change.from_quantity,
                "purchased_seats": change.target_quantity,
            },
        ),
    )
    return "seat_change_applied"


def _confirmed_preview(
    session: Session,
    *,
    organization: Organization,
    preview_id: str | None,
    target_seats: int,
    now: datetime,
) -> OrganizationSeatPreview:
    try:
        parsed_id = UUID(preview_id or "")
    except ValueError as error:
        raise HTTPException(
            status_code=422,
            detail="a valid Stripe proration preview is required",
        ) from error
    preview = session.scalar(
        select(OrganizationSeatPreview)
        .where(
            OrganizationSeatPreview.id == parsed_id,
            OrganizationSeatPreview.organization_id == organization.id,
        )
        .with_for_update()
    )
    if (
        preview is None
        or preview.consumed_at is not None
        or preview.expires_at <= now
        or preview.seat_version != organization.seat_version
        or preview.from_quantity != organization.purchased_seats
        or preview.target_quantity != target_seats
    ):
        raise HTTPException(
            status_code=409,
            detail="seat preview is stale; request a new preview",
        )
    return preview


def _validate_version_and_no_open_change(
    session: Session,
    *,
    organization: Organization,
    expected_version: int,
) -> None:
    if organization.seat_version != expected_version:
        raise HTTPException(
            status_code=409,
            detail="seat capacity changed; reload and try again",
        )
    open_change = session.scalar(
        select(OrganizationSeatChange.id).where(
            OrganizationSeatChange.organization_id == organization.id,
            OrganizationSeatChange.status.in_(
                [
                    SeatChangeStatus.PENDING_PAYMENT.value,
                    SeatChangeStatus.SCHEDULED.value,
                ]
            ),
        )
    )
    if open_change is not None:
        raise HTTPException(
            status_code=409,
            detail="a seat capacity change is already pending",
        )
