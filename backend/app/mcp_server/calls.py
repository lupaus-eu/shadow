"""The record of every MCP tool call (ADR-0047).

``track_tools`` wraps each tool the server registers. After the tool has run, one row goes
into ``mcp_calls`` in its own short transaction, so it survives a rolled-back write and also
covers refused and failing calls. The row names the person the agent acted for and the agent
program; it never holds the arguments or the result.

A successful read that names no Organization (``list_organizations``) is not stored: it returns
only the person's own memberships, and no Organization's retention could ever reach the row.

A write call, or any call that was refused or failed, fails when its row cannot be written:
an unrecorded agent action is worse than a failed one. A successful read call returns its
result and the failure goes to the log instead.
"""

import functools
import logging
import re
import time
from datetime import datetime, timedelta
from collections.abc import Callable
from typing import Any
from uuid import UUID, uuid4

import anyio.to_thread
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from app.database import RequestContext, apply_request_context, transaction_session
from app.limits import Ceiling
from app.mcp_server.identity import NotSignedUp, customer_account
from app.mcp_server.settings import McpSettings
from app.models import McpCall, OrganizationMembership

logger = logging.getLogger(__name__)
HTTP_STATUS = re.compile(r"\(HTTP (\d{3})\)$")


def classify(error: BaseException | None) -> tuple[str, str | None]:
    """(outcome, reason) of a finished call; the reason is a short code, never free text."""
    if error is None:
        return "ok", None
    if isinstance(error, ToolError):
        message = str(error)
        match = HTTP_STATUS.search(message)
        status = int(match.group(1)) if match else None
        if status in (401, 403):
            if "blocked by the operator" in message:
                return "refused", "operator_block"
            if "turned off by" in message:
                return "refused", "switch_off"
            if "read-only" in message:
                return "refused", "read_only"
            return "refused", "forbidden"
        if status == 404 and "Organization not found" in message:
            return "refused", "not_member"
        if status is not None:
            return "error", f"http_{status}"
        if message.startswith("Invalid input"):
            return "error", "invalid_input"
        return "error", "tool_error"
    return "error", "unexpected"


def _write(session_factory: sessionmaker[Session], settings: McpSettings, subject: str, client: str, organization_id: UUID | None, tool: str, kind: str, outcome: str, reason: str | None, duration_ms: int) -> bool:
    """Write the row; False when the token's person has no Shadow account (nothing to attribute)."""
    with transaction_session(session_factory, RequestContext()) as session:
        try:
            account = customer_account(session, settings, subject)
        except NotSignedUp:
            return False
        account_id = account.id
    member = False
    if organization_id is not None:
        with transaction_session(session_factory, RequestContext(user_account_id=account_id)) as session:
            member = session.scalar(
                select(OrganizationMembership.id).where(OrganizationMembership.organization_id == organization_id, OrganizationMembership.user_account_id == account_id)
            ) is not None
    with transaction_session(session_factory, RequestContext(user_account_id=account_id, organization_id=organization_id if member else None)) as session:
        session.add(
            McpCall(id=uuid4(), organization_id=organization_id if member else None, user_account_id=account_id, mcp_client=client[:200], tool=tool, kind=kind, outcome=outcome, reason=reason, duration_ms=duration_ms)
        )
    return True


def track_tools(server: MCPServer, session_factory: sessionmaker[Session], settings: McpSettings) -> None:
    """Make every tool registered from now on leave one ``mcp_calls`` row per call."""
    register = server.tool

    def tool(*args: Any, **options: Any) -> Callable[[Callable[..., Any]], Any]:
        annotations = options.get("annotations")
        kind = "read" if annotations is not None and annotations.read_only_hint else "write"
        decorator = register(*args, **options)

        def decorate(function: Callable[..., Any]) -> Any:
            name = options.get("name") or function.__name__

            @functools.wraps(function)
            async def tracked(*call_args: Any, **call_kwargs: Any) -> Any:
                started = time.monotonic()
                failure: BaseException | None = None
                try:
                    return await function(*call_args, **call_kwargs)
                except BaseException as error:  # noqa: BLE001 - recorded, then re-raised unchanged
                    failure = error
                    raise
                finally:
                    await _record(name, kind, call_kwargs.get("organization_id"), failure, int((time.monotonic() - started) * 1000))

            async def _record(tool_name: str, call_kind: str, organization_id: UUID | None, failure: BaseException | None, duration_ms: int) -> None:
                token = get_access_token()
                if token is None or not token.subject:
                    return  # refused before any person was identified; nothing to attribute
                outcome, reason = classify(failure)
                if organization_id is None and call_kind == "read" and outcome == "ok":
                    return  # list_organizations: only the person's own memberships; no Organization to keep it for
                try:
                    recorded = await anyio.to_thread.run_sync(
                        lambda: _write(session_factory, settings, token.subject, token.client_id, organization_id, tool_name, call_kind, outcome, reason, duration_ms)
                    )
                except Exception:
                    logger.exception("MCP call %s could not be recorded", tool_name)
                    if call_kind == "read" and outcome == "ok":
                        return  # reads fail open
                    raise ToolError("The call could not be recorded, so it was reported as failed. Check its effect before retrying.") from None
                if not recorded:
                    logger.warning("MCP call %s by a sign-in without a Shadow account was not recorded", tool_name)

            return decorator(tracked)

        return decorate

    server.tool = tool  # type: ignore[method-assign]


READ_LOG_JOB = "mcp.read_log_cleanup"
READ_LOG_RETENTION = Ceiling("mcp_read_log_retention_days", "MCP_READ_LOG_RETENTION_DAYS", 90)


def cleanup_read_log(session: Session, job: Any, now: datetime) -> None:
    """Delete this Organization's successful read calls past their retention; writes, refusals and errors stay."""
    apply_request_context(session, RequestContext(organization_id=job.organization_id, worker_scope="mcp_read_log"))
    session.execute(
        delete(McpCall).where(
            McpCall.organization_id == job.organization_id,
            McpCall.kind == "read",
            McpCall.outcome == "ok",
            McpCall.occurred_at < now - timedelta(days=READ_LOG_RETENTION.maximum),
        )
    )
