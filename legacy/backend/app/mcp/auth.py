"""Bearer authentication and tool scope checks for the MCP endpoint (ADR-015).

`McpBearerAuth` wraps the MCP server's Streamable HTTP app. It accepts only an
`Authorization: Bearer` token, never the browser session cookie, and on every
request verifies the token for the canonical resource and the minimum scope
`shadow.read`, applies the per-grant `mcp_rate_limiter` and exposes the
verified principal to tools through `current_principal`. `requires_scope` then
admits each tool and prompt only for a principal with its scope (TASK-074).
Tokens are never logged.
"""

from collections.abc import Callable
from contextvars import ContextVar
from typing import Literal

import anyio
import anyio.to_thread
from fastmcp.server.auth import AuthCheck, AuthContext
from sqlalchemy.orm import Session
from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.api.v1.auth.rate_limit import FixedWindowRateLimiter
from app.api.v1.mcp_oauth.service import (
    PROTECTED_RESOURCE_METADATA_PATH,
    READ_SCOPE,
    canonical_resource,
)
from app.api.v1.mcp_oauth.token_service import (
    McpPrincipal,
    TokenVerificationError,
    verify_access_token,
)
from app.core.config import Settings

MCP_RATE_LIMIT_BUCKET = "mcp"

current_principal: ContextVar[McpPrincipal | None] = ContextVar(
    "mcp_principal", default=None
)


def requires_scope(scope: str) -> AuthCheck:
    """Admit a tool or prompt only for a principal whose scopes include `scope`.

    The principal's scopes are the effective set that `verify_access_token`
    computed for this request: the grant's scopes that the User's role allows.
    fastmcp leaves a component whose check fails out of its lists and answers
    a call to it as an unknown tool, so a role without `shadow.write` sees
    only the read tools and prompts.
    """

    def check(_: AuthContext) -> bool:
        principal = current_principal.get()
        return principal is not None and scope in principal.scopes

    return check


class McpBearerAuth:
    """ASGI wrapper that authenticates the MCP endpoint."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        settings: Settings,
        session_factory: Callable[[], Session],
        limiter: anyio.CapacityLimiter,
        rate_limiter: FixedWindowRateLimiter,
    ) -> None:
        self._app = app
        self._resource = canonical_resource(settings)
        self._resource_metadata = (
            f"{settings.public_origin}{PROTECTED_RESOURCE_METADATA_PATH}"
        )
        self._rate_limit_per_minute = settings.mcp_rate_limit_per_minute
        self._session_factory = session_factory
        self._limiter = limiter
        self._rate_limiter = rate_limiter

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        authorization = Headers(scope=scope).getlist("authorization")
        if len(authorization) > 1:
            # More than one Authorization header is a rejected credential.
            await self._challenge(401, "invalid_token")(scope, receive, send)
            return
        scheme, _, token = (authorization[0] if authorization else "").partition(" ")
        if scheme.lower() != "bearer":
            # RFC 6750: no bearer token was presented, so no error code.
            await self._challenge(401, None)(scope, receive, send)
            return

        try:
            principal = await anyio.to_thread.run_sync(
                self._verify, token, limiter=self._limiter
            )
        except TokenVerificationError as exc:
            status_code = 403 if exc.error == "insufficient_scope" else 401
            await self._challenge(status_code, exc.error)(scope, receive, send)
            return
        if not self._rate_limiter.allow(
            MCP_RATE_LIMIT_BUCKET, principal.grant_key, self._rate_limit_per_minute
        ):
            response = JSONResponse(
                status_code=429,
                content={
                    "error": "temporarily_unavailable",
                    "error_description": "Too many requests",
                },
            )
            await response(scope, receive, send)
            return

        reset_token = current_principal.set(principal)
        try:
            await self._app(scope, receive, send)
        finally:
            current_principal.reset(reset_token)

    def _verify(self, token: str) -> McpPrincipal:
        with self._session_factory() as session:
            return verify_access_token(session, token, self._resource, READ_SCOPE)

    def _challenge(
        self,
        status_code: int,
        error: Literal["invalid_token", "insufficient_scope"] | None,
    ) -> JSONResponse:
        """Build the RFC 6750 / RFC 9728 challenge for the endpoint."""
        parameters: list[str] = []
        if error is not None:
            parameters.append(f'error="{error}"')
        if error == "insufficient_scope":
            parameters.append(f'scope="{READ_SCOPE}"')
        parameters.append(f'resource_metadata="{self._resource_metadata}"')
        descriptions = {
            None: "A bearer token is required",
            "invalid_token": "The access token is invalid",
            "insufficient_scope": "The access token lacks the required scope",
        }
        return JSONResponse(
            status_code=status_code,
            content={
                "error": error or "unauthorized",
                "error_description": descriptions[error],
            },
            headers={"WWW-Authenticate": "Bearer " + ", ".join(parameters)},
        )
