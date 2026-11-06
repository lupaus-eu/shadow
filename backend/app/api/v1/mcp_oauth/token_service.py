"""AI Domain MCP OAuth tokens, revocation, verification and connections.

ADR-015: access and refresh tokens are opaque 256-bit CSPRNG values stored only
as SHA-256 hashes, and no token or code value is ever logged. Every grant
revocation is logged without a token, so its audit survives the grant row's
later deletion by lazy cleanup.
"""

import base64
import hashlib
import hmac
import logging
import re
import secrets
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal, NoReturn, cast
from uuid import uuid4

from sqlalchemy import (
    ColumnElement,
    CursorResult,
    delete,
    or_,
    select,
    text,
    update,
)
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import InstrumentedAttribute, Session

from app.api.v1.mcp_oauth.models import (
    McpOauthAuthorizationRequest,
    McpOauthClient,
    McpOauthGrant,
    McpOauthToken,
)
from app.api.v1.mcp_oauth.service import (
    CLEANUP_BATCH_SIZE,
    MAX_CLIENT_ID_LENGTH,
    MCP_SCOPES,
    READ_SCOPE,
    WRITE_SCOPE,
    OAuthError,
    advisory_transaction_lock,
    cleanup_stale_clients,
    narrow_scopes,
)
from app.api.v1.users.models import User
from app.core.config import Settings

logger = logging.getLogger(__name__)

LAST_USED_WRITE_INTERVAL = timedelta(minutes=5)
MAX_GRANT_KEY_LENGTH = 128
BIGINT_MAX = 2**63 - 1
# ADR-015: both current roles may use both scopes. This mapping is the one
# place that limits a role: a role without `shadow.write` sees only the read
# tools on the same endpoint, with no token format, URL or client change.
ROLE_SCOPES: dict[str, frozenset[str]] = {
    "admin": frozenset({READ_SCOPE, WRITE_SCOPE}),
    "consultant": frozenset({READ_SCOPE, WRITE_SCOPE}),
}
# PostgreSQL text values cannot contain NUL, so parameters with one are
# rejected before they reach the database.
_NUL = "\x00"
_OPAQUE_256_BIT_VALUE = re.compile(r"[A-Za-z0-9_-]{43}")
# RFC 7636 section 4.1.
_CODE_VERIFIER = re.compile(r"[A-Za-z0-9._~-]{43,128}")
# lock_not_available and deadlock_detected end a cleanup step early.
_CLEANUP_LOCK_CONFLICTS = frozenset({"55P03", "40P01"})

RevocationReason = Literal[
    "user_revoke",
    "admin_revoke",
    "client_revoke",
    "refresh_token_reuse",
    "code_reuse",
    "reauthorization",
]


class TokenVerificationError(Exception):
    """A rejected MCP bearer token: `invalid_token` or `insufficient_scope`."""

    def __init__(self, error: Literal["invalid_token", "insufficient_scope"]) -> None:
        super().__init__(error)
        self.error: Literal["invalid_token", "insufficient_scope"] = error


class ConnectionNotFound(Exception):
    """The User has no active grant with this key."""


class UserNotFound(Exception):
    """No User has this id."""


@dataclass(frozen=True)
class IssuedTokens:
    access_token: str
    refresh_token: str
    expires_in: int
    scope: str


@dataclass(frozen=True)
class McpPrincipal:
    """The verified actor of one MCP request."""

    user_id: int
    role: str
    grant_id: int
    grant_key: str
    client_id: str
    client_name: str
    scopes: frozenset[str]


@dataclass(frozen=True)
class McpConnection:
    grant_key: str
    client_id: str
    client_name: str
    scope: str
    resource: str
    created_time: datetime
    last_used_time: datetime | None
    expires_time: datetime


@dataclass(frozen=True)
class _Revocation:
    message: str
    reason: RevocationReason
    actor: str
    user_id: int
    grant_key: str
    client_id: str
    client_name: str
    revoked_tokens: int


def allowed_scopes_for_role(role: str) -> frozenset[str]:
    return ROLE_SCOPES.get(role, frozenset())


