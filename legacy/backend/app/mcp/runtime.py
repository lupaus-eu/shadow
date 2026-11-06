"""Run MCP tool database work under ADR-015's resource protection.

Tools run their database work in a worker thread with their own session,
bounded by one `anyio.CapacityLimiter` shared by the MCP server's tools and its
bearer authentication. A domain error reaches the client as a tool error with
the service's message. Any other error reaches it only as a generic message and
is logged with its type and stack but without its message, which may contain
tool arguments (for example SQL parameters).
"""

import logging
import traceback
from collections.abc import Callable
from dataclasses import dataclass

import anyio
import anyio.to_thread
from fastapi import HTTPException, status
from fastmcp.exceptions import ToolError
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.api.v1.ai_change_sets import engine
from app.api.v1.mcp_oauth.token_service import McpPrincipal
from app.mcp.auth import current_principal

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class McpToolRuntime:
    session_factory: Callable[[], Session]
    limiter: anyio.CapacityLimiter

    async def run[T](self, work: Callable[[Session, McpPrincipal], T]) -> T:
        """Run `work` for the request's principal in a worker thread."""
        principal = current_principal.get()
        if principal is None:
            raise ToolError("Authentication required")

        def in_worker_thread() -> T:
            with self.session_factory() as session:
                return work(session, principal)

        try:
            return await anyio.to_thread.run_sync(
                in_worker_thread, limiter=self.limiter
            )
        except HTTPException as exc:
            if exc.status_code >= 500:
                raise _internal_error(exc) from None
            raise ToolError(str(exc.detail), log_level=logging.INFO) from None
        except Exception as exc:
            raise _internal_error(exc) from None


def busy_on_timeout[T](
    work: Callable[[Session, McpPrincipal], T],
) -> Callable[[Session, McpPrincipal], T]:
    """Report a lock or statement timeout as a retryable tool error."""

    def run(session: Session, principal: McpPrincipal) -> T:
        try:
            return work(session, principal)
        except DBAPIError as exc:
            sqlstate = getattr(exc.orig, "sqlstate", None)
            if sqlstate not in {engine.LOCK_NOT_AVAILABLE, engine.QUERY_CANCELED}:
                raise
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="The change set is busy or the database timed out; "
                "try again shortly.",
            ) from exc

    return run


def _internal_error(exc: BaseException) -> ToolError:
    logger.error(
        "MCP tool failed with %s\n%s",
        type(exc).__name__,
        "".join(traceback.format_tb(exc.__traceback__)),
    )
    return ToolError("Internal error")
