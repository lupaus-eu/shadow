from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models import AuditEvent


# Who made the change when it is not the web application: set by the MCP interface for the
# duration of one tool call, and merged into every audit entry written meanwhile (ADR-0037).
_SOURCE: ContextVar[dict[str, Any] | None] = ContextVar("audit_source", default=None)


def current_source() -> dict[str, Any] | None:
    return _SOURCE.get()


@contextmanager
def audit_source(**source: Any):
    token = _SOURCE.set(source)
    try:
        yield
    finally:
        _SOURCE.reset(token)


@dataclass(frozen=True)
class AuditEventDraft:
    action: str
    target_type: str
    target_id: UUID
    request_id: str
    change_summary: dict[str, Any] = field(default_factory=dict)


def record_audit_event(session: Session, draft: AuditEventDraft) -> UUID:
    context = session.execute(
        text(
            """
            SELECT
                NULLIF(current_setting('app.current_user_account_id', true), '')::uuid,
                NULLIF(current_setting('app.current_organization_id', true), '')::uuid,
                NULLIF(current_setting('app.current_support_access_id', true), '')::uuid
            """
        )
    ).one()
    audit_event_id = uuid4()
    session.add(
        AuditEvent(
            id=audit_event_id,
            actor_user_account_id=context[0],
            organization_id=context[1],
            support_access_id=context[2],
            action=draft.action,
            target_type=draft.target_type,
            target_id=draft.target_id,
            request_id=draft.request_id,
            change_summary={**draft.change_summary, **(_SOURCE.get() or {})},
        )
    )
    return audit_event_id
