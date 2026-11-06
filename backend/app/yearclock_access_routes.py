from contextlib import contextmanager
from uuid import UUID, uuid4
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker
from app.audit import AuditEventDraft, record_audit_event
from app.auth import AuthenticatedUser
from app.auth_routes import AuthenticatedUserDependency
from app.database import RequestContext, apply_request_context, transaction_session
from app.models import Group, OrganizationMembership, OrganizationRole, Yearclock, YearclockAccessGrant, YearclockGroupGrant
from app.lifecycle import live_yearclock
from app.access import group_scope
from app.notifications import AccessWatch
from app.subscription_access import require_organization_mutation_access

class GrantRequest(BaseModel):
    user_account_id: UUID
    role: str
    expected_version: int | None = None
class GrantResponse(BaseModel):
    id: UUID; user_account_id: UUID; role: str; version: int

class GroupGrantRequest(BaseModel):
    group_id: UUID
    role: Literal["editor", "viewer"]
    expected_version: int | None = Field(default=None, ge=1)

class GroupGrantResponse(BaseModel):
    group_id: UUID; name: str; role: str; version: int

class OrganizationAccessRequest(BaseModel):
    role: Literal["none", "viewer", "editor"]
    expected_version: int = Field(ge=1)
    confirm: bool = False

class OrganizationAccessResponse(BaseModel):
    id: UUID; organization_access: str; version: int

