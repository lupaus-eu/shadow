import base64
import hashlib
import hmac
import os
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AccountClass,
    OIDCLoginAttempt,
    PlatformEnrollment,
    PlatformRole,
    SupportedLocale,
    UserAccount,
    UserSession,
)

Clock = Callable[[], datetime]


@dataclass(frozen=True)
class OIDCIdentity:
    issuer: str
    subject: str
    email: str
    email_verified: bool
    display_name: str
    expires_at: int
    id_token: str | None = None


class OIDCClient(Protocol):
    def authorization_url(
        self,
        *,
        state: str,
        nonce: str,
        code_challenge: str,
        redirect_uri: str,
    ) -> str: ...

    def exchange_code(
        self,
        *,
        code: str,
        code_verifier: str,
        nonce: str,
        redirect_uri: str,
    ) -> OIDCIdentity: ...

    def end_session_url(self, *, post_logout_redirect_uri: str, id_token_hint: str | None = None) -> str: ...


@dataclass(frozen=True)
class AuthSettings:
    session_cookie_name: str = "shadow_session"
    flow_cookie_name: str = "shadow_oidc_flow"
    cookie_secure: bool = False
    session_max_age: timedelta = timedelta(hours=8)
    login_attempt_max_age: timedelta = timedelta(minutes=10)
    public_api_base_url: str | None = None
    frontend_url: str = "http://localhost:8173"

    @classmethod
    def from_environment(cls) -> "AuthSettings":
        return cls(
            cookie_secure=os.getenv("AUTH_COOKIE_SECURE", "false").lower() == "true",
            session_max_age=timedelta(
                seconds=int(os.getenv("AUTH_SESSION_MAX_AGE_SECONDS", "28800"))
            ),
            public_api_base_url=os.getenv("PUBLIC_API_BASE_URL") or None,
            frontend_url=os.getenv("FRONTEND_URL", "http://localhost:8173"),
        )


@dataclass(frozen=True)
class LoginStart:
    authorization_url: str
    flow_token: str


@dataclass(frozen=True)
class AuthenticatedUser:
    account: UserAccount
    user_session: UserSession


@dataclass(frozen=True)
class CompletedLogin:
    account: UserAccount
    session_token: str
    expires_at: datetime
    return_to: str
    audience: str = AccountClass.CUSTOMER.value


def utc_now() -> datetime:
    return datetime.now(UTC)


