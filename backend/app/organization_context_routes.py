from collections.abc import Iterator
from dataclasses import asdict
from datetime import datetime
from contextlib import contextmanager
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import and_, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, sessionmaker

from app.auth import AuthenticatedUser
from app.auth_routes import AuthenticatedUserDependency
from app.database import (
    RequestContext,
    apply_request_context,
    transaction_session,
)
from app.lifecycle import organization_purge_after
from app.subscription_access import subscription_view
from app.access import role_on, yearclock_access
from app.yearclock_reading import LinkSource, link_sources
from app.models import (
    Lane,
    Organization,
    OrganizationMembership,
    OrganizationRole,
    OrganizationStatus,
    Yearclock,
    YearclockVisit,
)


class OrganizationSummaryResponse(BaseModel):
    id: UUID
    name: str
    role: str
    status: str = OrganizationStatus.ACTIVE.value
    purge_after: datetime | None = None


class OrganizationListResponse(BaseModel):
    organizations: list[OrganizationSummaryResponse]


class LaneSummaryResponse(BaseModel):
    id: UUID
    name: str
    display_order: int
    version: int
    tint: str | None = None
    height: str = "normal"
    source_lane_id: UUID | None = None
    source: LinkSource | None = None


class VisitResponse(BaseModel):
    previous_visited_at: datetime | None


class YearclockSummaryResponse(BaseModel):
    id: UUID
    name: str
    version: int
    access_role: str
    lanes: list[LaneSummaryResponse]
    start_month: int = 1
    show_week_ring: bool = False
    show_quarter_ring: bool = False


class MembershipResponse(BaseModel):
    role: str


class OrganizationIdentityResponse(BaseModel):
    id: UUID
    name: str
    time_zone: str


class SubscriptionResponse(BaseModel):
    state: str
    writable: bool
    grace_expires_at: datetime | None
    cancel_at_period_end: bool
    current_period_end: datetime | None
    ended: bool = False


class OrganizationWorkspaceResponse(BaseModel):
    organization: OrganizationIdentityResponse
    membership: MembershipResponse
    subscription: SubscriptionResponse
    yearclocks: list[YearclockSummaryResponse]
    recent_yearclock_ids: list[UUID] = []


RECENT_YEARCLOCKS = 5


def create_organization_context_router(
    *,
    session_factory: sessionmaker[Session],
    authenticated_user_dependency: AuthenticatedUserDependency,
) -> APIRouter:
    router = APIRouter(
        prefix="/api/v1/organizations",
        tags=["organization context"],
    )

    @router.get("", response_model=OrganizationListResponse)
    def list_organizations(
        authenticated_user: AuthenticatedUser = Depends(
            authenticated_user_dependency
        ),
    ) -> OrganizationListResponse:
        return organizations_of(session_factory, authenticated_user)

    @router.get(
        "/{organization_id}",
        response_model=OrganizationWorkspaceResponse,
    )
    def organization_workspace(
        organization_id: UUID,
        authenticated_user: AuthenticatedUser = Depends(
            authenticated_user_dependency
        ),
    ) -> OrganizationWorkspaceResponse:
        with _organization_session(
            session_factory,
            organization_id=organization_id,
            authenticated_user=authenticated_user,
        ) as (session, membership):
            organization = session.scalar(
                select(Organization).where(
                    Organization.id == organization_id,
                    Organization.status == OrganizationStatus.ACTIVE.value,
                )
            )
            if organization is None:
                raise _not_found()
            return OrganizationWorkspaceResponse(
                organization=OrganizationIdentityResponse(
                    id=organization.id,
                    name=organization.name,
                    time_zone=organization.time_zone,
                ),
                membership=MembershipResponse(role=membership.role),
                subscription=SubscriptionResponse(**asdict(subscription_view(organization))),
                yearclocks=(yearclocks := _yearclocks(
                    session,
                    organization_id,
                    membership,
                )),
                recent_yearclock_ids=_recent(session, membership, {item.id for item in yearclocks}),
            )

    @router.post("/{organization_id}/yearclocks/{yearclock_id}/visit", response_model=VisitResponse)
    def record_visit(
        organization_id: UUID,
        yearclock_id: UUID,
        authenticated_user: AuthenticatedUser = Depends(authenticated_user_dependency),
    ) -> VisitResponse:
        """Remember that the user opened this Yearclock; allowed while read-only, since it is navigation."""
        with _organization_session(
            session_factory,
            organization_id=organization_id,
            authenticated_user=authenticated_user,
        ) as (session, membership):
            yearclock = session.scalar(
                select(Yearclock).where(
                    Yearclock.id == yearclock_id,
                    Yearclock.organization_id == organization_id,
                    Yearclock.deleted_at.is_(None),
                )
            )
            if yearclock is None or not _may_access_yearclock(session, yearclock.id, membership):
                raise _not_found()
            statement = insert(YearclockVisit).values(membership_id=membership.id, yearclock_id=yearclock.id, organization_id=organization_id, user_account_id=membership.user_account_id, visited_at=func.now())
            previous = session.execute(
                statement.on_conflict_do_update(index_elements=["membership_id", "yearclock_id"], set_={"previous_visited_at": YearclockVisit.visited_at, "visited_at": func.now()}).returning(YearclockVisit.previous_visited_at)
            ).scalar_one()
            return VisitResponse(previous_visited_at=previous)

    @router.get(
        "/{organization_id}/yearclocks/{yearclock_id}",
        response_model=YearclockSummaryResponse,
    )
    def yearclock_detail(
        organization_id: UUID,
        yearclock_id: UUID,
        authenticated_user: AuthenticatedUser = Depends(
            authenticated_user_dependency
        ),
    ) -> YearclockSummaryResponse:
        return yearclock_detail_of(session_factory, organization_id, yearclock_id, authenticated_user)

    return router


