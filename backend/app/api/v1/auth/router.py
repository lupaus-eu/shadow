from fastapi import APIRouter, Request, Response, status
from fastapi.responses import RedirectResponse

from app.api.v1.auth.dependencies import (
    AuthenticatedSessionDependency,
    AuthHttpError,
    ProviderDependency,
    SessionDependency,
    SettingsDependency,
    UnsafeRequestDependency,
)
from app.api.v1.auth.provider import OidcProviderError
from app.api.v1.auth.schemas import (
    LogoutResponse,
    SessionFeatures,
    SessionResponse,
)
from app.api.v1.auth.service import (
    GENERIC_ERROR_PATH,
    AuthenticationError,
    LoginRateLimited,
    consume_login,
    create_session,
    delete_session,
    resolve_identity,
    start_login,
)
from app.api.v1.users.service import to_user_response

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/login")
def login(
    request: Request,
    session: SessionDependency,
    settings: SettingsDependency,
    provider: ProviderDependency,
    return_to: str | None = None,
) -> Response:
    _enforce_rate_limit(request, "login", 20)
    try:
        started = start_login(
            session,
            settings,
            return_to=return_to,
            existing_browser_binding=request.cookies.get("shadow-preauth"),
            authorization_url_factory=provider.authorization_url,
        )
    except LoginRateLimited as exc:
        raise AuthHttpError(429, "RATE_LIMITED", "Too many requests") from exc
    except AuthenticationError as exc:
        raise AuthHttpError(400, "INVALID_RETURN_PATH", "Invalid return path") from exc
    except OidcProviderError as exc:
        raise AuthHttpError(
            503, "AUTHENTICATION_UNAVAILABLE", "Authentication unavailable"
        ) from exc
    response = RedirectResponse(
        started.authorization_url, status_code=status.HTTP_302_FOUND
    )
    if started.set_browser_cookie:
        response.set_cookie(
            "shadow-preauth",
            started.browser_binding,
            max_age=settings.oidc_transaction_lifetime_seconds,
            secure=settings.session_cookie_secure,
            httponly=True,
            samesite="lax",
            path="/",
        )
    return response


@router.get("/callback")
def callback(
    request: Request,
    session: SessionDependency,
    settings: SettingsDependency,
    provider: ProviderDependency,
) -> Response:
    _enforce_rate_limit(request, "callback", 60)
    state_values = request.query_params.getlist("state")
    state = state_values[0] if len(state_values) == 1 else None
    consumed = consume_login(
        session,
        state=state,
        browser_binding=request.cookies.get("shadow-preauth"),
    )
    if consumed is None:
        return RedirectResponse(
            f"{settings.public_origin}{GENERIC_ERROR_PATH}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    target = GENERIC_ERROR_PATH
    new_raw_session_id: str | None = None
    try:
        error_values = request.query_params.getlist("error")
        code_values = request.query_params.getlist("code")
        if error_values or len(code_values) != 1 or not code_values[0]:
            raise AuthenticationError("Provider callback failed")
        claims = provider.exchange_code(
            code=code_values[0],
            nonce=consumed.nonce,
            pkce_verifier=consumed.pkce_verifier,
        )
        user = resolve_identity(session, claims)
        created = create_session(
            session,
            settings,
            user=user,
            presented_session_id=request.cookies.get(settings.session_cookie_name),
            id_token=claims.id_token,
        )
        new_raw_session_id = created.raw_session_id
        target = consumed.return_to
    except Exception:
        session.rollback()

    response = RedirectResponse(
        f"{settings.public_origin}{target}",
        status_code=status.HTTP_303_SEE_OTHER,
    )
    response.delete_cookie(
        "shadow-preauth",
        secure=settings.session_cookie_secure,
        httponly=True,
        samesite="lax",
        path="/",
    )
    if new_raw_session_id is not None:
        response.set_cookie(
            settings.session_cookie_name,
            new_raw_session_id,
            max_age=settings.auth_session_absolute_lifetime_seconds,
            secure=settings.session_cookie_secure,
            httponly=True,
            samesite="strict",
            path="/",
        )
    return response


@router.get("/session", response_model=SessionResponse)
def session_status(
    active: AuthenticatedSessionDependency,
    settings: SettingsDependency,
) -> SessionResponse:
    return SessionResponse(
        user=to_user_response(active.user),
        csrfToken=active.auth_session.csrf_token,
        features=SessionFeatures(
            mcp=settings.mcp_enabled,
            mcpChangeSetReview=settings.mcp_change_set_review_active,
        ),
    )


@router.post("/logout", response_model=LogoutResponse)
def logout(
    response: Response,
    session: SessionDependency,
    settings: SettingsDependency,
    provider: ProviderDependency,
    active: UnsafeRequestDependency,
) -> LogoutResponse:
    # Read before the row is deleted: the hint ends Authentik's session as well.
    id_token_hint = active.auth_session.id_token
    delete_session(session, active)
    response.delete_cookie(
        settings.session_cookie_name,
        secure=settings.session_cookie_secure,
        httponly=True,
        samesite="strict",
        path="/",
    )
    return LogoutResponse(logoutUrl=provider.logout_url(id_token_hint=id_token_hint))


def _enforce_rate_limit(request: Request, bucket: str, limit: int) -> None:
    address = str(request.state.client_ip)
    if not request.app.state.auth_rate_limiter.allow(bucket, address, limit):
        raise AuthHttpError(429, "RATE_LIMITED", "Too many requests")
