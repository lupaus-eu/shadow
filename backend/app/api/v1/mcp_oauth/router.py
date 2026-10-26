"""Public MCP OAuth endpoints, registered only with `MCP_ENABLED=true`.

They live outside `/api/v1`, return RFC 6749 JSON errors and are rate-limited
by the separate `oauth_rate_limiter`, never the login `auth_rate_limiter`.
"""

import json
from typing import Literal, cast
from urllib.parse import parse_qsl

from fastapi import APIRouter, Request, Response, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, RedirectResponse

from app.api.v1.auth.dependencies import SessionDependency, SettingsDependency
from app.api.v1.auth.rate_limit import FixedWindowRateLimiter
from app.api.v1.mcp_oauth.schemas import (
    AuthorizationServerMetadata,
    ClientRegistrationResponse,
    OAuthErrorResponse,
    ProtectedResourceMetadata,
    TokenResponse,
)
from app.api.v1.mcp_oauth.service import (
    MCP_SERVER_SCOPES,
    OAuthError,
    canonical_resource,
    register_client,
    start_authorization,
)
from app.api.v1.mcp_oauth.token_service import issue_tokens, revoke_token
from app.core.config import Settings

OAuthBucket = Literal["register", "authorize", "token", "revoke"]
MAX_REGISTRATION_BODY_BYTES = 64 * 1024
MAX_FORM_BODY_BYTES = 16 * 1024
MAX_FORM_FIELDS = 20
FORM_CONTENT_TYPE = "application/x-www-form-urlencoded"

router = APIRouter(tags=["mcp-oauth"])
_ERROR_RESPONSES: dict[int | str, dict[str, object]] = {
    400: {"model": OAuthErrorResponse},
    429: {"model": OAuthErrorResponse},
}


@router.get(
    "/.well-known/oauth-authorization-server",
    response_model=AuthorizationServerMetadata,
)
def authorization_server_metadata(
    settings: SettingsDependency,
) -> AuthorizationServerMetadata:
    origin = settings.public_origin
    return AuthorizationServerMetadata(
        issuer=origin,
        authorization_endpoint=f"{origin}/api/oauth/authorize",
        token_endpoint=f"{origin}/api/oauth/token",
        registration_endpoint=f"{origin}/api/oauth/register",
        revocation_endpoint=f"{origin}/api/oauth/revoke",
        scopes_supported=list(MCP_SERVER_SCOPES.values()),
        response_types_supported=["code"],
        response_modes_supported=["query"],
        grant_types_supported=["authorization_code", "refresh_token"],
        token_endpoint_auth_methods_supported=["none"],
        revocation_endpoint_auth_methods_supported=["none"],
        code_challenge_methods_supported=["S256"],
        authorization_response_iss_parameter_supported=True,
    )


@router.get(
    "/.well-known/oauth-protected-resource/api/mcp/read",
    response_model=ProtectedResourceMetadata,
)
def read_resource_metadata(settings: SettingsDependency) -> ProtectedResourceMetadata:
    return _protected_resource_metadata(settings, "read")


@router.get(
    "/.well-known/oauth-protected-resource/api/mcp/write",
    response_model=ProtectedResourceMetadata,
)
def write_resource_metadata(
    settings: SettingsDependency,
) -> ProtectedResourceMetadata:
    return _protected_resource_metadata(settings, "write")


@router.post(
    "/api/oauth/register",
    status_code=status.HTTP_201_CREATED,
    response_model=ClientRegistrationResponse,
    responses={**_ERROR_RESPONSES, 503: {"model": OAuthErrorResponse}},
)
async def register(
    request: Request,
    session: SessionDependency,
    settings: SettingsDependency,
) -> Response:
    if not oauth_rate_limit_allows(request, settings, "register"):
        return rate_limited_response()
    try:
        metadata = await _read_json_body(request)
        registered = await run_in_threadpool(
            register_client,
            session,
            settings,
            metadata,
            client_ip=str(request.state.client_ip),
        )
    except OAuthError as exc:
        return oauth_error_response(exc)
    body = ClientRegistrationResponse(
        client_id=registered.client_id,
        client_id_issued_at=int(registered.created_time.timestamp()),
        client_name=registered.client_name,
        redirect_uris=registered.redirect_uris,
        grant_types=["authorization_code", "refresh_token"],
        response_types=["code"],
        token_endpoint_auth_method="none",
    )
    return JSONResponse(status_code=status.HTTP_201_CREATED, content=body.model_dump())


