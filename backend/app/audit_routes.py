from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.auth import AuthenticatedUser
from app.auth_routes import AuthenticatedUserDependency
from app.database import RequestContext, apply_request_context, transaction_session
from app.models import AccountClass, AuditEvent, OrganizationMembership, OrganizationRole, UserAccount


class AuditItem(BaseModel):
    id: UUID
    actor_user_account_id: UUID | None
    actor: str | None
    support_access_id: UUID | None
    action: str
    target_type: str
    target_id: UUID
    occurred_at: datetime
    change_summary: dict


class AuditPage(BaseModel):
    items: list[AuditItem]
    next_offset: int | None


def create_audit_router(*, session_factory: sessionmaker, authenticated_user_dependency: AuthenticatedUserDependency) -> APIRouter:
    router = APIRouter(prefix="/api/v1/organizations", tags=["Audit activity"])

    @router.get("/{organization_id}/audit-events", response_model=AuditPage)
    def list_events(
        organization_id: UUID,
        action: str | None = None,
        prefix: str | None = Query(default=None, max_length=60, pattern=r"^[a-z_]+\.?$"),
        offset: int = Query(default=0, ge=0),
        limit: int = Query(default=50, ge=1, le=100),
        user: AuthenticatedUser = Depends(authenticated_user_dependency),
    ) -> AuditPage:
        with transaction_session(session_factory, RequestContext(user_account_id=user.account.id)) as session:
            membership = session.scalar(select(OrganizationMembership).where(OrganizationMembership.organization_id == organization_id, OrganizationMembership.user_account_id == user.account.id))
            if membership is None:
                raise HTTPException(status_code=404, detail="organization not found")
            if membership.role not in {OrganizationRole.OWNER.value, OrganizationRole.ADMIN.value}:
                raise HTTPException(status_code=403, detail="Organization management role required")
            apply_request_context(session, RequestContext(user_account_id=user.account.id, organization_id=organization_id))
            statement = select(AuditEvent).where(AuditEvent.organization_id == organization_id)
            if action:
                statement = statement.where(AuditEvent.action == action)
            if prefix:
                statement = statement.where(AuditEvent.action.startswith(prefix if prefix.endswith(".") else f"{prefix}."))
            rows = session.scalars(statement.order_by(AuditEvent.occurred_at.desc(), AuditEvent.id).offset(offset).limit(limit + 1)).all()
            actors = {account.id: account for account in session.scalars(select(UserAccount).where(UserAccount.id.in_({row.actor_user_account_id for row in rows if row.actor_user_account_id}))).all()}
            return AuditPage(
                items=[_item(row, actors.get(row.actor_user_account_id)) for row in rows[:limit]],
                next_offset=offset + limit if len(rows) > limit else None,
            )

    return router


def _item(event: AuditEvent, actor: UserAccount | None) -> AuditItem:
    label = None
    if actor is not None:
        label = f"Platform support ({actor.display_name})" if actor.account_class == AccountClass.PLATFORM.value else actor.email
    return AuditItem(
        id=event.id,
        actor_user_account_id=event.actor_user_account_id,
        actor=label,
        support_access_id=event.support_access_id,
        action=event.action,
        target_type=event.target_type,
        target_id=event.target_id,
        occurred_at=event.occurred_at,
        change_summary=event.change_summary,
    )