def create_yearclock_access_router(*, session_factory: sessionmaker[Session], authenticated_user_dependency: AuthenticatedUserDependency) -> APIRouter:
    router = APIRouter(prefix="/api/v1/organizations", tags=["Yearclock access"])
    @router.get("/{organization_id}/yearclocks/{yearclock_id}/access", response_model=list[GrantResponse])
    def list_grants(organization_id: UUID, yearclock_id: UUID, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> list[GrantResponse]:
        with transaction_session(session_factory, RequestContext(user_account_id=user.account.id)) as session:
            actor = session.scalar(select(OrganizationMembership).where(OrganizationMembership.organization_id == organization_id, OrganizationMembership.user_account_id == user.account.id))
            if actor is None or actor.role not in {OrganizationRole.OWNER.value, OrganizationRole.ADMIN.value}:
                raise HTTPException(status_code=403, detail="Yearclock management role required")
            apply_request_context(session, RequestContext(user_account_id=user.account.id, organization_id=organization_id))
            live_yearclock(session, organization_id, yearclock_id)
            grants = session.scalars(select(YearclockAccessGrant).where(YearclockAccessGrant.organization_id == organization_id, YearclockAccessGrant.yearclock_id == yearclock_id).order_by(YearclockAccessGrant.created_at)).all()
            return [GrantResponse(id=item.id, user_account_id=item.user_account_id, role=item.role, version=item.version) for item in grants]
    @router.put("/{organization_id}/yearclocks/{yearclock_id}/access", response_model=GrantResponse)
    def grant(organization_id: UUID, yearclock_id: UUID, body: GrantRequest, request: Request, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> GrantResponse:
        if body.role not in {"editor", "viewer"}: raise HTTPException(status_code=422, detail="role must be editor or viewer")
        with transaction_session(session_factory, RequestContext(user_account_id=user.account.id)) as session:
            actor = session.scalar(select(OrganizationMembership).where(OrganizationMembership.organization_id == organization_id, OrganizationMembership.user_account_id == user.account.id))
            if actor is None or actor.role not in {OrganizationRole.OWNER.value, OrganizationRole.ADMIN.value}: raise HTTPException(status_code=403, detail="Yearclock management role required")
            apply_request_context(session, RequestContext(user_account_id=user.account.id, organization_id=organization_id))
            require_organization_mutation_access(session, organization_id)
            live_yearclock(session, organization_id, yearclock_id)
            if session.scalar(select(OrganizationMembership).where(OrganizationMembership.organization_id == organization_id, OrganizationMembership.user_account_id == body.user_account_id)) is None: raise HTTPException(status_code=422, detail="user is not an Organization member")
            watch = AccessWatch(session, organization_id, actor_id=user.account.id, yearclock_ids=[yearclock_id], user_ids=[body.user_account_id])
            item = session.scalar(select(YearclockAccessGrant).where(YearclockAccessGrant.yearclock_id == yearclock_id, YearclockAccessGrant.user_account_id == body.user_account_id))
            if item is None: item = YearclockAccessGrant(id=uuid4(), organization_id=organization_id, yearclock_id=yearclock_id, user_account_id=body.user_account_id, role=body.role, version=1); session.add(item)
            else:
                if body.expected_version != item.version: raise HTTPException(status_code=409, detail={"latest_version": item.version})
                item.role = body.role; item.version += 1
            record_audit_event(session, AuditEventDraft(action="yearclock.access_granted", target_type="yearclock_access_grant", target_id=item.id, request_id=(request.headers.get("X-Request-ID") or str(uuid4()))[:120], change_summary={"role": item.role}))
            watch.finish()
            return GrantResponse(id=item.id, user_account_id=item.user_account_id, role=item.role, version=item.version)
    @router.delete("/{organization_id}/yearclocks/{yearclock_id}/access/{user_account_id}", status_code=204)
    def revoke(organization_id: UUID, yearclock_id: UUID, user_account_id: UUID, request: Request, expected_version: int = Query(ge=1), user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> None:
        with transaction_session(session_factory, RequestContext(user_account_id=user.account.id)) as session:
            actor = session.scalar(select(OrganizationMembership).where(OrganizationMembership.organization_id == organization_id, OrganizationMembership.user_account_id == user.account.id))
            if actor is None or actor.role not in {OrganizationRole.OWNER.value, OrganizationRole.ADMIN.value}: raise HTTPException(status_code=403, detail="Yearclock management role required")
            apply_request_context(session, RequestContext(user_account_id=user.account.id, organization_id=organization_id))
            require_organization_mutation_access(session, organization_id)
            item = session.scalar(select(YearclockAccessGrant).where(YearclockAccessGrant.organization_id == organization_id, YearclockAccessGrant.yearclock_id == yearclock_id, YearclockAccessGrant.user_account_id == user_account_id))
            if item is None: raise HTTPException(status_code=404, detail="access grant not found")
            if expected_version != item.version: raise HTTPException(status_code=409, detail={"latest_version": item.version})
            watch = AccessWatch(session, organization_id, actor_id=user.account.id, yearclock_ids=[yearclock_id], user_ids=[user_account_id])
            record_audit_event(session, AuditEventDraft(action="yearclock.access_revoked", target_type="yearclock_access_grant", target_id=item.id, request_id=(request.headers.get("X-Request-ID") or str(uuid4()))[:120], change_summary={"role": item.role}))
            session.delete(item)
            watch.finish()
    @router.put("/{organization_id}/yearclocks/{yearclock_id}/organization-access", response_model=OrganizationAccessResponse)
    def set_organization_access(organization_id: UUID, yearclock_id: UUID, body: OrganizationAccessRequest, request: Request, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> OrganizationAccessResponse:
        """Share a Yearclock with every member, including future ones (V2 P10a)."""
        with transaction_session(session_factory, RequestContext(user_account_id=user.account.id)) as session:
            actor = session.scalar(select(OrganizationMembership).where(OrganizationMembership.organization_id == organization_id, OrganizationMembership.user_account_id == user.account.id))
            if actor is None or actor.role not in {OrganizationRole.OWNER.value, OrganizationRole.ADMIN.value}: raise HTTPException(status_code=403, detail="Yearclock management role required")
            apply_request_context(session, RequestContext(user_account_id=user.account.id, organization_id=organization_id))
            require_organization_mutation_access(session, organization_id)
            live_yearclock(session, organization_id, yearclock_id)
            clock = session.scalar(select(Yearclock).where(Yearclock.id == yearclock_id, Yearclock.organization_id == organization_id).with_for_update())
            if body.expected_version != clock.version: raise HTTPException(status_code=409, detail={"latest_version": clock.version})
            if body.role == "editor" and clock.organization_access != "editor" and not body.confirm:
                members = session.scalar(select(func.count()).select_from(OrganizationMembership).where(OrganizationMembership.organization_id == organization_id, OrganizationMembership.role == OrganizationRole.MEMBER.value)) or 0
                raise HTTPException(status_code=409, detail={"reason": "confirmation_required", "members": members})
            watch = AccessWatch(session, organization_id, actor_id=user.account.id, yearclock_ids=[yearclock_id])
            if clock.organization_access != body.role:
                record_audit_event(session, AuditEventDraft(action="yearclock.organization_access_changed", target_type="yearclock", target_id=clock.id, request_id=(request.headers.get("X-Request-ID") or str(uuid4()))[:120], change_summary={"from": clock.organization_access, "to": body.role}))
                clock.organization_access = body.role
                clock.version += 1
            watch.finish()
            return OrganizationAccessResponse(id=clock.id, organization_access=clock.organization_access, version=clock.version)
    @router.get("/{organization_id}/yearclocks/{yearclock_id}/group-access", response_model=list[GroupGrantResponse])
    def list_group_grants(organization_id: UUID, yearclock_id: UUID, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> list[GroupGrantResponse]:
        with _manager(session_factory, organization_id, user, mutate=False) as session:
            live_yearclock(session, organization_id, yearclock_id)
            rows = session.execute(select(YearclockGroupGrant, Group.name).join(Group, Group.id == YearclockGroupGrant.group_id).where(YearclockGroupGrant.yearclock_id == yearclock_id).order_by(func.lower(Group.name))).all()
            return [GroupGrantResponse(group_id=grant.group_id, name=name, role=grant.role, version=grant.version) for grant, name in rows]

    @router.put("/{organization_id}/yearclocks/{yearclock_id}/group-access", response_model=GroupGrantResponse)
    def grant_group(organization_id: UUID, yearclock_id: UUID, body: GroupGrantRequest, request: Request, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> GroupGrantResponse:
        """Give a Group Editor or Viewer access to a Yearclock (V2 P10a)."""
        with _manager(session_factory, organization_id, user, mutate=True) as session:
            live_yearclock(session, organization_id, yearclock_id)
            group = session.scalar(select(Group).where(Group.id == body.group_id, Group.organization_id == organization_id))
            if group is None: raise HTTPException(status_code=422, detail="Group not found in this Organization")
            watch = AccessWatch(session, organization_id, actor_id=user.account.id, yearclock_ids=[yearclock_id], user_ids=group_scope(session, group.id)[1])
            item = session.scalar(select(YearclockGroupGrant).where(YearclockGroupGrant.yearclock_id == yearclock_id, YearclockGroupGrant.group_id == group.id).with_for_update())
            if item is None:
                item = YearclockGroupGrant(id=uuid4(), organization_id=organization_id, yearclock_id=yearclock_id, group_id=group.id, role=body.role, version=1); session.add(item)
            else:
                if body.expected_version != item.version: raise HTTPException(status_code=409, detail={"latest_version": item.version})
                item.role = body.role; item.version += 1
            record_audit_event(session, AuditEventDraft(action="yearclock.group_access_granted", target_type="yearclock", target_id=yearclock_id, request_id=(request.headers.get("X-Request-ID") or str(uuid4()))[:120], change_summary={"group": group.name, "role": item.role}))
            watch.finish()
            return GroupGrantResponse(group_id=group.id, name=group.name, role=item.role, version=item.version)

    @router.delete("/{organization_id}/yearclocks/{yearclock_id}/group-access/{group_id}", status_code=204)
    def revoke_group(organization_id: UUID, yearclock_id: UUID, group_id: UUID, request: Request, expected_version: int = Query(ge=1), user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> None:
        with _manager(session_factory, organization_id, user, mutate=True) as session:
            item = session.scalar(select(YearclockGroupGrant).where(YearclockGroupGrant.yearclock_id == yearclock_id, YearclockGroupGrant.group_id == group_id).with_for_update())
            if item is None: raise HTTPException(status_code=404, detail="Group access not found")
            if expected_version != item.version: raise HTTPException(status_code=409, detail={"latest_version": item.version})
            group = session.get(Group, group_id)
            watch = AccessWatch(session, organization_id, actor_id=user.account.id, yearclock_ids=[yearclock_id], user_ids=group_scope(session, group_id)[1])
            record_audit_event(session, AuditEventDraft(action="yearclock.group_access_revoked", target_type="yearclock", target_id=yearclock_id, request_id=(request.headers.get("X-Request-ID") or str(uuid4()))[:120], change_summary={"group": group.name if group else None, "role": item.role}))
            session.delete(item)
            watch.finish()

    return router


@contextmanager
def _manager(factory: sessionmaker[Session], organization_id: UUID, user: AuthenticatedUser, *, mutate: bool):
    with transaction_session(factory, RequestContext(user_account_id=user.account.id)) as session:
        actor = session.scalar(select(OrganizationMembership).where(OrganizationMembership.organization_id == organization_id, OrganizationMembership.user_account_id == user.account.id))
        if actor is None or actor.role not in {OrganizationRole.OWNER.value, OrganizationRole.ADMIN.value}: raise HTTPException(status_code=403, detail="Yearclock management role required")
        apply_request_context(session, RequestContext(user_account_id=user.account.id, organization_id=organization_id))
        if mutate: require_organization_mutation_access(session, organization_id)
        yield session
