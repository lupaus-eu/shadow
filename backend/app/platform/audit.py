"""Append-only audit events (ADR-016; copied from Yearclock ``audit.py``, 6848e72).

An audit event is written in the transaction of the action it records, with the
actor and tenant taken from the transaction's request context.
"""

import json
from collections.abc import Generator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.platform.models import AuditEvent

# Who made the change when it is not the web application: set by the MCP
# interface for one tool call and stored under the reserved summary key
# ``source`` of every audit entry written meanwhile (ADR-015). It travels in a
# ContextVar, so it reaches asyncio tasks and anyio worker threads but not raw
# threads or ``run_in_executor``; wrap only the synchronous database work.
_SOURCE: ContextVar[Mapping[str, Any] | None] = ContextVar("audit_source", default=None)
SOURCE_KEY = "source"


def current_source() -> dict[str, Any] | None:
    source = _SOURCE.get()
    return None if source is None else dict(source)


@contextmanager
def audit_source(**source: Any) -> Generator[None, None, None]:
    _ensure_json(source)
    token = _SOURCE.set(MappingProxyType(dict(source)))
    try:
        yield
    finally:
        _SOURCE.reset(token)


@dataclass(frozen=True)
class AuditEventDraft:
    action: str
    target_type: str
    target_id: str | int | UUID
    request_id: str
    change_summary: dict[str, Any] = field(default_factory=dict[str, Any])


def _ensure_json(value: Any) -> None:
    """Fail at the call site, not at flush, when a value cannot be stored as JSON."""
    json.dumps(value)


def record_audit_event(session: Session, draft: AuditEventDraft) -> UUID:
    """Append an audit event for the transaction's request context.

    Raises ``RuntimeError`` when the session has no request context, because an
    event with silently missing attribution is worse than none: use
    ``transaction_session``. An event with an empty context (no actor, no
    tenant) is allowed and means a system action.
    """
    if SOURCE_KEY in draft.change_summary:
        raise ValueError(f"change_summary may not use the reserved key {SOURCE_KEY!r}")
    _ensure_json(draft.change_summary)
    context = session.execute(
        text(
            """
            SELECT
                current_setting('app.request_context', true),
                NULLIF(current_setting('app.current_user_id', true), '')::bigint,
                NULLIF(current_setting('app.current_tenant_id', true), '')::uuid,
                NULLIF(current_setting('app.current_support_access_id', true), '')::uuid
            """
        )
    ).one()
    if context[0] != "applied":
        raise RuntimeError(
            "record_audit_event needs a transaction_session request context"
        )
    source = _SOURCE.get()
    summary = dict(draft.change_summary)
    if source is not None:
        summary[SOURCE_KEY] = dict(source)
    audit_event_id = uuid4()
    session.add(
        AuditEvent(
            id=audit_event_id,
            actor_user_id=context[1],
            tenant_id=context[2],
            support_access_id=context[3],
            action=draft.action,
            target_type=draft.target_type,
            target_id=str(draft.target_id),
            request_id=draft.request_id,
            change_summary=summary,
        )
    )
    return audit_event_id
