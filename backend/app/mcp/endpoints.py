"""Build the MCP endpoints that `create_app()` registers (ADR-015).

Both FastMCP servers are built per app, stateless with JSON responses, so no
MCP session, server-sent event stream or per-session state is kept. They are
served at exact routes wrapped in `McpBearerAuth`: `app.mount` would redirect
`/api/mcp/<server>` to a trailing slash. Stateless servers answer an
authenticated GET or DELETE with 405.
"""

from collections.abc import Callable
from dataclasses import dataclass

import anyio
from fastmcp import FastMCP
from fastmcp.server.http import StarletteWithLifespan
from sqlalchemy.orm import Session
from starlette.routing import Route

from app.api.v1.auth.rate_limit import FixedWindowRateLimiter
from app.core.config import Settings
from app.core.database import get_session_factory
from app.mcp.auth import McpBearerAuth, McpServerName
from app.mcp.read_server import build_read_server
from app.mcp.runtime import McpToolRuntime
from app.mcp.write_server import build_write_server

MCP_ROUTE_METHODS = ("GET", "POST", "DELETE")


@dataclass(frozen=True)
class McpEndpoint:
    route: Route
    # Its lifespan runs the server's session manager.
    http_app: StarletteWithLifespan


def build_mcp_endpoints(
    settings: Settings,
    *,
    rate_limiter: FixedWindowRateLimiter,
    session_factory: Callable[[], Session] | None = None,
) -> list[McpEndpoint]:
    """Build the read and write endpoints with one shared capacity limiter."""
    resolved_session_factory = session_factory or _new_session
    limiter = anyio.CapacityLimiter(settings.mcp_tool_concurrency)
    servers: dict[McpServerName, FastMCP] = {
        "read": build_read_server(McpToolRuntime(resolved_session_factory, limiter)),
        "write": build_write_server(),
    }
    endpoints: list[McpEndpoint] = []
    for name, server in servers.items():
        path = f"/api/mcp/{name}"
        http_app = server.http_app(path=path, stateless_http=True, json_response=True)
        auth = McpBearerAuth(
            http_app,
            server=name,
            settings=settings,
            session_factory=resolved_session_factory,
            limiter=limiter,
            rate_limiter=rate_limiter,
        )
        route = Route(
            path, endpoint=auth, methods=MCP_ROUTE_METHODS, include_in_schema=False
        )
        endpoints.append(McpEndpoint(route=route, http_app=http_app))
    return endpoints


def _new_session() -> Session:
    return get_session_factory()()
