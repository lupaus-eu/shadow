from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from ipaddress import IPv4Network, IPv6Network, ip_address
from typing import cast

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import RequestResponseEndpoint

from app.api.v1.auth.dependencies import AuthHttpError
from app.api.v1.auth.logging import install_sensitive_query_filter
from app.api.v1.auth.provider import AuthlibOidcProvider, OidcProvider
from app.api.v1.auth.rate_limit import FixedWindowRateLimiter
from app.api.v1.mcp_oauth.audit_log import install_mcp_oauth_audit_log
from app.api.v1.mcp_oauth.consent_router import router as mcp_oauth_consent_router
from app.api.v1.mcp_oauth.router import router as mcp_oauth_router
from app.api.v1.router import router as api_v1_router
from app.core.config import Settings, get_settings
from app.health.router import router as health_router

NO_STORE_PATH_PREFIXES = (
    "/api/v1/auth",
    "/api/v1/ai/oauth",
    "/api/oauth",
    "/.well-known/oauth-",
)


def create_app(
    *,
    settings: Settings | None = None,
    oidc_provider: OidcProvider | None = None,
) -> FastAPI:
    resolved_settings = settings or get_settings()
    resolved_settings.validate_auth_configuration()
    install_sensitive_query_filter()
    # The connections API revokes grants even with MCP_ENABLED=false.
    install_mcp_oauth_audit_log()
    resolved_provider = oidc_provider or AuthlibOidcProvider(resolved_settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncGenerator[None, None]:
        if resolved_settings.app_environment != "test":
            resolved_provider.initialize()
        yield

    if resolved_settings.app_environment == "test":
        app = FastAPI(title="Schatten API")
    else:
        app = FastAPI(title="Schatten API", lifespan=lifespan)
    app.state.settings = resolved_settings
    app.state.oidc_provider = resolved_provider
    app.state.auth_rate_limiter = FixedWindowRateLimiter()
    # ADR-015: OAuth traffic never consumes the login limiter's entries.
    app.state.oauth_rate_limiter = FixedWindowRateLimiter()

    async def auth_error_handler(request: Request, exc: Exception) -> JSONResponse:
        auth_error = cast(AuthHttpError, exc)
        response = JSONResponse(
            status_code=auth_error.status_code,
            content={
                "error": {
                    "code": auth_error.code,
                    "message": auth_error.message,
                }
            },
        )
        if (
            auth_error.code == "AUTHENTICATION_REQUIRED"
            and resolved_settings.session_cookie_name in request.cookies
        ):
            response.delete_cookie(
                resolved_settings.session_cookie_name,
                secure=resolved_settings.session_cookie_secure,
                httponly=True,
                samesite="strict",
                path="/",
            )
        return response

    app.add_exception_handler(AuthHttpError, auth_error_handler)

    async def authentication_boundary(
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        host_values = request.headers.getlist("host")
        if len(host_values) != 1 or host_values[0] != resolved_settings.public_host:
            response = JSONResponse(
                status_code=400,
                content={"error": {"code": "INVALID_HOST", "message": "Invalid host"}},
            )
        else:
            forwarded_values = request.headers.getlist("x-schatten-client-ip")
            peer = request.client.host if request.client is not None else ""
            trusted_peer = _is_trusted_peer(
                peer, resolved_settings.trusted_caddy_peer_cidrs
            )
            if forwarded_values and (
                len(forwarded_values) != 1
                or not trusted_peer
                or not _is_ip_address(forwarded_values[0])
            ):
                response = JSONResponse(
                    status_code=400,
                    content={
                        "error": {
                            "code": "UNTRUSTED_FORWARDED_HEADER",
                            "message": "Invalid forwarded client address",
                        }
                    },
                )
            else:
                request.state.client_ip = (
                    forwarded_values[0] if forwarded_values else peer
                )
                response = await call_next(request)
        if request.url.path.startswith(NO_STORE_PATH_PREFIXES):
            response.headers["Cache-Control"] = "no-store"
        return response

    if resolved_settings.app_environment == "development":
        app.add_middleware(
            CORSMiddleware,
            allow_origins=[resolved_settings.allowed_origin],
            allow_credentials=True,
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["Content-Type", "X-CSRF-Token"],
        )
    app.middleware("http")(authentication_boundary)
    app.include_router(health_router)
    app.include_router(api_v1_router)
    if resolved_settings.mcp_enabled:
        app.include_router(mcp_oauth_router)
        app.include_router(mcp_oauth_consent_router)
    return app


app = create_app()


def _is_trusted_peer(
    peer: str, networks: tuple[IPv4Network | IPv6Network, ...]
) -> bool:
    try:
        address = ip_address(peer)
    except ValueError:
        return False
    return any(address in network for network in networks)


def _is_ip_address(value: str) -> bool:
    try:
        ip_address(value)
    except ValueError:
        return False
    return True