def issue_tokens(
    session: Session,
    settings: Settings,
    parameters: Mapping[str, Sequence[str]],
    *,
    now: datetime | None = None,
) -> IssuedTokens:
    """Handle an `authorization_code` or `refresh_token` token request.

    Lazy cleanup runs first, in its own transaction.
    """
    current = now or datetime.now(UTC)
    grant_type = _single_parameter(parameters, "grant_type")
    if grant_type is None:
        raise OAuthError("invalid_request", "grant_type is required")
    if grant_type not in {"authorization_code", "refresh_token"}:
        raise OAuthError("unsupported_grant_type", "Unsupported grant_type")
    cleanup_expired_oauth_rows(session, now=current)
    if grant_type == "authorization_code":
        return _exchange_authorization_code(session, settings, parameters, current)
    return _refresh(session, settings, parameters, current)


def revoke_token(
    session: Session,
    parameters: Mapping[str, Sequence[str]],
    *,
    now: datetime | None = None,
) -> None:
    """RFC 7009 revocation by a public client.

    Revoking a refresh token revokes its grant and all the grant's tokens;
    revoking an access token revokes only that token. An unknown token, or one
    issued to another client, is treated as invalid and needs no action.
    """
    current = now or datetime.now(UTC)
    token = _required_parameter(parameters, "token")
    # The hint is optional and only an optimisation; every kind is searched.
    _single_parameter(parameters, "token_type_hint")
    client = _load_client(session, parameters)
    grant, stored = _lock_grant_and_token(session, token, kind=None)
    if (
        grant is None
        or stored is None
        or grant.mcp_oauth_client_id != client.mcp_oauth_client_id
    ):
        session.rollback()
        return
    revocation: _Revocation | None = None
    if stored.kind == "refresh":
        if _is_active(grant, current):
            revocation = _revoke_grant(
                session,
                grant,
                reason="client_revoke",
                actor="client",
                revoked_by=None,
                now=current,
            )
    elif stored.revoked_time is None:
        stored.revoked_time = current
    session.commit()
    if revocation is not None:
        _log_revocation(revocation)


def verify_access_token(
    session: Session,
    token: str | None,
    required_resource: str,
    required_scope: str,
    *,
    now: datetime | None = None,
) -> McpPrincipal:
    """Verify an MCP bearer token for the resource and a minimum scope (ADR-015).

    Every call re-reads the token, grant, client and User, so revocation,
    expiry, User soft deletion and role changes take effect on the next call.
    The principal carries the effective scopes, the grant's scopes that the
    User's role allows, which each MCP tool checks for its own scope.
    """
    current = now or datetime.now(UTC)
    stored = (
        session.scalar(
            select(McpOauthToken).where(
                McpOauthToken.token_hash == _sha256(token),
                McpOauthToken.kind == "access",
            )
        )
        if token is not None and _OPAQUE_256_BIT_VALUE.fullmatch(token)
        else None
    )
    if (
        stored is None
        or stored.revoked_time is not None
        or _as_utc(stored.expires_time) <= current
    ):
        _reject(session, "invalid_token")
    grant = session.get(McpOauthGrant, stored.grant_id)
    if (
        grant is None
        or not _is_active(grant, current)
        or grant.resource != required_resource
    ):
        _reject(session, "invalid_token")
    user = _active_user(session, grant.user_id)
    client = session.get(McpOauthClient, grant.mcp_oauth_client_id)
    if user is None or client is None:
        _reject(session, "invalid_token")
    scopes = frozenset(grant.scopes.split()) & allowed_scopes_for_role(user.role)
    if required_scope not in scopes:
        _reject(session, "insufficient_scope")
    principal = McpPrincipal(
        user_id=user.user_id,
        role=user.role,
        grant_id=grant.grant_id,
        grant_key=grant.grant_key,
        client_id=client.client_id,
        client_name=client.client_name,
        scopes=scopes,
    )
    _touch_grant(session, grant.grant_id, current)
    session.commit()
    return principal


def list_connections(
    session: Session, *, user_id: int, role: str, now: datetime | None = None
) -> list[McpConnection]:
    """List the User's active grants, newest first, with their effective scopes."""
    allowed_scopes = allowed_scopes_for_role(role)
    current = now or datetime.now(UTC)
    rows = session.execute(
        select(McpOauthGrant, McpOauthClient)
        .join(
            McpOauthClient,
            McpOauthClient.mcp_oauth_client_id == McpOauthGrant.mcp_oauth_client_id,
        )
        .where(
            McpOauthGrant.user_id == user_id,
            McpOauthGrant.revoked_time.is_(None),
            McpOauthGrant.expires_time > current,
        )
        .order_by(McpOauthGrant.created_time.desc(), McpOauthGrant.grant_id.desc())
    ).tuples()
    return [
        McpConnection(
            grant_key=grant.grant_key,
            client_id=client.client_id,
            client_name=client.client_name,
            scope=narrow_scopes(grant.scopes, allowed_scopes),
            resource=grant.resource,
            created_time=_as_utc(grant.created_time),
            last_used_time=(
                _as_utc(grant.last_used_time)
                if grant.last_used_time is not None
                else None
            ),
            expires_time=_as_utc(grant.expires_time),
        )
        for grant, client in rows
    ]


