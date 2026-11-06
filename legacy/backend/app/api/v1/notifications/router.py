"""The caller's own notifications (ADR-019).

Every user reads and marks only their own. The API sends the type and the
parameters; the interface builds the text in the reader's language.
"""

import base64
import binascii
from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session, sessionmaker

from app.api.v1.auth.dependencies import (
    BusinessSessionDependency,
    UnsafeRequestDependency,
    require_business_request,
)
from app.api.v1.notifications.schemas import (
    NotificationPage,
    NotificationResponse,
    ReadAllResponse,
    UnreadCount,
)
from app.core.database import RequestContext, get_session_factory, transaction_session
from app.platform.models import Notification

PAGE_SIZE = 20

router = APIRouter(
    prefix="/notifications",
    tags=["notifications"],
    dependencies=[Depends(require_business_request)],
)
SessionFactoryDependency = Annotated[
    sessionmaker[Session], Depends(get_session_factory)
]


def _encode_cursor(value: str) -> str:
    return base64.urlsafe_b64encode(value.encode()).decode().rstrip("=")


def _decode_cursor(cursor: str) -> str:
    try:
        return base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)).decode()
    except (binascii.Error, UnicodeDecodeError):
        raise ValueError("invalid cursor") from None


def _response(row: Notification) -> NotificationResponse:
    return NotificationResponse(
        id=row.id,
        type=row.type,
        params=row.params,
        created_time=row.created_time,
        read_time=row.read_time,
    )


@router.get("", response_model=NotificationPage)
def list_notifications(
    active: BusinessSessionDependency,
    factory: SessionFactoryDependency,
    cursor: Annotated[str | None, Query(max_length=200)] = None,
    unread: bool = False,
) -> NotificationPage:
    user_id = active.user.user_id
    with transaction_session(factory, RequestContext(user_id=user_id)) as session:
        query = (
            select(Notification)
            .where(Notification.recipient_user_id == user_id)
            .order_by(Notification.created_time.desc(), Notification.id.desc())
            .limit(PAGE_SIZE + 1)
        )
        if unread:
            query = query.where(Notification.read_time.is_(None))
        if cursor:
            try:
                stamp, identifier = _decode_cursor(cursor).split("|", 1)
                moment, last = datetime.fromisoformat(stamp), UUID(identifier)
            except ValueError:
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_CONTENT, "invalid cursor"
                ) from None
            query = query.where(
                or_(
                    Notification.created_time < moment,
                    (Notification.created_time == moment) & (Notification.id < last),
                )
            )
        rows = session.scalars(query).all()
        page = rows[:PAGE_SIZE]
        more = (
            _encode_cursor(f"{page[-1].created_time.isoformat()}|{page[-1].id}")
            if len(rows) > PAGE_SIZE
            else None
        )
        return NotificationPage(
            items=[_response(row) for row in page], next_cursor=more
        )


@router.get("/unread-count", response_model=UnreadCount)
def unread_count(
    active: BusinessSessionDependency, factory: SessionFactoryDependency
) -> UnreadCount:
    user_id = active.user.user_id
    with transaction_session(factory, RequestContext(user_id=user_id)) as session:
        count = session.scalar(
            select(func.count())
            .select_from(Notification)
            .where(
                Notification.recipient_user_id == user_id,
                Notification.read_time.is_(None),
            )
        )
        return UnreadCount(unread=count or 0)


@router.post("/read-all", response_model=ReadAllResponse)
def read_all(
    active: UnsafeRequestDependency, factory: SessionFactoryDependency
) -> ReadAllResponse:
    user_id = active.user.user_id
    with transaction_session(factory, RequestContext(user_id=user_id)) as session:
        result = session.execute(
            update(Notification)
            .where(
                Notification.recipient_user_id == user_id,
                Notification.read_time.is_(None),
            )
            .values(read_time=func.greatest(func.now(), Notification.created_time))
        )
        return ReadAllResponse(updated=getattr(result, "rowcount", 0) or 0)


@router.post("/{notification_id}/read", status_code=status.HTTP_204_NO_CONTENT)
def read_one(
    notification_id: UUID,
    active: UnsafeRequestDependency,
    factory: SessionFactoryDependency,
) -> Response:
    user_id = active.user.user_id
    with transaction_session(factory, RequestContext(user_id=user_id)) as session:
        row = session.scalar(
            select(Notification).where(
                Notification.id == notification_id,
                Notification.recipient_user_id == user_id,
            )
        )
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "notification not found")
        if row.read_time is None:
            row.read_time = func.greatest(  # pyright: ignore[reportAttributeAccessIssue]
                func.now(), Notification.created_time
            )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
