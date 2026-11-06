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
from app.models import (
    Organization,
    OrganizationMembership,
    OrganizationRole,
    OrganizationStatus,
)


class OrganizationSummaryResponse(BaseModel):
    id: UUID
    name: str
    role: str
    status: str = OrganizationStatus.ACTIVE.value
    purge_after: datetime | None = None


class OrganizationListResponse(BaseModel):
    organizations: list[OrganizationSummaryResponse]


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
        return workspace_of(session_factory, organization_id, authenticated_user)

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


def workspace_of(
    session_factory: sessionmaker[Session],
    organization_id: UUID,
    authenticated_user: AuthenticatedUser,
) -> OrganizationWorkspaceResponse:
    """One Organization's identity, the caller's role in it, and its subscription."""
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
        )


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


def _not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="organization not found")