def revoke_connection(
    session: Session,
    grant_key: str,
    *,
    user_id: int,
    now: datetime | None = None,
) -> None:
    """Revoke one of the User's own active grants and all its tokens."""
    current = now or datetime.now(UTC)
    grant = (
        session.scalar(
            select(McpOauthGrant)
            .where(
                McpOauthGrant.grant_key == grant_key,
                McpOauthGrant.user_id == user_id,
                McpOauthGrant.revoked_time.is_(None),
                McpOauthGrant.expires_time > current,
            )
            .with_for_update(key_share=True)
        )
        if len(grant_key) <= MAX_GRANT_KEY_LENGTH and _NUL not in grant_key
        else None
    )
    if grant is None:
        session.rollback()
        raise ConnectionNotFound(grant_key)
    revocation = _revoke_grant(
        session,
        grant,
        reason="user_revoke",
        actor=f"user:{user_id}",
        revoked_by=user_id,
        now=current,
    )
    session.commit()
    _log_revocation(revocation)


def revoke_user_connections(
    session: Session,
    target_user_id: int,
    *,
    admin_user_id: int,
    now: datetime | None = None,
) -> int:
    """Revoke every active grant of one User; return the number revoked.

    A soft-deleted User's grants can be revoked too (ADR-015 offboarding and
    incident procedure).
    """
    current = now or datetime.now(UTC)
    if (
        not -BIGINT_MAX - 1 <= target_user_id <= BIGINT_MAX
        or session.get(User, target_user_id) is None
    ):
        session.rollback()
        raise UserNotFound(target_user_id)
    grants = session.scalars(
        select(McpOauthGrant)
        .where(
            McpOauthGrant.user_id == target_user_id,
            McpOauthGrant.revoked_time.is_(None),
            McpOauthGrant.expires_time > current,
        )
        .order_by(McpOauthGrant.grant_id)
        .with_for_update(key_share=True)
    ).all()
    revocations = [
        _revoke_grant(
            session,
            grant,
            reason="admin_revoke",
            actor=f"user:{admin_user_id}",
            revoked_by=admin_user_id,
            now=current,
        )
        for grant in grants
    ]
    session.commit()
    for revocation in revocations:
        _log_revocation(revocation)
    return len(revocations)


def cleanup_expired_oauth_rows(session: Session, *, now: datetime) -> None:
    """Lazily delete expired OAuth rows during token operations.

    It deletes expired authorization requests (once their code has expired
    too), expired access tokens, and revoked or expired grants. The database
    deletes a grant's tokens with it and sets references to it to null.
    Replaced refresh tokens of an active grant are never deleted, because reuse
    detection depends on them. The client cleanup runs last, once these
    references are gone.

    Candidates are locked `FOR UPDATE SKIP LOCKED`, but a grant deletion's
    cascades can still wait for rows that another operation holds. Each step
    therefore commits on its own, so it never holds another step's locks, and
    runs with a PostgreSQL `lock_timeout` below the default 1 s
    `deadlock_timeout`. Cleanup is best effort: a step that hits the timeout
    or a deadlock is rolled back and left to a later token request, and the
    token request continues.
    """
    steps: tuple[Callable[[Session, datetime], None], ...] = (
        _delete_expired_requests,
        _delete_expired_access_tokens,
        _delete_inactive_grants,
    )
    for step in steps:
        try:
            if session.get_bind().dialect.name == "postgresql":
                session.execute(text("SET LOCAL lock_timeout = '500ms'"))
            step(session, now)
            session.commit()
        except OperationalError as exc:
            session.rollback()
            if getattr(exc.orig, "sqlstate", None) not in _CLEANUP_LOCK_CONFLICTS:
                raise
            logger.warning(
                "MCP OAuth lazy cleanup step %s skipped after a lock conflict",
                step.__name__,
            )
    cleanup_stale_clients(session, now=now)


