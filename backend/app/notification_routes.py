"""The notification inbox (Shadow V2 P8, ADR-0031).

Every Organization member reads and marks only their own notifications; the
row-level policy also keeps other people's rows out of reach. The API sends
the type and parameters, and the interface builds the text in the reader's
language.
"""
from contextlib import contextmanager
from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session, sessionmaker

from app.auth import AuthenticatedUser
from app.auth_routes import AuthenticatedUserDependency
from app.database import RequestContext, apply_request_context, transaction_session
from app.models import Notification, NotificationPreference, OrganizationMembership, OrganizationRole
from app.notifications import SETTINGS, channel_enabled

PAGE_SIZE = 20


class NotificationResponse(BaseModel):
    id: UUID
    type: str
    params: dict[str, Any]
    created_at: datetime
    read_at: datetime | None


class NotificationPage(BaseModel):
    items: list[NotificationResponse]
    next_cursor: str | None = None


class UnreadCount(BaseModel):
    unread: int


class ReadAllResponse(BaseModel):
    updated: int


class SettingItem(BaseModel):
    key: str
    audience: str
    in_app: bool
    email: bool


class SettingsResponse(BaseModel):
    items: list[SettingItem]


class ChannelChoice(BaseModel):
    in_app: bool
    email: bool


class SettingsRequest(BaseModel):
    settings: dict[str, ChannelChoice] = {}


@contextmanager
def _member_session(factory: sessionmaker[Session], organization_id: UUID, user: AuthenticatedUser):
    with transaction_session(factory, RequestContext(user_account_id=user.account.id)) as session:
        if session.scalar(select(OrganizationMembership.id).where(OrganizationMembership.organization_id == organization_id, OrganizationMembership.user_account_id == user.account.id)) is None:
            raise HTTPException(status_code=404, detail="Organization not found")
        apply_request_context(session, RequestContext(user_account_id=user.account.id, organization_id=organization_id))
        yield session


def _own(organization_id: UUID, user: AuthenticatedUser):
    return (Notification.organization_id == organization_id, Notification.recipient_user_id == user.account.id)


def create_notification_router(*, session_factory: sessionmaker[Session], authenticated_user_dependency: AuthenticatedUserDependency) -> APIRouter:
    router = APIRouter(prefix="/api/v1/organizations", tags=["Notifications"])

    @router.get("/{organization_id}/notifications", response_model=NotificationPage)
    def list_notifications(organization_id: UUID, cursor: str | None = None, unread: bool = False, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> NotificationPage:
        with _member_session(session_factory, organization_id, user) as session:
            query = select(Notification).where(*_own(organization_id, user)).order_by(Notification.created_at.desc(), Notification.id.desc()).limit(PAGE_SIZE + 1)
            if unread:
                query = query.where(Notification.read_at.is_(None))
            if cursor:
                try:
                    stamp, identifier = cursor.split("|", 1)
                    moment, last = datetime.fromisoformat(stamp), UUID(identifier)
                except ValueError as error:
                    raise HTTPException(status_code=422, detail="invalid cursor") from error
                query = query.where(or_(Notification.created_at < moment, (Notification.created_at == moment) & (Notification.id < last)))
            rows = session.scalars(query).all()
            page = rows[:PAGE_SIZE]
            more = f"{page[-1].created_at.isoformat()}|{page[-1].id}" if len(rows) > PAGE_SIZE else None
            return NotificationPage(items=[NotificationResponse(id=row.id, type=row.type, params=row.params, created_at=row.created_at, read_at=row.read_at) for row in page], next_cursor=more)

    @router.get("/{organization_id}/notifications/unread-count", response_model=UnreadCount)
    def unread_count(organization_id: UUID, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> UnreadCount:
        with _member_session(session_factory, organization_id, user) as session:
            return UnreadCount(unread=session.scalar(select(func.count()).select_from(Notification).where(*_own(organization_id, user), Notification.read_at.is_(None))) or 0)

    @router.post("/{organization_id}/notifications/read-all", response_model=ReadAllResponse)
    def read_all(organization_id: UUID, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> ReadAllResponse:
        with _member_session(session_factory, organization_id, user) as session:
            result = session.execute(update(Notification).where(*_own(organization_id, user), Notification.read_at.is_(None)).values(read_at=func.now()))
            return ReadAllResponse(updated=result.rowcount or 0)

    @router.post("/{organization_id}/notifications/{notification_id}/read", status_code=204)
    def read_one(organization_id: UUID, notification_id: UUID, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> None:
        with _member_session(session_factory, organization_id, user) as session:
            row = session.scalar(select(Notification).where(Notification.id == notification_id, *_own(organization_id, user)))
            if row is None:
                raise HTTPException(status_code=404, detail="notification not found")
            if row.read_at is None:
                row.read_at = func.now()

    def _settings(session: Session, organization_id: UUID, user: AuthenticatedUser) -> SettingsResponse:
        role = session.scalar(select(OrganizationMembership.role).where(OrganizationMembership.organization_id == organization_id, OrganizationMembership.user_account_id == user.account.id))
        manager = role in {OrganizationRole.OWNER.value, OrganizationRole.ADMIN.value}
        preference = session.get(NotificationPreference, (organization_id, user.account.id))
        return SettingsResponse(items=[SettingItem(key=key, audience=info.audience, in_app=channel_enabled(preference, key, "in_app"), email=channel_enabled(preference, key, "email")) for key, info in SETTINGS.items() if info.audience == "everyone" or manager])

    @router.get("/{organization_id}/notification-settings", response_model=SettingsResponse)
    def read_settings(organization_id: UUID, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> SettingsResponse:
        with _member_session(session_factory, organization_id, user) as session:
            return _settings(session, organization_id, user)

    @router.put("/{organization_id}/notification-settings", response_model=SettingsResponse)
    def write_settings(organization_id: UUID, body: SettingsRequest, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> SettingsResponse:
        with _member_session(session_factory, organization_id, user) as session:
            allowed = {item.key for item in _settings(session, organization_id, user).items}
            unknown = set(body.settings) - allowed
            if unknown:
                raise HTTPException(status_code=422, detail=f"unknown notification types: {sorted(unknown)}")
            preference = session.get(NotificationPreference, (organization_id, user.account.id))
            if preference is None:
                preference = NotificationPreference(organization_id=organization_id, user_id=user.account.id, settings={})
                session.add(preference)
            preference.settings = {**(preference.settings or {}), **{key: choice.model_dump() for key, choice in body.settings.items()}}
            preference.updated_at = func.now()
            session.flush()
            return _settings(session, organization_id, user)

    return router
