"""ORM models of the platform foundation (ADR-016): audit, queues, notifications."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import BigInteger, DateTime, ForeignKey, Text, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.api.v1.users.models import User
from app.core.models import Base

# Keep the Users table in the registry so the string-based user foreign keys resolve.
_REGISTERED_USER_TABLE = User.__table__


class AuditEvent(Base):
    __tablename__ = "audit_events"
    # Keep inserts free of RETURNING so they also work under future row-level
    # security policies that do not let the writer read the row back.
    __table_args__ = {"implicit_returning": False}

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    actor_user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.user_id")
    )
    tenant_id: Mapped[UUID | None] = mapped_column(Uuid)
    support_access_id: Mapped[UUID | None] = mapped_column(Uuid)
    action: Mapped[str] = mapped_column(Text)
    target_type: Mapped[str] = mapped_column(Text)
    target_id: Mapped[str] = mapped_column(Text)
    occurred_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    request_id: Mapped[str] = mapped_column(Text)
    change_summary: Mapped[dict[str, Any]] = mapped_column(JSONB)