def _delete_expired_requests(session: Session, now: datetime) -> None:
    request_hashes = session.scalars(
        select(McpOauthAuthorizationRequest.request_id_hash)
        .where(
            McpOauthAuthorizationRequest.expires_time <= now,
            or_(
                McpOauthAuthorizationRequest.code_expires_time.is_(None),
                McpOauthAuthorizationRequest.code_expires_time <= now,
            ),
        )
        .limit(CLEANUP_BATCH_SIZE)
        .with_for_update(skip_locked=True)
    ).all()
    if request_hashes:
        session.execute(
            delete(McpOauthAuthorizationRequest).where(
                McpOauthAuthorizationRequest.request_id_hash.in_(request_hashes)
            )
        )


def _delete_expired_access_tokens(session: Session, now: datetime) -> None:
    access_hashes = session.scalars(
        select(McpOauthToken.token_hash)
        .where(McpOauthToken.kind == "access", McpOauthToken.expires_time <= now)
        .limit(CLEANUP_BATCH_SIZE)
        .with_for_update(skip_locked=True)
    ).all()
    if access_hashes:
        session.execute(
            delete(McpOauthToken).where(McpOauthToken.token_hash.in_(access_hashes))
        )


def _delete_inactive_grants(session: Session, now: datetime) -> None:
    grant_ids = session.scalars(
        select(McpOauthGrant.grant_id)
        .where(
            or_(
                McpOauthGrant.revoked_time.is_not(None),
                McpOauthGrant.expires_time <= now,
            )
        )
        .order_by(McpOauthGrant.grant_id)
        .limit(CLEANUP_BATCH_SIZE)
        .with_for_update(skip_locked=True)
    ).all()
    if grant_ids:
        session.execute(
            delete(McpOauthGrant).where(McpOauthGrant.grant_id.in_(grant_ids))
        )


def _exchange_authorization_code(
    session: Session,
    settings: Settings,
    parameters: Mapping[str, Sequence[str]],
    now: datetime,
) -> IssuedTokens:
    code = _required_parameter(parameters, "code")
    redirect_uri = _required_parameter(parameters, "redirect_uri")
    code_verifier = _required_parameter(parameters, "code_verifier")
    resource = _resource_parameter(parameters)
    client = _load_client(session, parameters)
    pending = (
        session.scalar(
            select(McpOauthAuthorizationRequest)
            .where(McpOauthAuthorizationRequest.code_hash == _sha256(code))
            .with_for_update()
        )
        if _OPAQUE_256_BIT_VALUE.fullmatch(code)
        else None
    )
    if pending is None:
        _fail(session, "invalid_grant", "Invalid authorization code")
    if pending.consumed_time is not None:
        _revoke_redeemed_code_grant(session, pending, now)
        raise OAuthError("invalid_grant", "Authorization code already used")
    if pending.mcp_oauth_client_id != client.mcp_oauth_client_id:
        _fail(session, "invalid_grant", "Invalid authorization code")
    if pending.code_expires_time is None or _as_utc(pending.code_expires_time) <= now:
        _fail(session, "invalid_grant", "Authorization code expired")
    if redirect_uri != pending.redirect_uri:
        _fail(session, "invalid_grant", "redirect_uri does not match")
    if not _code_verifier_matches(code_verifier, pending.code_challenge):
        _fail(session, "invalid_grant", "code_verifier does not match")
    if resource != pending.resource:
        _fail(session, "invalid_target", "resource does not match the request")
    user = (
        _active_user(session, pending.user_id) if pending.user_id is not None else None
    )
    if user is None:
        _fail(session, "invalid_grant", "Invalid authorization code")

    pending.consumed_time = now
    revocation: _Revocation | None = None
    grant = _reusable_grant(session, client, user.user_id, pending.resource, now)
    if grant is None:
        grant = McpOauthGrant(
            grant_key=f"grant_{uuid4().hex}",
            mcp_oauth_client_id=client.mcp_oauth_client_id,
            user_id=user.user_id,
            scopes=pending.scopes,
            resource=pending.resource,
            created_time=now,
            expires_time=now
            + timedelta(seconds=settings.mcp_oauth_grant_lifetime_seconds),
        )
        session.add(grant)
        session.flush()
    else:
        # A reused grant keeps its expiry and takes the newest consent's scopes;
        # its earlier tokens are revoked, so a stale refresh chain fails as
        # revoked instead of triggering reuse detection against this
        # authorization.
        grant.scopes = pending.scopes
        revocation = _revocation(
            session,
            grant,
            message="MCP OAuth grant tokens revoked",
            reason="reauthorization",
            actor=f"user:{user.user_id}",
            revoked_tokens=_revoke_grant_tokens(session, grant.grant_id, now),
        )
    pending.grant_id = grant.grant_id
    issued, _ = _issue_token_pair(session, settings, grant, user, now)
    _touch_client(session, client, now)
    session.commit()
    if revocation is not None:
        _log_revocation(revocation)
    return issued


