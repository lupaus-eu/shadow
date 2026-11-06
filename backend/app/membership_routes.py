from contextlib import contextmanager
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.audit import AuditEventDraft, record_audit_event
from app.auth import AuthenticatedUser
from app.auth_routes import AuthenticatedUserDependency
from app.database import RequestContext, apply_request_context, transaction_session
from app.notifications import notify_role_change
from app.models import OrganizationMembership, OrganizationRole, UserAccount, YearclockAccessGrant
from app.subscription_access import require_organization_mutation_access


class MembershipResponse(BaseModel):
    id: UUID
    user_account_id: UUID
    email: str
    display_name: str
    role: str
    version: int


class TransferOwnershipRequest(BaseModel):
    expected_version: int
    keep_owner: bool = False


class LeaveRequest(BaseModel):
    successor_membership_id: UUID | None = None


class MembershipRoleRequest(BaseModel):
    role: OrganizationRole
    expected_version: int


def create_membership_router(*, session_factory: sessionmaker[Session], authenticated_user_dependency: AuthenticatedUserDependency) -> APIRouter:
    router = APIRouter(prefix="/api/v1/organizations", tags=["Organization memberships"])

    @router.get("/{organization_id}/memberships", response_model=list[MembershipResponse])
    def list_memberships(organization_id: UUID, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> list[MembershipResponse]:
        with _manager_session(session_factory, organization_id, user, mutate=False) as (session, _actor):
            memberships = session.scalars(select(OrganizationMembership).where(OrganizationMembership.organization_id == organization_id).order_by(OrganizationMembership.created_at)).all()
            return [_response(session, membership) for membership in memberships]

    @router.patch("/{organization_id}/memberships/{membership_id}", response_model=MembershipResponse)
    def change_role(organization_id: UUID, membership_id: UUID, body: MembershipRoleRequest, request: Request, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> MembershipResponse:
        with _manager_session(session_factory, organization_id, user) as (session, actor):
            target = session.get(OrganizationMembership, membership_id)
            if target is None or target.organization_id != organization_id:
                raise _not_found()
            if actor.role != OrganizationRole.OWNER.value and (
                target.role == OrganizationRole.OWNER.value
                or body.role == OrganizationRole.OWNER
            ):
                raise HTTPException(status_code=403, detail="only an Owner can manage ownership")
            if target.role == OrganizationRole.OWNER.value and body.role != OrganizationRole.OWNER and _owner_count(session, organization_id) == 1:
                raise HTTPException(status_code=409, detail="an Organization must retain an Owner")
            if body.expected_version != target.version:
                raise HTTPException(status_code=409, detail={"latest_version": target.version})
            previous_role = target.role
            target.role = body.role.value
            target.version += 1
            notify_role_change(session, organization_id, actor_id=user.account.id, target_user_id=target.user_account_id, from_role=previous_role, to_role=target.role)
            _audit(session, request, "organization.membership_role_changed", target, {"role": target.role})
            return _response(session, target)

    @router.delete("/{organization_id}/memberships/{membership_id}", status_code=204)
    def remove_membership(organization_id: UUID, membership_id: UUID, request: Request, expected_version: int = Query(ge=1), user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> None:
        with _member_session(session_factory, organization_id, user) as (session, actor):
            target = session.get(OrganizationMembership, membership_id)
            if target is None or target.organization_id != organization_id:
                raise _not_found()
            leaving = actor.id == target.id
            if not leaving and actor.role not in MANAGER_ROLES:
                raise HTTPException(status_code=403, detail="Organization management role required")
            if not leaving and actor.role != OrganizationRole.OWNER.value and target.role == OrganizationRole.OWNER.value:
                raise HTTPException(status_code=403, detail="Admins cannot manage Owners")
            if target.role == OrganizationRole.OWNER.value and _owner_count(session, organization_id) == 1:
                raise HTTPException(status_code=409, detail="an Organization must retain an Owner")
            if expected_version != target.version:
                raise HTTPException(status_code=409, detail={"latest_version": target.version})
            for grant in session.scalars(select(YearclockAccessGrant).where(YearclockAccessGrant.organization_id == organization_id, YearclockAccessGrant.user_account_id == target.user_account_id)).all():
                session.delete(grant)
            session.delete(target)
            _audit(session, request, "organization.membership_left" if leaving else "organization.membership_removed", target, {})

    @router.post("/{organization_id}/memberships/{membership_id}/transfer-ownership", response_model=MembershipResponse)
    def transfer_ownership(organization_id: UUID, membership_id: UUID, body: TransferOwnershipRequest, request: Request, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> MembershipResponse:
        """Make an active Admin or Member an Owner and, unless the caller keeps the role, lower the caller to Admin, in one transaction (ADR-0032)."""
        with _member_session(session_factory, organization_id, user) as (session, actor):
            if actor.role != OrganizationRole.OWNER.value:
                raise HTTPException(status_code=403, detail="only an Owner can transfer ownership")
            target = _transfer(session, organization_id, actor, membership_id, keep_owner=body.keep_owner, expected_version=body.expected_version)
            _audit(session, request, "organization.ownership_transferred", target, {"kept_owner": body.keep_owner, "from": str(actor.id)})
            return _response(session, target)

    @router.post("/{organization_id}/memberships/{membership_id}/leave", status_code=204)
    def leave(organization_id: UUID, membership_id: UUID, request: Request, body: LeaveRequest | None = None, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> None:
        """Leave the Organization. The only Owner must name a successor, who becomes an Owner in the same transaction."""
        with _member_session(session_factory, organization_id, user) as (session, actor):
            if actor.id != membership_id:
                raise HTTPException(status_code=403, detail="you can only leave for yourself")
            if actor.role == OrganizationRole.OWNER.value and _owner_count(session, organization_id) == 1:
                others = session.scalar(select(func.count()).select_from(OrganizationMembership).where(OrganizationMembership.organization_id == organization_id, OrganizationMembership.id != actor.id)) or 0
                if others == 0:
                    raise HTTPException(status_code=409, detail={"reason": "last_member"})
                if body is None or body.successor_membership_id is None:
                    raise HTTPException(status_code=409, detail={"reason": "successor_required"})
                successor = _transfer(session, organization_id, actor, body.successor_membership_id, keep_owner=False, expected_version=None)
                _audit(session, request, "organization.ownership_transferred", successor, {"kept_owner": False, "from": str(actor.id), "leaving": True})
            for grant in session.scalars(select(YearclockAccessGrant).where(YearclockAccessGrant.organization_id == organization_id, YearclockAccessGrant.user_account_id == actor.user_account_id)).all():
                session.delete(grant)
            session.delete(actor)
            _audit(session, request, "organization.membership_left", actor, {})

    return router


def _transfer(session: Session, organization_id: UUID, actor: OrganizationMembership, target_id: UUID, *, keep_owner: bool, expected_version: int | None) -> OrganizationMembership:
    """Promote the target to Owner and, unless ``keep_owner``, lower the actor to Admin; the Organization keeps an Owner throughout."""
    target = session.scalar(select(OrganizationMembership).where(OrganizationMembership.id == target_id, OrganizationMembership.organization_id == organization_id).with_for_update())
    if target is None:
        raise _not_found()
    if target.id == actor.id or target.role not in {OrganizationRole.ADMIN.value, OrganizationRole.MEMBER.value}:
        raise HTTPException(status_code=422, detail="choose an active Administrator or Member")
    if expected_version is not None and expected_version != target.version:
        raise HTTPException(status_code=409, detail={"latest_version": target.version})
    previous = target.role
    target.role = OrganizationRole.OWNER.value
    target.version += 1
    if not keep_owner:
        actor.role = OrganizationRole.ADMIN.value
        actor.version += 1
    session.flush()
    notify_role_change(session, organization_id, actor_id=actor.user_account_id, target_user_id=target.user_account_id, from_role=previous, to_role=OrganizationRole.OWNER.value)
    if not keep_owner:
        notify_role_change(session, organization_id, actor_id=actor.user_account_id, target_user_id=actor.user_account_id, from_role=OrganizationRole.OWNER.value, to_role=OrganizationRole.ADMIN.value)
    return target


MANAGER_ROLES = {OrganizationRole.OWNER.value, OrganizationRole.ADMIN.value}


@contextmanager
def _manager_session(factory: sessionmaker[Session], organization_id: UUID, user: AuthenticatedUser, *, mutate: bool = True):
    """Yield a session for an Owner or Admin; Members receive 403 (ADR-0007)."""
    with _member_session(factory, organization_id, user, mutate=mutate) as (session, actor):
        if actor.role not in MANAGER_ROLES:
            raise HTTPException(status_code=403, detail="Organization management role required")
        yield session, actor


@contextmanager
def _member_session(factory: sessionmaker[Session], organization_id: UUID, user: AuthenticatedUser, *, mutate: bool = True):
    """Yield a session for any member; callers enforce role rules themselves."""
    with transaction_session(factory, RequestContext(user_account_id=user.account.id)) as session:
        actor = _membership(session, organization_id, user.account.id)
        if actor is None:
            raise _not_found()
        apply_request_context(session, RequestContext(user_account_id=user.account.id, organization_id=organization_id))
        if mutate:
            require_organization_mutation_access(session, organization_id)
        yield session, actor


def _membership(session: Session, organization_id: UUID, user_account_id: UUID) -> OrganizationMembership | None:
    return session.scalar(select(OrganizationMembership).where(OrganizationMembership.organization_id == organization_id, OrganizationMembership.user_account_id == user_account_id))


def _owner_count(session: Session, organization_id: UUID) -> int:
    return session.scalar(select(func.count()).select_from(OrganizationMembership).where(OrganizationMembership.organization_id == organization_id, OrganizationMembership.role == OrganizationRole.OWNER.value)) or 0


def _audit(session: Session, request: Request, action: str, membership: OrganizationMembership, change_summary: dict) -> None:
    record_audit_event(session, AuditEventDraft(action=action, target_type="organization_membership", target_id=membership.id, request_id=(request.headers.get("X-Request-ID") or str(uuid4()))[:120], change_summary=change_summary))


def _response(session: Session, membership: OrganizationMembership) -> MembershipResponse:
    account = session.get(UserAccount, membership.user_account_id)
    return MembershipResponse(
        id=membership.id,
        user_account_id=membership.user_account_id,
        email=account.email if account else "",
        display_name=account.display_name if account else "",
        role=membership.role,
        version=membership.version,
    )


def _not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="organization not found")
