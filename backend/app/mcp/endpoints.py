"""Build the MCP endpoint that `create_app()` registers (ADR-015).

The one Schatten FastMCP server is built per app, stateless with JSON
responses, so no MCP session, server-sent event stream or per-session state is
kept. It is served at the exact route `/api/mcp` wrapped in `McpBearerAuth`:
`app.mount` would redirect `/api/mcp` to a trailing slash. The stateless server
answers an authenticated GET or DELETE with 405.
"""

from collections.abc import Callable
from dataclasses import dataclass

import anyio
from fastmcp.server.http import StarletteWithLifespan
from sqlalchemy.orm import Session
from starlette.routing import Route

from app.api.v1.auth.rate_limit import FixedWindowRateLimiter
from app.api.v1.mcp_oauth.service import MCP_PATH
from app.core.config import Settings
from app.core.database import get_session_factory
from app.mcp.auth import McpBearerAuth
from app.mcp.runtime import McpToolRuntime
from app.mcp.server import build_mcp_server

MCP_ROUTE_METHODS = ("GET", "POST", "DELETE")


@dataclass(frozen=True)
class McpEndpoint:
    route: Route
    # Its lifespan runs the server's session manager.
    http_app: StarletteWithLifespan


def build_mcp_endpoint(
    settings: Settings,
    *,
    rate_limiter: FixedWindowRateLimiter,
    session_factory: Callable[[], Session] | None = None,
) -> McpEndpoint:
    """Build the endpoint; its tools and authentication share one limiter."""
    resolved_session_factory = session_factory or _new_session
    limiter = anyio.CapacityLimiter(settings.mcp_tool_concurrency)
    runtime = McpToolRuntime(resolved_session_factory, limiter)
    server = build_mcp_server(runtime, settings)
    http_app = server.http_app(path=MCP_PATH, stateless_http=True, json_response=True)
    auth = McpBearerAuth(
        http_app,
        settings=settings,
        session_factory=resolved_session_factory,
        limiter=limiter,
        rate_limiter=rate_limiter,
    )
    route = Route(
        MCP_PATH, endpoint=auth, methods=MCP_ROUTE_METHODS, include_in_schema=False
    )
    return McpEndpoint(route=route, http_app=http_app)


def _new_session() -> Session:
    return get_session_factory()()
