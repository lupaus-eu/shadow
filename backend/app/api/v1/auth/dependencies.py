import hmac
from typing import Annotated, cast

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.api.v1.auth.provider import OidcProvider
from app.api.v1.auth.service import (
    ActiveSession,
    load_active_session,
    touch_active_session,
)
from app.core.config import Settings
from app.core.database import get_db_session


class AuthHttpError(Exception):
    def __init__(self, status_code: int, code: str, message: str) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message


def get_auth_settings(request: Request) -> Settings:
    return cast(Settings, request.app.state.settings)


def get_oidc_provider(request: Request) -> OidcProvider:
    return cast(OidcProvider, request.app.state.oidc_provider)


SessionDependency = Annotated[Session, Depends(get_db_session)]
SettingsDependency = Annotated[Settings, Depends(get_auth_settings)]
ProviderDependency = Annotated[OidcProvider, Depends(get_oidc_provider)]


def _load_authenticated_session_without_activity(
    request: Request,
    session: SessionDependency,
    settings: SettingsDependency,
) -> ActiveSession:
    active = load_active_session(
        session,
        settings,
        request.cookies.get(settings.session_cookie_name),
        touch_activity=False,
    )
    if active is None:
        raise AuthHttpError(401, "AUTHENTICATION_REQUIRED", "Authentication required")
    return active


UntouchedAuthenticatedSessionDependency = Annotated[
    ActiveSession, Depends(_load_authenticated_session_without_activity)
]


def require_authenticated_session(
    session: SessionDependency,
    settings: SettingsDependency,
    active: UntouchedAuthenticatedSessionDependency,
) -> ActiveSession:
    touch_active_session(session, settings, active)
    return active


AuthenticatedSessionDependency = Annotated[
    ActiveSession, Depends(require_authenticated_session)
]


def require_admin(active: AuthenticatedSessionDependency) -> ActiveSession:
    if active.user.role != "admin":
        raise AuthHttpError(403, "FORBIDDEN", "Forbidden")
    return active


AdminSessionDependency = Annotated[ActiveSession, Depends(require_admin)]


def require_unsafe_request(
    request: Request,
    session: SessionDependency,
    settings: SettingsDependency,
    active: UntouchedAuthenticatedSessionDependency,
) -> ActiveSession:
    origins = request.headers.getlist("origin")
    csrf_tokens = request.headers.getlist("x-csrf-token")
    if (
        len(origins) != 1
        or origins[0] == "null"
        or origins[0] != settings.allowed_origin
        or len(csrf_tokens) != 1
        or not hmac.compare_digest(
            csrf_tokens[0].encode(), active.auth_session.csrf_token.encode()
        )
    ):
        raise AuthHttpError(403, "FORBIDDEN", "Forbidden")
    touch_active_session(session, settings, active)
    return active


UnsafeRequestDependency = Annotated[ActiveSession, Depends(require_unsafe_request)]
