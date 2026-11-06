"""The access overview (Yearclock V2, P10a ticket 06).

Answers "who can open what, and why" for Owners and Admins, straight from
the single access rule in ``app.access``.
"""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.access import yearclock_access
from app.auth import AuthenticatedUser
from app.auth_routes import AuthenticatedUserDependency
from app.group_routes import _session
from app.models import OrganizationMembership, UserAccount, Yearclock


class AccessSourceResponse(BaseModel):
    kind: str
    role: str
    organization_role: str | None = None
    group_id: UUID | None = None
    group_name: str | None = None


class PersonYearclock(BaseModel):
    id: UUID
    name: str
    archived: bool
    role: str
    sources: list[AccessSourceResponse]


class Person(BaseModel):
    membership_id: UUID
    name: str
    email: str
    organization_role: str


class PersonOverview(BaseModel):
    person: Person
    yearclocks: list[PersonYearclock]


class YearclockPerson(Person):
    role: str
    sources: list[AccessSourceResponse]


class YearclockOverview(BaseModel):
    id: UUID
    name: str
    people: list[YearclockPerson]


def create_access_overview_router(*, session_factory: sessionmaker[Session], authenticated_user_dependency: AuthenticatedUserDependency) -> APIRouter:
    router = APIRouter(prefix="/api/v1/organizations", tags=["Access overview"])

    @router.get("/{organization_id}/access-overview/people/{membership_id}", response_model=PersonOverview)
    def person(organization_id: UUID, membership_id: UUID, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> PersonOverview:
        with _session(session_factory, organization_id, user, manage=True, mutate=False) as (session, _):
            membership = session.scalar(select(OrganizationMembership).where(OrganizationMembership.id == membership_id, OrganizationMembership.organization_id == organization_id))
            if membership is None: raise HTTPException(status_code=404, detail="membership not found")
            access = yearclock_access(session, membership)
            clocks = session.scalars(select(Yearclock).where(Yearclock.id.in_(access.keys())).order_by(Yearclock.display_order, Yearclock.id)).all()
            return PersonOverview(person=_person(session, membership), yearclocks=[PersonYearclock(id=clock.id, name=clock.name, archived=clock.archived_at is not None, role=access[clock.id].role, sources=access[clock.id].sources) for clock in clocks])

    @router.get("/{organization_id}/access-overview/yearclocks/{yearclock_id}", response_model=YearclockOverview)
    def yearclock(organization_id: UUID, yearclock_id: UUID, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> YearclockOverview:
        with _session(session_factory, organization_id, user, manage=True, mutate=False) as (session, _):
            clock = session.scalar(select(Yearclock).where(Yearclock.id == yearclock_id, Yearclock.organization_id == organization_id, Yearclock.deleted_at.is_(None)))
            if clock is None: raise HTTPException(status_code=404, detail="Yearclock not found")
            people = []
            for membership in session.scalars(select(OrganizationMembership).join(UserAccount, UserAccount.id == OrganizationMembership.user_account_id).where(OrganizationMembership.organization_id == organization_id).order_by(func.lower(UserAccount.display_name))).all():
                access = yearclock_access(session, membership, [clock.id]).get(clock.id)
                if access:
                    people.append(YearclockPerson(**_person(session, membership).model_dump(), role=access.role, sources=access.sources))
            return YearclockOverview(id=clock.id, name=clock.name, people=people)

    return router


def _person(session: Session, membership: OrganizationMembership) -> Person:
    account = session.get(UserAccount, membership.user_account_id)
    return Person(membership_id=membership.id, name=(account.display_name or account.email) if account else "", email=account.email if account else "", organization_role=membership.role)
