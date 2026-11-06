import hashlib
import hmac
import re
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol
from urllib.parse import urlsplit

from sqlalchemy import delete, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.v1.auth.provider import NormalizedClaims
from app.api.v1.users.models import (
    AuthSession,
    OidcLoginTransaction,
    User,
    UserIdentity,
)
from app.core.config import Settings

MAX_LIVE_TRANSACTIONS = 5
GENERIC_ERROR_PATH = "/login?error=authentication_failed"
_VALID_PERCENT_ESCAPE = re.compile(r"%(?:[0-9A-Fa-f]{2})")
_OPAQUE_256_BIT_TOKEN = re.compile(r"[A-Za-z0-9_-]{43}")


class AuthenticationError(Exception):
    """Generic authentication failure that reveals no identity details."""


class LoginRateLimited(AuthenticationError):
    """The per-browser live transaction cap has been reached."""


class AuthorizationUrlFactory(Protocol):
    def __call__(self, *, state: str, nonce: str, pkce_verifier: str) -> str: ...


@dataclass(frozen=True)
class LoginStart:
    authorization_url: str
    browser_binding: str
    set_browser_cookie: bool


@dataclass(frozen=True)
class ConsumedLogin:
    nonce: str
    pkce_verifier: str
    return_to: str


@dataclass(frozen=True)
class ActiveSession:
    auth_session: AuthSession
    user: User


@dataclass(frozen=True)
class NewSession:
    raw_session_id: str
    active: ActiveSession


def validate_return_to(value: str | None) -> str:
    if value is None:
        return "/"
    if not value.startswith("/") or value.startswith("//"):
        raise AuthenticationError("Invalid return path")
    if "\\" in value or any(
        ord(character) < 32 or 127 <= ord(character) <= 159 for character in value
    ):
        raise AuthenticationError("Invalid return path")
    if any(
        value[index] == "%"
        and _VALID_PERCENT_ESCAPE.fullmatch(value[index : index + 3]) is None
        for index in range(len(value))
    ):
        raise AuthenticationError("Invalid return path")
    parsed = urlsplit(value)
    if parsed.scheme or parsed.netloc or parsed.fragment:
        raise AuthenticationError("Invalid return path")
    return value


def start_login(
    session: Session,
    settings: Settings,
    *,
    return_to: str | None,
    existing_browser_binding: str | None,
    authorization_url_factory: AuthorizationUrlFactory,
) -> LoginStart:
    clean_return_to = validate_return_to(return_to)
    now = datetime.now(UTC)
    session.execute(
        delete(OidcLoginTransaction).where(OidcLoginTransaction.expires_time <= now)
    )
    session.commit()
    reusable_binding = (
        existing_browser_binding
        if existing_browser_binding is not None
        and _OPAQUE_256_BIT_TOKEN.fullmatch(existing_browser_binding)
        else None
    )
    browser_binding = reusable_binding or secrets.token_urlsafe(32)
    binding_hash = _sha256(browser_binding)
    _lock_binding_transaction(session, binding_hash)
    live_count = session.scalar(
        select(func.count())
        .select_from(OidcLoginTransaction)
        .where(
            OidcLoginTransaction.browser_binding_hash == binding_hash,
            OidcLoginTransaction.expires_time > now,
        )
    )
    if live_count is None or live_count >= MAX_LIVE_TRANSACTIONS:
        session.rollback()
        raise LoginRateLimited("Too many live login transactions")

    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    pkce_verifier = secrets.token_urlsafe(48)
    session.add(
        OidcLoginTransaction(
            state_hash=_sha256(state),
            browser_binding_hash=binding_hash,
            nonce=nonce,
            pkce_verifier=pkce_verifier,
            return_to=clean_return_to,
            created_time=now,
            expires_time=now
            + timedelta(seconds=settings.oidc_transaction_lifetime_seconds),
        )
    )
    try:
        session.commit()
        url = authorization_url_factory(
            state=state,
            nonce=nonce,
            pkce_verifier=pkce_verifier,
        )
    except Exception:
        session.rollback()
        session.execute(
            delete(OidcLoginTransaction).where(
                OidcLoginTransaction.state_hash == _sha256(state)
            )
        )
        session.commit()
        raise
    return LoginStart(
        authorization_url=url,
        browser_binding=browser_binding,
        set_browser_cookie=reusable_binding is None,
    )


def consume_login(
    session: Session,
    *,
    state: str | None,
    browser_binding: str | None,
) -> ConsumedLogin | None:
    if (
        state is None
        or browser_binding is None
        or _OPAQUE_256_BIT_TOKEN.fullmatch(state) is None
        or _OPAQUE_256_BIT_TOKEN.fullmatch(browser_binding) is None
    ):
        return None
    binding_hash = _sha256(browser_binding)
    _lock_binding_transaction(session, binding_hash)
    state_hash = _sha256(state)
    transaction = session.scalar(
        select(OidcLoginTransaction)
        .where(OidcLoginTransaction.state_hash == state_hash)
        .with_for_update()
    )
    if transaction is None:
        session.rollback()
        return None
    now = datetime.now(UTC)
    stored_binding = bytes(transaction.browser_binding_hash)
    if _as_utc(transaction.expires_time) <= now or not hmac.compare_digest(
        stored_binding, binding_hash
    ):
        session.rollback()
        return None
    consumed = ConsumedLogin(
        nonce=transaction.nonce,
        pkce_verifier=transaction.pkce_verifier,
        return_to=transaction.return_to,
    )
    session.execute(
        delete(OidcLoginTransaction).where(
            OidcLoginTransaction.browser_binding_hash == stored_binding
        )
    )
    session.commit()
    return consumed


