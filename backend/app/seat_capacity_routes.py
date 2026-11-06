from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.auth import AuthenticatedUser
from app.auth_routes import AuthenticatedUserDependency
from app.billing import StripeBilling
from app.database import RequestContext, apply_request_context, transaction_session
from app.models import (
    Organization,
    OrganizationMembership,
    OrganizationRole,
    OrganizationStatus,
)
from app.seat_capacity import (
    SeatProjection,
    preview_increase,
    request_change,
    seat_projection,
)


class PendingSeatChangeResponse(BaseModel):
    id: UUID
    kind: str
    status: str
    target_seats: int
    effective_at: datetime | None


class SeatProjectionResponse(BaseModel):
    purchased: int
    occupied: int
    reserved: int
    available: int
    version: int
    pending_change: PendingSeatChangeResponse | None


class SeatIncreasePreviewBody(BaseModel):
    target_seats: int = Field(ge=1)
    expected_version: int = Field(ge=1)


class SeatIncreasePreviewResponse(BaseModel):
    preview_id: str
    target_seats: int
    amount_due: int
    currency: str
    proration_date: datetime


class SeatChangeBody(BaseModel):
    target_seats: int = Field(ge=0)
    expected_version: int = Field(ge=1)
    preview_id: str | None = Field(default=None, max_length=255)
    confirmed: bool


def create_seat_capacity_router(
    *,
    session_factory: sessionmaker[Session],
    authenticated_user_dependency: AuthenticatedUserDependency,
    stripe_billing: StripeBilling,
    clock,
) -> APIRouter:
    router = APIRouter(
        prefix="/api/v1/organizations/{organization_id}/billing/seats",
        tags=["organization billing"],
    )

    @router.get("", response_model=SeatProjectionResponse)
    def get_seats(
        organization_id: UUID,
        authenticated_user: AuthenticatedUser = Depends(
            authenticated_user_dependency
        ),
    ) -> SeatProjectionResponse:
        with _owner_session(
            session_factory,
            organization_id=organization_id,
            authenticated_user=authenticated_user,
        ) as (session, organization):
            return _projection_response(seat_projection(session, organization))

    @router.post(
        "/increase-preview",
        response_model=SeatIncreasePreviewResponse,
    )
    def increase_preview(
        organization_id: UUID,
        body: SeatIncreasePreviewBody,
        authenticated_user: AuthenticatedUser = Depends(
            authenticated_user_dependency
        ),
    ) -> SeatIncreasePreviewResponse:
        with _owner_session(
            session_factory,
            organization_id=organization_id,
            authenticated_user=authenticated_user,
        ) as (session, organization):
            preview = preview_increase(
                session,
                organization=organization,
                target_seats=body.target_seats,
                expected_version=body.expected_version,
                now=clock(),
                stripe=stripe_billing,
            )
            return SeatIncreasePreviewResponse(
                preview_id=str(preview.id),
                target_seats=body.target_seats,
                amount_due=preview.amount_due,
                currency=preview.currency,
                proration_date=preview.proration_date,
            )

    @router.post(
        "",
        response_model=SeatProjectionResponse,
        status_code=202,
    )
    def change_seats(
        organization_id: UUID,
        body: SeatChangeBody,
        request: Request,
        authenticated_user: AuthenticatedUser = Depends(
            authenticated_user_dependency
        ),
    ) -> SeatProjectionResponse:
        if not body.confirmed:
            raise HTTPException(status_code=422, detail="confirmation is required")
        with _owner_session(
            session_factory,
            organization_id=organization_id,
            authenticated_user=authenticated_user,
        ) as (session, organization):
            projection = request_change(
                session,
                organization=organization,
                requested_by_user_account_id=authenticated_user.account.id,
                target_seats=body.target_seats,
                expected_version=body.expected_version,
                preview_id=body.preview_id,
                now=clock(),
                request_id=(
                    request.headers.get("X-Request-ID") or str(uuid4())
                )[:120],
                stripe=stripe_billing,
            )
            return _projection_response(projection)

    return router


@contextmanager
def _owner_session(
    session_factory: sessionmaker[Session],
    *,
    organization_id: UUID,
    authenticated_user: AuthenticatedUser,
) -> Iterator[tuple[Session, Organization]]:
    with transaction_session(
        session_factory,
        RequestContext(user_account_id=authenticated_user.account.id),
    ) as session:
        membership = session.scalar(
            select(OrganizationMembership).where(
                OrganizationMembership.organization_id == organization_id,
                OrganizationMembership.user_account_id
                == authenticated_user.account.id,
            )
        )
        if membership is None:
            raise HTTPException(status_code=404, detail="organization not found")
        if membership.role != OrganizationRole.OWNER.value:
            raise HTTPException(status_code=403, detail="owner role required")
        apply_request_context(
            session,
            RequestContext(
                user_account_id=authenticated_user.account.id,
                organization_id=organization_id,
            ),
        )
        organization = session.scalar(
            select(Organization)
            .where(
                Organization.id == organization_id,
                Organization.status == OrganizationStatus.ACTIVE.value,
            )
            .with_for_update()
        )
        if organization is None:
            raise HTTPException(status_code=404, detail="organization not found")
        yield session, organization


def _projection_response(projection: SeatProjection) -> SeatProjectionResponse:
    change = projection.pending_change
    return SeatProjectionResponse(
        purchased=projection.purchased,
        occupied=projection.occupied,
        reserved=projection.reserved,
        available=projection.available,
        version=projection.version,
        pending_change=(
            PendingSeatChangeResponse(
                id=change.id,
                kind=change.kind,
                status=change.status,
                target_seats=change.target_quantity,
                effective_at=change.effective_at,
            )
            if change
            else None
        ),
    )