def organizations_of(
    session_factory: sessionmaker[Session],
    authenticated_user: AuthenticatedUser,
) -> OrganizationListResponse:
    """The user's active Organization memberships; shared by the REST API and the MCP interface."""
    with transaction_session(
        session_factory,
        RequestContext(user_account_id=authenticated_user.account.id),
    ) as session:
        memberships = session.execute(
            select(OrganizationMembership, Organization)
            .join(
                Organization,
                Organization.id == OrganizationMembership.organization_id,
            )
            .where(
                OrganizationMembership.user_account_id
                == authenticated_user.account.id,
                or_(
                    Organization.status == OrganizationStatus.ACTIVE.value,
                    and_(
                        Organization.status == OrganizationStatus.PENDING_DELETION.value,
                        OrganizationMembership.role == OrganizationRole.OWNER.value,
                    ),
                ),
            )
            .order_by(Organization.name, Organization.id)
        ).all()
        return OrganizationListResponse(
            organizations=[
                OrganizationSummaryResponse(
                    id=organization.id,
                    name=organization.name,
                    role=membership.role,
                    status=organization.status,
                    purge_after=organization_purge_after(organization),
                )
                for membership, organization in memberships
            ]
        )


def yearclock_detail_of(
    session_factory: sessionmaker[Session],
    organization_id: UUID,
    yearclock_id: UUID,
    authenticated_user: AuthenticatedUser,
) -> YearclockSummaryResponse:
    """One Yearclock the user may open, with its Lanes; shared by the REST API and the MCP interface."""
    with _organization_session(
        session_factory,
        organization_id=organization_id,
        authenticated_user=authenticated_user,
    ) as (session, _membership):
        yearclock = session.scalar(
            select(Yearclock).where(
                Yearclock.id == yearclock_id,
                Yearclock.organization_id == organization_id,
                Yearclock.deleted_at.is_(None),
            )
        )
        if yearclock is None:
            raise _not_found()
        if not _may_access_yearclock(session, yearclock.id, _membership):
            raise _not_found()
        return _yearclock_response(session, yearclock, _membership)


def yearclocks_of(
    session_factory: sessionmaker[Session],
    organization_id: UUID,
    authenticated_user: AuthenticatedUser,
) -> list[YearclockSummaryResponse]:
    """The Yearclocks of one Organization the user may open; shared by the REST API and the MCP interface."""
    with _organization_session(
        session_factory,
        organization_id=organization_id,
        authenticated_user=authenticated_user,
    ) as (session, membership):
        organization = session.scalar(
            select(Organization).where(
                Organization.id == organization_id,
                Organization.status == OrganizationStatus.ACTIVE.value,
            )
        )
        if organization is None:
            raise _not_found()
        return _yearclocks(session, organization_id, membership)


@contextmanager
def _organization_session(
    session_factory: sessionmaker[Session],
    *,
    organization_id: UUID,
    authenticated_user: AuthenticatedUser,
) -> Iterator[tuple[Session, OrganizationMembership]]:
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
            raise _not_found()
        apply_request_context(
            session,
            RequestContext(
                user_account_id=authenticated_user.account.id,
                organization_id=organization_id,
            ),
        )
        yield session, membership


def _yearclocks(
    session: Session,
    organization_id: UUID,
    membership: OrganizationMembership,
) -> list[YearclockSummaryResponse]:
    statement = select(Yearclock).where(
        Yearclock.organization_id == organization_id,
        Yearclock.archived_at.is_(None),
        Yearclock.deleted_at.is_(None),
    )
    access = yearclock_access(session, membership)
    statement = statement.where(Yearclock.id.in_(access.keys()))
    yearclocks = session.scalars(statement.order_by(Yearclock.display_order, Yearclock.id)).all()
    return [_yearclock_response(session, yearclock, membership, access[yearclock.id].role) for yearclock in yearclocks]


def _recent(session: Session, membership: OrganizationMembership, accessible: set[UUID]) -> list[UUID]:
    """The user's most recently opened Yearclocks they can still open, newest first."""
    visited = session.scalars(
        select(YearclockVisit.yearclock_id)
        .where(YearclockVisit.membership_id == membership.id)
        .order_by(YearclockVisit.visited_at.desc())
    ).all()
    return [yearclock_id for yearclock_id in visited if yearclock_id in accessible][:RECENT_YEARCLOCKS]


def _may_access_yearclock(
    session: Session,
    yearclock_id: UUID,
    membership: OrganizationMembership,
) -> bool:
    return role_on(session, membership, yearclock_id) is not None


def _yearclock_response(
    session: Session,
    yearclock: Yearclock,
    membership: OrganizationMembership,
    role: str | None = None,
) -> YearclockSummaryResponse:
    lanes = session.scalars(
        select(Lane)
        .where(
            Lane.organization_id == yearclock.organization_id,
            Lane.yearclock_id == yearclock.id,
        )
        .order_by(Lane.display_order, Lane.id)
    ).all()
    sources = link_sources(session, yearclock.organization_id, membership.user_account_id, lanes)
    return YearclockSummaryResponse(
        id=yearclock.id,
        name=yearclock.name,
        version=yearclock.version,
        start_month=yearclock.start_month or 1,
        show_week_ring=bool(yearclock.show_week_ring),
        show_quarter_ring=bool(yearclock.show_quarter_ring),
        access_role=role if role is not None else role_on(session, membership, yearclock.id),
        lanes=[
            LaneSummaryResponse(id=lane.id, name=lane.name, display_order=lane.display_order, version=lane.version, tint=lane.tint, height=lane.height or "normal", source_lane_id=lane.source_lane_id, source=sources.get(lane.id))
            for lane in lanes
        ],
    )


def _not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="organization not found")
