from datetime import datetime
from typing import Any
from uuid import UUID

from app.core.schemas import StrictBaseModel


class NotificationResponse(StrictBaseModel):
    id: UUID
    type: str
    params: dict[str, Any]
    created_time: datetime
    read_time: datetime | None


class NotificationPage(StrictBaseModel):
    items: list[NotificationResponse]
    next_cursor: str | None = None


class UnreadCount(StrictBaseModel):
    unread: int


class ReadAllResponse(StrictBaseModel):
    updated: int