def _refresh(
    session: Session,
    settings: Settings,
    parameters: Mapping[str, Sequence[str]],
    now: datetime,
) -> IssuedTokens:
    refresh_token = _required_parameter(parameters, "refresh_token")
    resource = _resource_parameter(parameters)
    scope = _single_parameter(parameters, "scope")
    client = _load_client(session, parameters)
    grant, token = _lock_grant_and_token(session, refresh_token, kind="refresh")
    if (
        grant is None
        or token is None
        or grant.mcp_oauth_client_id != client.mcp_oauth_client_id
    ):
        _fail(session, "invalid_grant", "Invalid refresh token")
    if resource != grant.resource:
        _fail(session, "invalid_target", "resource does not match the grant")
    # Tokens carry no scope of their own, so a sent scope cannot narrow one:
    # the token keeps the grant's scopes, and the response names them.
    if scope is not None and not frozenset(scope.split(" ")) <= frozenset(MCP_SCOPES):
        _fail(session, "invalid_scope", "Unknown scope")

    # ADR-015's check order; the first match decides.
    if not _is_active(grant, now):
        _fail(session, "invalid_grant", "The grant is revoked or expired")
    if token.revoked_time is not None:
        _fail(session, "invalid_grant", "Refresh token revoked")
    if token.replaced_by_hash is not None:
        revocation = _revoke_grant(
            session,
            grant,
            reason="refresh_token_reuse",
            actor="system",
            revoked_by=None,
            now=now,
        )
        session.commit()
        _log_revocation(revocation)
        raise OAuthError("invalid_grant", "Refresh token already used")
    if _as_utc(token.expires_time) <= now:
        _fail(session, "invalid_grant", "Refresh token expired")
    user = _active_user(session, grant.user_id)
    if user is None:
        _fail(session, "invalid_grant", "Invalid refresh token")

    issued, refresh_hash = _issue_token_pair(session, settings, grant, user, now)
    # Rotation only links the replacement; it never sets revoked_time.
    token.replaced_by_hash = refresh_hash
    session.flush()
    _touch_client(session, client, now)
    session.commit()
    return issued


def _lock_grant_and_token(
    session: Session, raw_token: str, *, kind: Literal["refresh"] | None
) -> tuple[McpOauthGrant | None, McpOauthToken | None]:
    """Lock a token's grant, then the token: the order of every revocation."""
    if _OPAQUE_256_BIT_VALUE.fullmatch(raw_token) is None:
        return None, None
    token_hash = _sha256(raw_token)
    lookup = select(McpOauthToken.grant_id).where(
        McpOauthToken.token_hash == token_hash
    )
    if kind is not None:
        lookup = lookup.where(McpOauthToken.kind == kind)
    grant_id = session.scalar(lookup)
    if grant_id is None:
        return None, None
    grant = session.scalar(
        select(McpOauthGrant)
        .where(McpOauthGrant.grant_id == grant_id)
        .with_for_update(key_share=True)
    )
    token = session.scalar(
        select(McpOauthToken)
        .where(McpOauthToken.token_hash == token_hash)
        .with_for_update()
    )
    return grant, token


def _reusable_grant(
    session: Session,
    client: McpOauthClient,
    user_id: int,
    resource: str,
    now: datetime,
) -> McpOauthGrant | None:
    """Return the User's active grant for this client and resource, locked.

    A transaction-scoped advisory lock per client, User and resource makes a
    concurrent exchange wait and then reuse this exchange's grant instead of
    creating a second active grant.
    """
    lock_name = (
        f"shadow.mcp_oauth.grant:{client.mcp_oauth_client_id}:{user_id}:{resource}"
    )
    advisory_transaction_lock(
        session,
        int.from_bytes(
            hashlib.sha256(lock_name.encode("utf-8")).digest()[:8],
            byteorder="big",
            signed=True,
        ),
    )
    return session.scalar(
        select(McpOauthGrant)
        .where(
            McpOauthGrant.mcp_oauth_client_id == client.mcp_oauth_client_id,
            McpOauthGrant.user_id == user_id,
            McpOauthGrant.resource == resource,
            McpOauthGrant.revoked_time.is_(None),
            McpOauthGrant.expires_time > now,
        )
        .order_by(McpOauthGrant.grant_id.desc())
        .limit(1)
        .with_for_update(key_share=True)
    )


