"""Groups (Yearclock V2, P10a ticket 03).

Owners and Admins manage Groups; every member sees their own. Groups are
flat, take no seats, and only add access (ADR-0007).
"""
from contextlib import contextmanager
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.access import group_deletion_impact, group_access
from app.audit import AuditEventDraft, record_audit_event
from app.auth import AuthenticatedUser
from app.auth_routes import AuthenticatedUserDependency
from app.database import RequestContext, apply_request_context, transaction_session
from app.limits import require_group_capacity
from app.access import group_scope
from app.notifications import AccessWatch, membership_user
from app.models import Group, GroupMember, OrganizationMembership, OrganizationRole, UserAccount
from app.subscription_access import require_organization_mutation_access

MANAGERS = {OrganizationRole.OWNER.value, OrganizationRole.ADMIN.value}


class GroupRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    expected_version: int | None = Field(default=None, ge=1)

    @field_validator("name")
    @classmethod
    def trimmed(cls, value: str) -> str:
        if not (value := " ".join(value.split())): raise ValueError("must not be blank")
        return value


class GroupMemberResponse(BaseModel):
    membership_id: UUID
    name: str
    email: str


class GroupResponse(BaseModel):
    id: UUID
    name: str
    version: int
    members: list[GroupMemberResponse]


class OwnGroupAccess(BaseModel):
    yearclock_id: UUID
    yearclock_name: str
    role: str


class OwnGroup(BaseModel):
    id: UUID
    name: str
    access: list[OwnGroupAccess]