def _token_hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _code_challenge(code_verifier: str) -> str:
    digest = hashlib.sha256(code_verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def safe_return_path(return_to: str) -> str:
    if return_to.startswith("/") and not return_to.startswith("//"):
        return return_to
    return "/"


def begin_login(
    session: Session,
    oidc_client: OIDCClient,
    *,
    redirect_uri: str,
    return_to: str,
    now: datetime,
    settings: AuthSettings,
    audience: str = AccountClass.CUSTOMER.value,
) -> LoginStart:
    state = secrets.token_urlsafe(32)
    flow_token = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    code_verifier = secrets.token_urlsafe(64)
    session.add(
        OIDCLoginAttempt(
            state_hash=_token_hash(state),
            flow_token_hash=_token_hash(flow_token),
            nonce=nonce,
            code_verifier=code_verifier,
            return_to=safe_return_path(return_to),
            audience=audience,
            expires_at=now + settings.login_attempt_max_age,
        )
    )
    return LoginStart(
        authorization_url=oidc_client.authorization_url(
            state=state,
            nonce=nonce,
            code_challenge=_code_challenge(code_verifier),
            redirect_uri=redirect_uri,
        ),
        flow_token=flow_token,
    )


def complete_login(
    session: Session,
    oidc_client: OIDCClient,
    *,
    code: str,
    state: str,
    flow_token: str | None,
    redirect_uri: str,
    now: datetime,
    settings: AuthSettings,
) -> CompletedLogin:
    attempt = session.scalar(
        select(OIDCLoginAttempt)
        .where(OIDCLoginAttempt.state_hash == _token_hash(state))
        .with_for_update()
    )
    if (
        attempt is None
        or flow_token is None
        or not hmac.compare_digest(
            attempt.flow_token_hash,
            _token_hash(flow_token),
        )
        or attempt.expires_at <= now
    ):
        raise HTTPException(status_code=400, detail="invalid login transaction")

    identity = oidc_client.exchange_code(
        code=code,
        code_verifier=attempt.code_verifier,
        nonce=attempt.nonce,
        redirect_uri=redirect_uri,
    )
    if not identity.email_verified:
        raise HTTPException(status_code=403, detail="verified email required")

    account = session.scalar(
        select(UserAccount).where(
            UserAccount.oidc_issuer == identity.issuer,
            UserAccount.oidc_subject == identity.subject,
        )
    )
    if attempt.audience == AccountClass.PLATFORM.value:
        account = _platform_account(session, account, identity, now=now)
    elif account is not None and account.account_class != AccountClass.CUSTOMER.value:
        raise HTTPException(status_code=403, detail="customer account required")
    if account is None:
        account = UserAccount(
            id=uuid4(),
            oidc_issuer=identity.issuer,
            oidc_subject=identity.subject,
            account_class=AccountClass.CUSTOMER.value,
            email=identity.email,
            display_name=identity.display_name,
            locale=SupportedLocale.ENGLISH.value,
        )
        session.add(account)
    else:
        account.email = identity.email
        account.display_name = identity.display_name

    identity_expiry = datetime.fromtimestamp(identity.expires_at, tz=UTC)
    session_expiry = min(identity_expiry, now + settings.session_max_age)
    if session_expiry <= now:
        raise HTTPException(status_code=401, detail="identity session expired")

    session_token = secrets.token_urlsafe(48)
    session.add(
        UserSession(
            id=uuid4(),
            user_account_id=account.id,
            token_hash=_token_hash(session_token),
            expires_at=session_expiry,
            id_token_hint=identity.id_token,
        )
    )
    session.delete(attempt)
    session.flush()
    return CompletedLogin(
        account=account,
        session_token=session_token,
        expires_at=session_expiry,
        return_to=attempt.return_to,
        audience=attempt.audience,
    )


def _platform_account(session: Session, account: UserAccount | None, identity: OIDCIdentity, *, now: datetime) -> UserAccount:
    """A Platform User for this identity: existing, or created from an unused enrollment (ADR-0021)."""
    if account is not None:
        if account.account_class != AccountClass.PLATFORM.value:
            raise HTTPException(status_code=403, detail="platform account required")
        account.email = identity.email
        account.display_name = identity.display_name
        return account
    enrollment = session.scalar(
        select(PlatformEnrollment)
        .where(
            PlatformEnrollment.email == identity.email.strip().lower(),
            PlatformEnrollment.consumed_at.is_(None),
            PlatformEnrollment.expires_at > now,
        )
        .order_by(PlatformEnrollment.created_at.desc())
        .with_for_update()
    )
    if enrollment is None:
        raise HTTPException(status_code=403, detail="platform enrollment required")
    account = UserAccount(
        id=uuid4(),
        oidc_issuer=identity.issuer,
        oidc_subject=identity.subject,
        account_class=AccountClass.PLATFORM.value,
        email=identity.email,
        display_name=identity.display_name,
        locale=SupportedLocale.ENGLISH.value,
    )
    session.add(account)
    session.flush()
    for role in enrollment.roles:
        session.add(PlatformRole(id=uuid4(), user_account_id=account.id, role=role))
    enrollment.consumed_at = now
    enrollment.user_account_id = account.id
    return account


def authenticate_session(
    session: Session,
    *,
    session_token: str | None,
    now: datetime,
    account_class: str = AccountClass.CUSTOMER.value,
) -> AuthenticatedUser:
    if session_token is None:
        raise HTTPException(status_code=401, detail="authentication required")

    user_session = session.scalar(
        select(UserSession).where(UserSession.token_hash == _token_hash(session_token))
    )
    if (
        user_session is None
        or user_session.revoked_at is not None
        or user_session.expires_at <= now
    ):
        raise HTTPException(status_code=401, detail="authentication required")

    account = session.get(UserAccount, user_session.user_account_id)
    if account is None or account.account_class != account_class:
        raise HTTPException(status_code=403, detail=f"{account_class} account required")
    return AuthenticatedUser(account=account, user_session=user_session)


def revoke_session(authenticated_user: AuthenticatedUser, *, now: datetime) -> str | None:
    """Revoke the session and hand back its ID token once, for the identity provider logout."""
    user_session = authenticated_user.user_session
    id_token_hint = user_session.id_token_hint
    user_session.revoked_at = now
    user_session.id_token_hint = None
    return id_token_hint