def _revoke_redeemed_code_grant(
    session: Session, pending: McpOauthAuthorizationRequest, now: datetime
) -> None:
    """Revoke the active grant a second redemption of a code points to.

    Lazy cleanup may already have deleted the grant and set `grant_id` to
    null; then nothing is left to revoke.
    """
    grant = (
        session.scalar(
            select(McpOauthGrant)
            .where(
                McpOauthGrant.grant_id == pending.grant_id,
                McpOauthGrant.revoked_time.is_(None),
                McpOauthGrant.expires_time > now,
            )
            .with_for_update(key_share=True)
        )
        if pending.grant_id is not None
        else None
    )
    revocation = (
        _revoke_grant(
            session,
            grant,
            reason="code_reuse",
            actor="system",
            revoked_by=None,
            now=now,
        )
        if grant is not None
        else None
    )
    session.commit()
    if revocation is not None:
        _log_revocation(revocation)


def _issue_token_pair(
    session: Session,
    settings: Settings,
    grant: McpOauthGrant,
    user: User,
    now: datetime,
) -> tuple[IssuedTokens, bytes]:
    """Store a new access and refresh token; no token outlives its grant.

    The response `scope` is the effective set, the grant's scopes that the
    User's current role allows, which may differ from the request (RFC 6749
    section 5.1).
    """
    access_token = secrets.token_urlsafe(32)
    refresh_token = secrets.token_urlsafe(32)
    refresh_hash = _sha256(refresh_token)
    grant_expires = _as_utc(grant.expires_time)
    access_expires = min(
        now + timedelta(seconds=settings.mcp_oauth_access_token_lifetime_seconds),
        grant_expires,
    )
    refresh_expires = min(
        now + timedelta(seconds=settings.mcp_oauth_refresh_token_idle_lifetime_seconds),
        grant_expires,
    )
    session.add_all(
        [
            McpOauthToken(
                token_hash=_sha256(access_token),
                grant_id=grant.grant_id,
                kind="access",
                created_time=now,
                expires_time=access_expires,
            ),
            McpOauthToken(
                token_hash=refresh_hash,
                grant_id=grant.grant_id,
                kind="refresh",
                created_time=now,
                expires_time=refresh_expires,
            ),
        ]
    )
    session.flush()
    issued = IssuedTokens(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=int((access_expires - now).total_seconds()),
        scope=narrow_scopes(grant.scopes, allowed_scopes_for_role(user.role)),
    )
    return issued, refresh_hash


def _revoke_grant(
    session: Session,
    grant: McpOauthGrant,
    *,
    reason: RevocationReason,
    actor: str,
    revoked_by: int | None,
    now: datetime,
) -> _Revocation:
    grant.revoked_time = now
    grant.revoked_by = revoked_by
    session.flush()
    return _revocation(
        session,
        grant,
        message="MCP OAuth grant revoked",
        reason=reason,
        actor=actor,
        revoked_tokens=_revoke_grant_tokens(session, grant.grant_id, now),
    )


def _revoke_grant_tokens(session: Session, grant_id: int, now: datetime) -> int:
    result = cast(
        CursorResult[Any],
        session.execute(
            update(McpOauthToken)
            .where(
                McpOauthToken.grant_id == grant_id,
                McpOauthToken.revoked_time.is_(None),
            )
            .values(revoked_time=now)
            .execution_options(synchronize_session=False)
        ),
    )
    return result.rowcount


def _revocation(
    session: Session,
    grant: McpOauthGrant,
    *,
    message: str,
    reason: RevocationReason,
    actor: str,
    revoked_tokens: int,
) -> _Revocation:
    client = session.get(McpOauthClient, grant.mcp_oauth_client_id)
    return _Revocation(
        message=message,
        reason=reason,
        actor=actor,
        user_id=grant.user_id,
        grant_key=grant.grant_key,
        client_id=client.client_id if client is not None else "",
        client_name=client.client_name if client is not None else "",
        revoked_tokens=revoked_tokens,
    )