def resolve_identity(session: Session, claims: NormalizedClaims) -> User:
    now = datetime.now(UTC)
    identity = session.scalar(
        select(UserIdentity)
        .where(
            UserIdentity.issuer == claims.issuer,
            UserIdentity.subject == claims.subject,
        )
        .with_for_update()
    )
    if identity is not None:
        user = session.scalar(
            select(User).where(
                User.user_id == identity.user_id,
                User.deleted_time.is_(None),
            )
        )
        if user is None:
            session.rollback()
            raise AuthenticationError("Identity resolution failed")
        identity.last_login_time = now
        session.commit()
        return user

    if claims.email is None:
        session.rollback()
        raise AuthenticationError("Identity resolution failed")
    candidates = session.scalars(
        select(User)
        .where(
            func.lower(func.trim(User.email)) == claims.email,
            User.deleted_time.is_(None),
        )
        .with_for_update()
        .limit(2)
    ).all()
    if len(candidates) != 1:
        session.rollback()
        raise AuthenticationError("Identity resolution failed")
    user = candidates[0]
    issuer_binding = session.scalar(
        select(UserIdentity.user_identity_id).where(
            UserIdentity.user_id == user.user_id,
            UserIdentity.issuer == claims.issuer,
        )
    )
    if issuer_binding is not None:
        session.rollback()
        raise AuthenticationError("Identity resolution failed")
    session.add(
        UserIdentity(
            user_id=user.user_id,
            issuer=claims.issuer,
            subject=claims.subject,
            created_time=now,
            last_login_time=now,
        )
    )
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise AuthenticationError("Identity resolution failed") from exc
    return user


def create_session(
    session: Session,
    settings: Settings,
    *,
    user: User,
    presented_session_id: str | None,
    id_token: str | None = None,
) -> NewSession:
    now = datetime.now(UTC)
    session.execute(
        delete(AuthSession).where(
            (AuthSession.absolute_expires_time <= now)
            | (
                AuthSession.last_activity_time
                <= now - timedelta(seconds=settings.auth_session_idle_timeout_seconds)
            )
        )
    )
    if presented_session_id:
        session.execute(
            delete(AuthSession).where(
                AuthSession.session_id_hash == _sha256(presented_session_id)
            )
        )
    raw_session_id = secrets.token_urlsafe(32)
    auth_session = AuthSession(
        session_id_hash=_sha256(raw_session_id),
        user_id=user.user_id,
        csrf_token=secrets.token_urlsafe(32),
        id_token=id_token or None,
        created_time=now,
        last_activity_time=now,
        absolute_expires_time=now
        + timedelta(seconds=settings.auth_session_absolute_lifetime_seconds),
    )
    session.add(auth_session)
    session.commit()
    return NewSession(
        raw_session_id=raw_session_id,
        active=ActiveSession(auth_session=auth_session, user=user),
    )


def load_active_session(
    session: Session,
    settings: Settings,
    raw_session_id: str | None,
    *,
    touch_activity: bool = True,
) -> ActiveSession | None:
    if (
        raw_session_id is None
        or _OPAQUE_256_BIT_TOKEN.fullmatch(raw_session_id) is None
    ):
        return None
    auth_session = session.scalar(
        select(AuthSession).where(
            AuthSession.session_id_hash == _sha256(raw_session_id)
        )
    )
    if auth_session is None:
        return None
    now = datetime.now(UTC)
    if (
        _as_utc(auth_session.absolute_expires_time) <= now
        or _as_utc(auth_session.last_activity_time)
        + timedelta(seconds=settings.auth_session_idle_timeout_seconds)
        <= now
    ):
        session.delete(auth_session)
        session.commit()
        return None
    user = session.scalar(
        select(User).where(
            User.user_id == auth_session.user_id,
            User.deleted_time.is_(None),
        )
    )
    if user is None:
        session.delete(auth_session)
        session.commit()
        return None
    active = ActiveSession(auth_session=auth_session, user=user)
    if touch_activity:
        touch_active_session(session, settings, active)
    return active


def touch_active_session(
    session: Session,
    settings: Settings,
    active: ActiveSession,
) -> None:
    now = datetime.now(UTC)
    if (
        _as_utc(active.auth_session.last_activity_time)
        + timedelta(seconds=settings.auth_session_activity_write_seconds)
        <= now
    ):
        active.auth_session.last_activity_time = now
        session.commit()


def delete_session(session: Session, active: ActiveSession) -> None:
    session.delete(active.auth_session)
    session.commit()


def _sha256(value: str) -> bytes:
    return hashlib.sha256(value.encode("utf-8")).digest()


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _lock_binding_transaction(session: Session, binding_hash: bytes) -> None:
    if session.get_bind().dialect.name != "postgresql":
        return
    lock_key = int.from_bytes(binding_hash[:8], byteorder="big", signed=True)
    session.execute(
        text("SELECT pg_advisory_xact_lock(:lock_key)"), {"lock_key": lock_key}
    )