@router.get(
    "/api/oauth/authorize",
    status_code=status.HTTP_303_SEE_OTHER,
    response_class=RedirectResponse,
    responses=_ERROR_RESPONSES,
)
def authorize(
    request: Request,
    session: SessionDependency,
    settings: SettingsDependency,
) -> Response:
    if not oauth_rate_limit_allows(request, settings, "authorize"):
        return rate_limited_response()
    query: dict[str, list[str]] = {}
    for name, value in request.query_params.multi_items():
        query.setdefault(name, []).append(value)
    try:
        location = start_authorization(session, settings, query)
    except OAuthError as exc:
        return oauth_error_response(exc)
    return RedirectResponse(location, status_code=status.HTTP_303_SEE_OTHER)


@router.post(
    "/api/oauth/token",
    response_model=TokenResponse,
    responses=_ERROR_RESPONSES,
)
async def token(
    request: Request,
    session: SessionDependency,
    settings: SettingsDependency,
) -> Response:
    if not oauth_rate_limit_allows(request, settings, "token"):
        return rate_limited_response()
    try:
        parameters = await _read_form_body(request)
        issued = await run_in_threadpool(issue_tokens, session, settings, parameters)
    except OAuthError as exc:
        return oauth_error_response(exc)
    body = TokenResponse(
        access_token=issued.access_token,
        token_type="Bearer",
        expires_in=issued.expires_in,
        refresh_token=issued.refresh_token,
        scope=issued.scope,
    )
    return JSONResponse(content=body.model_dump())


@router.post("/api/oauth/revoke", responses=_ERROR_RESPONSES)
async def revoke(
    request: Request,
    session: SessionDependency,
    settings: SettingsDependency,
) -> Response:
    """RFC 7009: an unknown or foreign token also answers 200."""
    if not oauth_rate_limit_allows(request, settings, "revoke"):
        return rate_limited_response()
    try:
        parameters = await _read_form_body(request)
        await run_in_threadpool(revoke_token, session, parameters)
    except OAuthError as exc:
        return oauth_error_response(exc)
    return Response(status_code=status.HTTP_200_OK)


def oauth_rate_limit_allows(
    request: Request, settings: Settings, bucket: OAuthBucket
) -> bool:
    """Apply the per-endpoint `oauth_rate_limiter` bucket keyed by client IP."""
    limits: dict[OAuthBucket, int] = {
        "register": settings.mcp_oauth_register_rate_limit_per_minute,
        "authorize": settings.mcp_oauth_authorize_rate_limit_per_minute,
        "token": settings.mcp_oauth_token_rate_limit_per_minute,
        "revoke": settings.mcp_oauth_revoke_rate_limit_per_minute,
    }
    limiter = cast(FixedWindowRateLimiter, request.app.state.oauth_rate_limiter)
    return limiter.allow(bucket, str(request.state.client_ip), limits[bucket])


def rate_limited_response() -> JSONResponse:
    return oauth_error_response(
        OAuthError("temporarily_unavailable", "Too many requests", 429)
    )


def oauth_error_response(error: OAuthError) -> JSONResponse:
    body = OAuthErrorResponse(error=error.error, error_description=error.description)
    return JSONResponse(status_code=error.status_code, content=body.model_dump())


def _protected_resource_metadata(
    settings: Settings, server: str
) -> ProtectedResourceMetadata:
    return ProtectedResourceMetadata(
        resource=canonical_resource(settings, server),
        authorization_servers=[settings.public_origin],
        scopes_supported=[MCP_SERVER_SCOPES[server]],
        bearer_methods_supported=["header"],
    )


async def _read_json_body(request: Request) -> object:
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > MAX_REGISTRATION_BODY_BYTES:
            raise OAuthError("invalid_client_metadata", "Client metadata is too large")
    try:
        metadata: object = json.loads(body)
    except ValueError as exc:
        raise OAuthError(
            "invalid_client_metadata", "Client metadata must be JSON"
        ) from exc
    return metadata


async def _read_form_body(request: Request) -> dict[str, list[str]]:
    """Parse a bounded form body; empty values count as omitted (RFC 6749)."""
    content_type = request.headers.get("content-type", "")
    if content_type.split(";", 1)[0].strip().lower() != FORM_CONTENT_TYPE:
        raise OAuthError("invalid_request", f"The body must be {FORM_CONTENT_TYPE}")
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > MAX_FORM_BODY_BYTES:
            raise OAuthError("invalid_request", "The request body is too large")
    try:
        pairs = parse_qsl(
            body.decode("utf-8"),
            errors="strict",
            max_num_fields=MAX_FORM_FIELDS,
        )
    except ValueError as exc:
        raise OAuthError("invalid_request", "Malformed request body") from exc
    parameters: dict[str, list[str]] = {}
    for name, value in pairs:
        parameters.setdefault(name, []).append(value)
    return parameters