def _log_revocation(revocation: _Revocation) -> None:
    logger.info(
        "%s: reason=%s actor=%s user_id=%d grant_key=%s client_id=%s "
        "self_declared_client_name=%r revoked_tokens=%d",
        revocation.message,
        revocation.reason,
        revocation.actor,
        revocation.user_id,
        revocation.grant_key,
        revocation.client_id,
        revocation.client_name,
        revocation.revoked_tokens,
    )


def _touch_client(session: Session, client: McpOauthClient, now: datetime) -> None:
    """Write the client's `last_used_time` at most every five minutes.

    This is a token operation's last write before commit. It can wait briefly
    for an in-flight authorize's client row lock (`FOR NO KEY UPDATE`), while
    the grant and token inserts before it take only key-share locks on the
    client and never wait.
    """
    session.execute(
        update(McpOauthClient)
        .where(
            McpOauthClient.mcp_oauth_client_id == client.mcp_oauth_client_id,
            _last_used_is_stale(McpOauthClient.last_used_time, now),
        )
        .values(last_used_time=now)
        .execution_options(synchronize_session=False)
    )


def _touch_grant(session: Session, grant_id: int, now: datetime) -> None:
    """Write the grant's `last_used_time` at most every five minutes."""
    session.execute(
        update(McpOauthGrant)
        .where(
            McpOauthGrant.grant_id == grant_id,
            _last_used_is_stale(McpOauthGrant.last_used_time, now),
        )
        .values(last_used_time=now)
        .execution_options(synchronize_session=False)
    )


def _last_used_is_stale(
    column: InstrumentedAttribute[datetime | None], now: datetime
) -> ColumnElement[bool]:
    return or_(column.is_(None), column <= now - LAST_USED_WRITE_INTERVAL)


def _load_client(
    session: Session, parameters: Mapping[str, Sequence[str]]
) -> McpOauthClient:
    """Identify the public client; a soft-deleted client cannot obtain tokens."""
    client_id = _single_parameter(parameters, "client_id")
    if client_id is None or len(client_id) > MAX_CLIENT_ID_LENGTH:
        raise OAuthError("invalid_client", "Unknown client")
    client = session.scalar(
        select(McpOauthClient).where(McpOauthClient.client_id == client_id)
    )
    if client is None or client.deleted_time is not None:
        _fail(session, "invalid_client", "Unknown client")
    return client


def _active_user(session: Session, user_id: int) -> User | None:
    # ADR-016: an MCP grant acts as a customer account; a person reclassified as an
    # operator (platform account) loses the access of grants made earlier.
    return session.scalar(
        select(User).where(
            User.user_id == user_id,
            User.deleted_time.is_(None),
            User.account_class == "customer",
        )
    )


def _is_active(grant: McpOauthGrant, now: datetime) -> bool:
    return grant.revoked_time is None and _as_utc(grant.expires_time) > now


def _single_parameter(parameters: Mapping[str, Sequence[str]], name: str) -> str | None:
    values = parameters.get(name, ())
    if len(values) > 1:
        raise OAuthError("invalid_request", f"{name} must not be repeated")
    if values and _NUL in values[0]:
        raise OAuthError("invalid_request", f"Invalid {name}")
    return values[0] if values else None


def _required_parameter(parameters: Mapping[str, Sequence[str]], name: str) -> str:
    value = _single_parameter(parameters, name)
    if value is None:
        raise OAuthError("invalid_request", f"{name} is required")
    return value


def _resource_parameter(parameters: Mapping[str, Sequence[str]]) -> str:
    resources = parameters.get("resource", ())
    if len(resources) != 1:
        raise OAuthError("invalid_target", "Exactly one resource is required")
    return resources[0]


def _code_verifier_matches(code_verifier: str, code_challenge: str) -> bool:
    if _CODE_VERIFIER.fullmatch(code_verifier) is None:
        return False
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    computed = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return hmac.compare_digest(computed, code_challenge)


def _fail(session: Session, error: str, description: str) -> NoReturn:
    session.rollback()
    raise OAuthError(error, description)


def _reject(
    session: Session, error: Literal["invalid_token", "insufficient_scope"]
) -> NoReturn:
    session.rollback()
    raise TokenVerificationError(error)


def _sha256(value: str) -> bytes:
    return hashlib.sha256(value.encode("utf-8")).digest()


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