def create_group_router(*, session_factory: sessionmaker[Session], authenticated_user_dependency: AuthenticatedUserDependency) -> APIRouter:
    router = APIRouter(prefix="/api/v1/organizations", tags=["Groups"])

    @router.get("/{organization_id}/groups", response_model=list[GroupResponse])
    def list_groups(organization_id: UUID, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> list[GroupResponse]:
        with _session(session_factory, organization_id, user, manage=True, mutate=False) as (session, _):
            return [_response(session, item) for item in session.scalars(select(Group).where(Group.organization_id == organization_id).order_by(func.lower(Group.name))).all()]

    @router.post("/{organization_id}/groups", response_model=GroupResponse, status_code=201)
    def create(organization_id: UUID, body: GroupRequest, request: Request, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> GroupResponse:
        with _session(session_factory, organization_id, user, manage=True, mutate=True) as (session, _):
            require_group_capacity(session, organization_id)
            _refuse_duplicate(session, organization_id, body.name, None)
            item = Group(id=uuid4(), organization_id=organization_id, name=body.name, version=1)
            session.add(item); session.flush()
            _audit(session, request, "group.created", item.id, {"name": item.name})
            return _response(session, item)

    @router.patch("/{organization_id}/groups/{group_id}", response_model=GroupResponse)
    def rename(organization_id: UUID, group_id: UUID, body: GroupRequest, request: Request, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> GroupResponse:
        with _session(session_factory, organization_id, user, manage=True, mutate=True) as (session, _):
            item = _group(session, organization_id, group_id, body.expected_version)
            _refuse_duplicate(session, organization_id, body.name, item.id)
            if item.name != body.name:
                _audit(session, request, "group.renamed", item.id, {"from": item.name, "to": body.name})
                item.name = body.name; item.version += 1
            return _response(session, item)

    @router.delete("/{organization_id}/groups/{group_id}", status_code=204)
    def delete(organization_id: UUID, group_id: UUID, request: Request, expected_version: int = Query(ge=1), confirm: bool = Query(False), user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> None:
        with _session(session_factory, organization_id, user, manage=True, mutate=True) as (session, _):
            item = _group(session, organization_id, group_id, expected_version)
            impact = group_deletion_impact(session, item)
            if not confirm and (impact["members"] or impact["yearclocks"]):
                raise HTTPException(status_code=409, detail={"reason": "confirmation_required", **impact})
            granted, members = group_scope(session, item.id)
            watch = AccessWatch(session, organization_id, actor_id=user.account.id, yearclock_ids=granted, user_ids=members)
            _audit(session, request, "group.deleted", item.id, {"name": item.name, "members": impact["members"], "yearclocks": impact["yearclocks"]})
            session.delete(item)
            watch.finish()

    @router.put("/{organization_id}/groups/{group_id}/members/{membership_id}", response_model=GroupResponse)
    def add_member(organization_id: UUID, group_id: UUID, membership_id: UUID, request: Request, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> GroupResponse:
        with _session(session_factory, organization_id, user, manage=True, mutate=True) as (session, _):
            item = _group(session, organization_id, group_id, None)
            watch = AccessWatch(session, organization_id, actor_id=user.account.id, yearclock_ids=group_scope(session, group_id)[0], user_ids=[membership_user(session, membership_id)])
            if session.scalar(select(OrganizationMembership.id).where(OrganizationMembership.id == membership_id, OrganizationMembership.organization_id == organization_id)) is None:
                raise HTTPException(status_code=422, detail="not a member of this Organization")
            if session.get(GroupMember, (group_id, membership_id)) is None:
                session.add(GroupMember(group_id=group_id, membership_id=membership_id, organization_id=organization_id)); item.version += 1
                _audit(session, request, "group.member_added", item.id, {"name": item.name, "membership_id": str(membership_id)})
            watch.finish()
            return _response(session, item)

    @router.delete("/{organization_id}/groups/{group_id}/members/{membership_id}", response_model=GroupResponse)
    def remove_member(organization_id: UUID, group_id: UUID, membership_id: UUID, request: Request, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> GroupResponse:
        with _session(session_factory, organization_id, user, manage=True, mutate=True) as (session, _):
            item = _group(session, organization_id, group_id, None)
            watch = AccessWatch(session, organization_id, actor_id=user.account.id, yearclock_ids=group_scope(session, group_id)[0], user_ids=[membership_user(session, membership_id)])
            member = session.get(GroupMember, (group_id, membership_id))
            if member is not None:
                session.delete(member); item.version += 1
                _audit(session, request, "group.member_removed", item.id, {"name": item.name, "membership_id": str(membership_id)})
            watch.finish()
            return _response(session, item)

    @router.get("/{organization_id}/me/groups", response_model=list[OwnGroup])
    def own_groups(organization_id: UUID, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> list[OwnGroup]:
        """The member's own Groups and the Yearclock access each gives; other Groups stay hidden."""
        with _session(session_factory, organization_id, user, manage=False, mutate=False) as (session, membership):
            groups = session.scalars(select(Group).join(GroupMember, GroupMember.group_id == Group.id).where(GroupMember.membership_id == membership.id).order_by(func.lower(Group.name))).all()
            return [OwnGroup(id=item.id, name=item.name, access=[OwnGroupAccess(**entry) for entry in group_access(session, item)]) for item in groups]

    return router


@contextmanager
def _session(factory: sessionmaker[Session], organization_id: UUID, user: AuthenticatedUser, *, manage: bool, mutate: bool):
    with transaction_session(factory, RequestContext(user_account_id=user.account.id)) as session:
        membership = session.scalar(select(OrganizationMembership).where(OrganizationMembership.organization_id == organization_id, OrganizationMembership.user_account_id == user.account.id))
        if membership is None: raise HTTPException(status_code=404, detail="Organization not found")
        if manage and membership.role not in MANAGERS: raise HTTPException(status_code=403, detail="Owner or Admin role required")
        apply_request_context(session, RequestContext(user_account_id=user.account.id, organization_id=organization_id))
        if mutate: require_organization_mutation_access(session, organization_id)
        yield session, membership


def _group(session: Session, organization_id: UUID, group_id: UUID, expected_version: int | None) -> Group:
    item = session.scalar(select(Group).where(Group.id == group_id, Group.organization_id == organization_id).with_for_update())
    if item is None: raise HTTPException(status_code=404, detail="Group not found")
    if expected_version is not None and expected_version != item.version: raise HTTPException(status_code=409, detail={"latest_version": item.version})
    return item


def _refuse_duplicate(session: Session, organization_id: UUID, name: str, own_id: UUID | None) -> None:
    other = session.scalar(select(Group.id).where(Group.organization_id == organization_id, func.lower(Group.name) == name.lower()))
    if other is not None and other != own_id: raise HTTPException(status_code=409, detail={"reason": "duplicate_name"})


def _response(session: Session, item: Group) -> GroupResponse:
    rows = session.execute(select(OrganizationMembership.id, UserAccount.display_name, UserAccount.email).join(GroupMember, GroupMember.membership_id == OrganizationMembership.id).join(UserAccount, UserAccount.id == OrganizationMembership.user_account_id).where(GroupMember.group_id == item.id).order_by(func.lower(UserAccount.display_name))).all()
    return GroupResponse(id=item.id, name=item.name, version=item.version, members=[GroupMemberResponse(membership_id=row[0], name=row[1] or row[2], email=row[2]) for row in rows])


def _audit(session: Session, request: Request, action: str, target_id: UUID, summary: dict) -> None:
    record_audit_event(session, AuditEventDraft(action=action, target_type="group", target_id=target_id, request_id=(request.headers.get("X-Request-ID") or str(uuid4()))[:120], change_summary=summary))
