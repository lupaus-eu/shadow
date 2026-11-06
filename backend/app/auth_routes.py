from collections.abc import Callable, Iterator
from typing import Literal

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session, sessionmaker

from app.auth import (
    AuthSettings,
    AuthenticatedUser,
    Clock,
    OIDCClient,
    authenticate_session,
    begin_login,
    complete_login,
    revoke_session,
)
from app.database import RequestContext, apply_request_context, transaction_session
from app.models import AccountClass, SupportedLocale

AuthenticatedUserDependency = Callable[[Request], Iterator[AuthenticatedUser]]


class UserAccountResponse(BaseModel):
    id: str
    account_class: str
    email: str
    display_name: str
    locale: str


class SessionResponse(BaseModel):
    user_account: UserAccountResponse


class LocaleRequest(BaseModel):
    locale: SupportedLocale


def create_authenticated_user_dependency(
    *,
    session_factory: sessionmaker[Session],
    clock: Clock,
    settings: AuthSettings,
    account_class: str = AccountClass.CUSTOMER.value,
) -> AuthenticatedUserDependency:
    """Authenticate the session cookie for one account class; the other class gets 403."""
    def get_authenticated_user(request: Request) -> Iterator[AuthenticatedUser]:
        with transaction_session(session_factory, RequestContext()) as session:
            authenticated_user = authenticate_session(
                session,
                session_token=request.cookies.get(settings.session_cookie_name),
                now=clock(),
                account_class=account_class,
            )
            apply_request_context(
                session,
                RequestContext(user_account_id=authenticated_user.account.id),
            )
            yield authenticated_user

    return get_authenticated_user


def create_auth_router(
    *,
    session_factory: sessionmaker[Session],
    oidc_client: OIDCClient,
    clock: Clock,
    settings: AuthSettings,
    authenticated_user_dependency: AuthenticatedUserDependency,
) -> APIRouter:
    router = APIRouter(prefix="/api/v1/auth", tags=["authentication"])

    def callback_url(request: Request) -> str:
        base_url = settings.public_api_base_url or str(request.base_url).rstrip("/")
        return f"{base_url}/api/v1/auth/callback"

    @router.get("/login")
    def login(request: Request, return_to: str | None = None, audience: Literal["customer", "platform"] = "customer") -> RedirectResponse:
        destination = return_to or ("/platform" if audience == AccountClass.PLATFORM.value else "/")
        if audience == AccountClass.PLATFORM.value and not destination.startswith("/platform"):
            destination = "/platform"
        with transaction_session(session_factory, RequestContext()) as session:
            login_start = begin_login(
                session,
                oidc_client,
                redirect_uri=callback_url(request),
                return_to=destination,
                now=clock(),
                settings=settings,
                audience=audience,
            )
        response = RedirectResponse(login_start.authorization_url)
        response.set_cookie(
            settings.flow_cookie_name,
            login_start.flow_token,
            max_age=int(settings.login_attempt_max_age.total_seconds()),
            httponly=True,
            secure=settings.cookie_secure,
            samesite="lax",
            path="/api/v1/auth/callback",
        )
        return response

    @router.get("/callback")
    def callback(request: Request, code: str, state: str) -> RedirectResponse:
        now = clock()
        with transaction_session(session_factory, RequestContext()) as session:
            completed_login = complete_login(
                session,
                oidc_client,
                code=code,
                state=state,
                flow_token=request.cookies.get(settings.flow_cookie_name),
                redirect_uri=callback_url(request),
                now=now,
                settings=settings,
            )
        frontend_destination = (
            f"{settings.frontend_url.rstrip('/')}{completed_login.return_to}"
        )
        response = RedirectResponse(frontend_destination, status_code=303)
        response.delete_cookie(
            settings.flow_cookie_name,
            path="/api/v1/auth/callback",
        )
        response.set_cookie(
            settings.session_cookie_name,
            completed_login.session_token,
            max_age=int((completed_login.expires_at - now).total_seconds()),
            httponly=True,
            secure=settings.cookie_secure,
            samesite="lax",
            path="/",
        )
        return response

    @router.get("/session", response_model=SessionResponse)
    def current_session(
        authenticated_user: AuthenticatedUser = Depends(
            authenticated_user_dependency
        ),
    ) -> SessionResponse:
        account = authenticated_user.account
        return SessionResponse(
            user_account=UserAccountResponse(
                id=str(account.id),
                account_class=account.account_class,
                email=account.email,
                display_name=account.display_name,
                locale=account.locale,
            )
        )

    @router.patch("/profile/locale", response_model=SessionResponse)
    def update_locale(
        locale_request: LocaleRequest,
        authenticated_user: AuthenticatedUser = Depends(
            authenticated_user_dependency
        ),
    ) -> SessionResponse:
        authenticated_user.account.locale = locale_request.locale.value
        return current_session(authenticated_user)

    @router.post("/logout")
    def logout(
        authenticated_user: AuthenticatedUser = Depends(
            authenticated_user_dependency
        ),
    ) -> Response:
        id_token_hint = revoke_session(authenticated_user, now=clock())
        response = RedirectResponse(
            oidc_client.end_session_url(
                post_logout_redirect_uri=settings.frontend_url,
                id_token_hint=id_token_hint,
            ),
            status_code=303,
        )
        response.delete_cookie(settings.session_cookie_name, path="/")
        return response

    return router
