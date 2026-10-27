"""Bearer authentication for the MCP endpoints (ADR-015).

`McpBearerAuth` wraps each MCP server's Streamable HTTP app. It accepts only an
`Authorization: Bearer` token, never the browser session cookie, and on every
request verifies the token for the endpoint's canonical resource and scope,
applies the per-grant `mcp_rate_limiter` and exposes the verified principal to
tools through `current_principal`. Tokens are never logged.
"""

from collections.abc import Callable
from contextvars import ContextVar
from typing import Literal

import anyio
import anyio.to_thread
from sqlalchemy.orm import Session
from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.api.v1.auth.rate_limit import FixedWindowRateLimiter
from app.api.v1.mcp_oauth.service import MCP_SERVER_SCOPES, canonical_resource
from app.api.v1.mcp_oauth.token_service import (
    McpPrincipal,
    TokenVerificationError,
    verify_access_token,
)
from app.core.config import Settings

McpServerName = Literal["read", "write"]
MCP_RATE_LIMIT_BUCKET = "mcp"

current_principal: ContextVar[McpPrincipal | None] = ContextVar(
    "mcp_principal", default=None
)


class McpBearerAuth:
    """ASGI wrapper that authenticates one MCP endpoint."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        server: McpServerName,
        settings: Settings,
        session_factory: Callable[[], Session],
        limiter: anyio.CapacityLimiter,
        rate_limiter: FixedWindowRateLimiter,
    ) -> None:
        self._app = app
        self._resource = canonical_resource(settings, server)
        self._scope = MCP_SERVER_SCOPES[server]
        self._resource_metadata = (
            f"{settings.public_origin}"
            f"/.well-known/oauth-protected-resource/api/mcp/{server}"
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
            return verify_access_token(session, token, self._resource, self._scope)

    def _challenge(
        self,
        status_code: int,
        error: Literal["invalid_token", "insufficient_scope"] | None,
    ) -> JSONResponse:
        """Build the RFC 6750 / RFC 9728 challenge for this endpoint."""
        parameters: list[str] = []
        if error is not None:
            parameters.append(f'error="{error}"')
        if error == "insufficient_scope":
            parameters.append(f'scope="{self._scope}"')
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
