"""Running one tool call: who is calling, under which rules, in a worker thread.

The application's database work is synchronous, so each call runs in a thread. Every
call resolves the signed-in customer account from the token's subject, marks the audit
entries it writes as made through MCP (ADR-0037), and turns the application's HTTP
errors into tool errors the agent can read.
"""

import json
from collections.abc import Callable
from functools import partial
from typing import Any
from uuid import UUID

import anyio.to_thread
from fastapi import HTTPException
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import BaseModel
from sqlalchemy.orm import Session, sessionmaker

from app.audit import audit_source
from app.auth import AuthenticatedUser
from app.database import RequestContext, transaction_session
from app.mcp_server.gate import require_mcp_enabled
from app.mcp_server.identity import NotSignedUp, customer_account
from app.mcp_server.settings import McpSettings

TOOL_FUNCTION = Callable[..., Any]


def plain(value: Any) -> Any:
    """Pydantic models, UUIDs, dates and the like as plain JSON values."""
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, (list, tuple)):
        return [plain(item) for item in value]
    if isinstance(value, dict):
        return {key: plain(item) for key, item in value.items()}
    return json.loads(json.dumps(value, default=str))


def _message(error: HTTPException) -> str:
    detail = error.detail
    text = detail if isinstance(detail, str) else json.dumps(detail, default=str)
    return f"{text} (HTTP {error.status_code})"


class ToolRuntime:
    def __init__(self, session_factory: sessionmaker[Session], settings: McpSettings) -> None:
        self.session_factory = session_factory
        self.settings = settings

    async def call(self, function: TOOL_FUNCTION, *, organization_id: UUID | None = None, **arguments: Any) -> Any:
        token = get_access_token()
        if token is None or not token.subject:
            raise ToolError("Sign in is required")
        return await anyio.to_thread.run_sync(
            partial(self._invoke, token.subject, token.client_id, function, organization_id, arguments)
        )

    def _invoke(self, subject: str, client_id: str, function: TOOL_FUNCTION, organization_id: UUID | None, arguments: dict[str, Any]) -> Any:
        with audit_source(source="mcp", mcp_client=client_id):
            try:
                with transaction_session(self.session_factory, RequestContext()) as session:
                    account = customer_account(session, self.settings, subject)
                user = AuthenticatedUser(account=account, user_session=None)  # type: ignore[arg-type]
                if organization_id is not None:
                    require_mcp_enabled(self.session_factory, user, organization_id)
                return plain(function(user, **arguments))
            except NotSignedUp:
                raise ToolError("This sign-in has no Yearclock account. Sign in to the Yearclock web application once first.") from None
            except HTTPException as error:
                raise ToolError(_message(error)) from None
