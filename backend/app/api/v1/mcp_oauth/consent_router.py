"""Cookie-session consent API, registered only with `MCP_ENABLED=true`.

The pending request id travels only in the `request` query parameter (redacted
from access logs) and in JSON bodies, never in a URL path. The consent shows,
and the approval grants, only the requested scopes the User's role allows.
"""

from typing import Annotated

from fastapi import APIRouter, Query

from app.api.v1.auth.dependencies import (
    AuthHttpError,
    BusinessSessionDependency,
    SessionDependency,
    SettingsDependency,
    UnsafeRequestDependency,
)
from app.api.v1.mcp_oauth.schemas import (
    ConsentDecisionRequest,
    ConsentDecisionResponse,
    ConsentRequestResponse,
)
from app.api.v1.mcp_oauth.service import (
    ConsentError,
    approve_consent,
    deny_consent,
    load_consent,
)
from app.api.v1.mcp_oauth.token_service import allowed_scopes_for_role

router = APIRouter(prefix="/api/v1/ai/oauth", tags=["ai"])


@router.get("/consent", response_model=ConsentRequestResponse)
def get_consent(
    session: SessionDependency,
    settings: SettingsDependency,
    active: BusinessSessionDependency,
    request_id: Annotated[str | None, Query(alias="request")] = None,
) -> ConsentRequestResponse:
    try:
        consent = load_consent(
            session,
            settings,
            request_id,
            allowed_scopes=allowed_scopes_for_role(active.user.role),
        )
    except ConsentError as exc:
        raise _consent_http_error(exc) from exc
    return ConsentRequestResponse(
        clientName=consent.client_name,
        redirectIsLoopback=consent.redirect.is_loopback,
        redirectHost=consent.redirect.host,
        scope=consent.scope,
        resource=consent.resource,
        expiresTime=consent.expires_time,
    )


@router.post("/consent/approve", response_model=ConsentDecisionResponse)
def approve(
    payload: ConsentDecisionRequest,
    session: SessionDependency,
    settings: SettingsDependency,
    active: UnsafeRequestDependency,
) -> ConsentDecisionResponse:
    try:
        redirect_url = approve_consent(
            session,
            settings,
            payload.request,
            user_id=active.user.user_id,
            allowed_scopes=allowed_scopes_for_role(active.user.role),
        )
    except ConsentError as exc:
        raise _consent_http_error(exc) from exc
    return ConsentDecisionResponse(redirectUrl=redirect_url)


@router.post("/consent/deny", response_model=ConsentDecisionResponse)
def deny(
    payload: ConsentDecisionRequest,
    session: SessionDependency,
    settings: SettingsDependency,
    active: UnsafeRequestDependency,
) -> ConsentDecisionResponse:
    try:
        redirect_url = deny_consent(
            session, settings, payload.request, user_id=active.user.user_id
        )
    except ConsentError as exc:
        raise _consent_http_error(exc) from exc
    return ConsentDecisionResponse(redirectUrl=redirect_url)


def _consent_http_error(error: ConsentError) -> AuthHttpError:
    if error.reason == "expired":
        return AuthHttpError(
            410, "AUTHORIZATION_REQUEST_EXPIRED", "Authorization request expired"
        )
    if error.reason == "decided":
        return AuthHttpError(
            409,
            "AUTHORIZATION_REQUEST_DECIDED",
            "Authorization request already decided",
        )
    return AuthHttpError(
        404, "AUTHORIZATION_REQUEST_NOT_FOUND", "Authorization request not found"
    )
