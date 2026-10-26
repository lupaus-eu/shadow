"""AI Domain MCP OAuth 2.1 discovery, registration, authorization and consent.

ADR-015: request ids and codes are CSPRNG values stored only as SHA-256
hashes, and they are never logged.
"""

import hashlib
import logging
import re
import secrets
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal, cast
from urllib.parse import urlencode, urlsplit

from sqlalchemy import and_, delete, exists, func, or_, select, text, update
from sqlalchemy.orm import Session

from app.api.v1.mcp_oauth.models import (
    McpOauthAuthorizationRequest,
    McpOauthClient,
    McpOauthGrant,
)
from app.core.config import MCP_LOOPBACK_REDIRECT_ENTRY, Settings

logger = logging.getLogger(__name__)

READ_SCOPE = "schatten.read"
WRITE_SCOPE = "schatten.write"
MCP_SERVER_SCOPES = {"read": READ_SCOPE, "write": WRITE_SCOPE}
CLIENT_STALE_AFTER = timedelta(days=30)
CLEANUP_BATCH_SIZE = 1000
MAX_CLIENT_NAME_LENGTH = 100
MAX_REDIRECT_URIS = 10
MAX_REDIRECT_URI_LENGTH = 2048
MAX_CLIENT_ID_LENGTH = 128
CONSENT_PATH = "/ai/authorize"
# PostgreSQL text values cannot contain NUL, so stored or queried parameters
# with one are rejected before they reach the database.
_NUL = "\x00"

_CLIENT_NAME_CHARACTERS = re.compile(r"[A-Za-z0-9 .\-_():/+]+")
_CLIENT_NAME_LETTER_OR_DIGIT = re.compile(r"[A-Za-z0-9]")
_OPAQUE_256_BIT_VALUE = re.compile(r"[A-Za-z0-9_-]{43}")
_REGISTRATION_LOCK_KEY = int.from_bytes(
    hashlib.sha256(b"schatten.mcp_oauth.client_registration").digest()[:8],
    byteorder="big",
    signed=True,
)
_PENDING_REQUESTS_LOCK_KEY = int.from_bytes(
    hashlib.sha256(b"schatten.mcp_oauth.pending_requests").digest()[:8],
    byteorder="big",
    signed=True,
)


class OAuthError(Exception):
    """An RFC 6749 style error that is returned to the caller, never redirected."""

    def __init__(self, error: str, description: str, status_code: int = 400) -> None:
        super().__init__(description)
        self.error = error
        self.description = description
        self.status_code = status_code


class ConsentError(Exception):
    def __init__(self, reason: Literal["not_found", "expired", "decided"]) -> None:
        super().__init__(reason)
        self.reason: Literal["not_found", "expired", "decided"] = reason


class _RedirectedError(Exception):
    def __init__(self, error: str) -> None:
        super().__init__(error)
        self.error = error


@dataclass(frozen=True)
class RedirectTarget:
    """A redirect URI that matched one `MCP_OAUTH_REDIRECT_URIS` entry."""

    uri: str
    is_loopback: bool
    host: str
    path: str


@dataclass(frozen=True)
class RegisteredClient:
    client_id: str
    client_name: str
    redirect_uris: list[str]
    created_time: datetime


@dataclass(frozen=True)
class PendingConsent:
    client_name: str
    redirect: RedirectTarget
    scope: str
    resource: str
    expires_time: datetime


def canonical_resources(settings: Settings) -> dict[str, str]:
    """Map each canonical MCP resource URI to its single scope."""
    return {
        canonical_resource(settings, server): scope
        for server, scope in MCP_SERVER_SCOPES.items()
    }


def canonical_resource(settings: Settings, server: str) -> str:
    return f"{settings.public_origin}/api/mcp/{server}"


def validate_client_name(value: object) -> str:
    """Apply ADR-015's ASCII allowlist and return the trimmed name."""
    if not isinstance(value, str):
        raise OAuthError("invalid_client_metadata", "client_name is required")
    name = value.strip(" ")
    if (
        not 1 <= len(name) <= MAX_CLIENT_NAME_LENGTH
        or _CLIENT_NAME_CHARACTERS.fullmatch(name) is None
        or _CLIENT_NAME_LETTER_OR_DIGIT.search(name) is None
    ):
        raise OAuthError("invalid_client_metadata", "Invalid client_name")
    return name


def match_redirect_uri(settings: Settings, uri: str) -> RedirectTarget | None:
    """Match a URI against the allowlist by exact or structured loopback rules.

    Exact entries match by whole-string equality. Loopback entries match only
    `http://<entry host>:<port 1-65535><entry path>`, with no userinfo, query
    or fragment; prefixes and globs never match.
    """
    if len(uri) > MAX_REDIRECT_URI_LENGTH:
        return None
    for entry in settings.mcp_oauth_redirect_uris:
        loopback = MCP_LOOPBACK_REDIRECT_ENTRY.fullmatch(entry)
        if loopback is None:
            if uri == entry:
                return RedirectTarget(
                    uri=uri,
                    is_loopback=False,
                    host=_url_form_host(uri),
                    path=urlsplit(uri).path,
                )
            continue
        host = loopback.group("host")
        path = loopback.group("path")
        if _loopback_port(uri, host, path) is not None:
            return RedirectTarget(uri=uri, is_loopback=True, host=host, path=path)
    return None


def register_client(
    session: Session,
    settings: Settings,
    metadata: object,
    *,
    client_ip: str | None,
    now: datetime | None = None,
) -> RegisteredClient:
    """RFC 7591 registration of a public client with allowlisted redirect URIs."""
    if not isinstance(metadata, dict):
        raise OAuthError(
            "invalid_client_metadata", "Client metadata must be a JSON object"
        )
    fields = cast(dict[str, object], metadata)
    if fields.get("token_endpoint_auth_method", "none") != "none":
        raise OAuthError(
            "invalid_client_metadata",
            "Only public clients with token_endpoint_auth_method none are supported",
        )
    client_name = validate_client_name(fields.get("client_name"))
    redirect_uris = _validated_redirect_uris(settings, fields.get("redirect_uris"))

    current = now or datetime.now(UTC)
    cleanup_stale_clients(session, now=current)
    advisory_transaction_lock(session, _REGISTRATION_LOCK_KEY)
    client_count = session.scalar(
        select(func.count())
        .select_from(McpOauthClient)
        .where(McpOauthClient.deleted_time.is_(None))
    )
    if client_count is None or client_count >= settings.mcp_oauth_max_clients:
        session.rollback()
        logger.warning(
            "MCP OAuth client registration refused: the cap of %d non-deleted "
            "clients is reached",
            settings.mcp_oauth_max_clients,
        )
        raise OAuthError(
            "temporarily_unavailable",
            "Client registration is temporarily unavailable",
            503,
        )
    client = McpOauthClient(
        client_id=secrets.token_urlsafe(32),
        client_name=client_name,
        redirect_uris=redirect_uris,
        created_time=current,
        created_ip=client_ip or None,
    )
    session.add(client)
    session.commit()
    logger.info(
        "MCP OAuth client registered: client_id=%s self_declared_client_name=%r",
        client.client_id,
        client_name,
    )
    return RegisteredClient(
        client_id=client.client_id,
        client_name=client_name,
        redirect_uris=redirect_uris,
        created_time=current,
    )


def cleanup_stale_clients(session: Session, *, now: datetime) -> None:
    """Soft-delete stale clients, then hard-delete unreferenced deleted ones.

    Candidates are locked `FOR UPDATE SKIP LOCKED`, so cleanup never waits for
    a client that an in-flight authorize holds and never deletes it.
    """
    active_grant = exists().where(
        McpOauthGrant.mcp_oauth_client_id == McpOauthClient.mcp_oauth_client_id,
        McpOauthGrant.revoked_time.is_(None),
        McpOauthGrant.expires_time > now,
    )
    stale_ids = session.scalars(
        select(McpOauthClient.mcp_oauth_client_id)
        .where(
            McpOauthClient.deleted_time.is_(None),
            func.coalesce(McpOauthClient.last_used_time, McpOauthClient.created_time)
            < now - CLIENT_STALE_AFTER,
            ~active_grant,
        )
        .order_by(McpOauthClient.mcp_oauth_client_id)
        .limit(CLEANUP_BATCH_SIZE)
        .with_for_update(skip_locked=True)
    ).all()
    if stale_ids:
        session.execute(
            update(McpOauthClient)
            .where(McpOauthClient.mcp_oauth_client_id.in_(stale_ids))
            .values(deleted_time=now)
        )

    referenced = or_(
        exists().where(
            McpOauthAuthorizationRequest.mcp_oauth_client_id
            == McpOauthClient.mcp_oauth_client_id
        ),
        exists().where(
            McpOauthGrant.mcp_oauth_client_id == McpOauthClient.mcp_oauth_client_id
        ),
    )
    unreferenced_ids = session.scalars(
        select(McpOauthClient.mcp_oauth_client_id)
        .where(McpOauthClient.deleted_time.is_not(None), ~referenced)
        .order_by(McpOauthClient.mcp_oauth_client_id)
        .limit(CLEANUP_BATCH_SIZE)
        .with_for_update(skip_locked=True)
    ).all()
    if unreferenced_ids:
        session.execute(
            delete(McpOauthClient).where(
                McpOauthClient.mcp_oauth_client_id.in_(unreferenced_ids)
            )
        )
    session.commit()


def start_authorization(
    session: Session,
    settings: Settings,
    query: Mapping[str, Sequence[str]],
    *,
    now: datetime | None = None,
) -> str:
    """Validate and store a pending request; return the 303 Location.

    Invalid client or redirect URI errors raise `OAuthError` and are shown.
    Every later error returns a redirect to the validated redirect URI.
    """
    current = now or datetime.now(UTC)
    client_ids = query.get("client_id", ())
    redirect_uris = query.get("redirect_uri", ())
    if (
        len(client_ids) != 1
        or not 1 <= len(client_ids[0]) <= MAX_CLIENT_ID_LENGTH
        or _NUL in client_ids[0]
    ):
        raise OAuthError("invalid_client", "Unknown client")
    client = session.scalar(
        select(McpOauthClient)
        .where(McpOauthClient.client_id == client_ids[0])
        .with_for_update(key_share=True)
    )
    if client is None or client.deleted_time is not None:
        session.rollback()
        raise OAuthError("invalid_client", "Unknown client")
    target = (
        _registered_redirect_target(settings, client, redirect_uris[0])
        if len(redirect_uris) == 1
        else None
    )
    if target is None:
        session.rollback()
        raise OAuthError("invalid_request", "Invalid redirect_uri")

    states = query.get("state", ())
    # A repeated state, or one PostgreSQL cannot store, is invalid and not echoed.
    valid_state = len(states) <= 1 and all(_NUL not in value for value in states)
    state = states[0] if states and valid_state else None
    try:
        if not valid_state:
            raise _RedirectedError("invalid_request")
        code_challenge, scope, resource = _validated_authorization_parameters(
            settings, query
        )
        _enforce_pending_request_caps(session, settings, client, current)
    except _RedirectedError as exc:
        session.rollback()
        return build_redirect_url(settings, target.uri, [("error", exc.error)], state)

    request_id = secrets.token_urlsafe(32)
    session.add(
        McpOauthAuthorizationRequest(
            request_id_hash=_sha256(request_id),
            mcp_oauth_client_id=client.mcp_oauth_client_id,
            redirect_uri=target.uri,
            state=state,
            code_challenge=code_challenge,
            scopes=scope,
            resource=resource,
            created_time=current,
            expires_time=current
            + timedelta(
                seconds=settings.mcp_oauth_authorization_request_lifetime_seconds
            ),
        )
    )
    session.flush()
    client.last_used_time = current
    session.commit()
    consent_query = urlencode({"request": request_id})
    return f"{settings.public_origin}{CONSENT_PATH}?{consent_query}"


def build_redirect_url(
    settings: Settings,
    redirect_uri: str,
    parameters: Sequence[tuple[str, str]],
    state: str | None,
) -> str:
    """Build every authorization response redirect: `parameters`, `state`, `iss`.

    Allowlisted redirect URIs carry no query or fragment of their own.
    """
    query = list(parameters)
    if state is not None:
        query.append(("state", state))
    query.append(("iss", settings.public_origin))
    return f"{redirect_uri}?{urlencode(query)}"


def load_consent(
    session: Session,
    settings: Settings,
    raw_request_id: str | None,
    *,
    now: datetime | None = None,
) -> PendingConsent:
    pending, client, target = _load_undecided_request(
        session, settings, raw_request_id, now or datetime.now(UTC), lock=False
    )
    return PendingConsent(
        client_name=client.client_name,
        redirect=target,
        scope=pending.scopes,
        resource=pending.resource,
        expires_time=_as_utc(pending.expires_time),
    )


def approve_consent(
    session: Session,
    settings: Settings,
    raw_request_id: str | None,
    *,
    user_id: int,
    now: datetime | None = None,
) -> str:
    """Record the User, store a hashed one-time code and return the redirect."""
    current = now or datetime.now(UTC)
    pending, _, target = _load_undecided_request(
        session, settings, raw_request_id, current, lock=True
    )
    code = secrets.token_urlsafe(32)
    pending.user_id = user_id
    pending.code_hash = _sha256(code)
    pending.code_expires_time = current + timedelta(
        seconds=settings.mcp_oauth_authorization_code_lifetime_seconds
    )
    state = pending.state
    session.commit()
    return build_redirect_url(settings, target.uri, [("code", code)], state)


def deny_consent(
    session: Session,
    settings: Settings,
    raw_request_id: str | None,
    *,
    user_id: int,
    now: datetime | None = None,
) -> str:
    """Record the deciding User without a code and return `access_denied`."""
    pending, _, target = _load_undecided_request(
        session, settings, raw_request_id, now or datetime.now(UTC), lock=True
    )
    pending.user_id = user_id
    state = pending.state
    session.commit()
    return build_redirect_url(settings, target.uri, [("error", "access_denied")], state)


def _load_undecided_request(
    session: Session,
    settings: Settings,
    raw_request_id: str | None,
    now: datetime,
    *,
    lock: bool,
) -> tuple[McpOauthAuthorizationRequest, McpOauthClient, RedirectTarget]:
    if (
        raw_request_id is None
        or _OPAQUE_256_BIT_VALUE.fullmatch(raw_request_id) is None
    ):
        raise ConsentError("not_found")
    statement = select(McpOauthAuthorizationRequest).where(
        McpOauthAuthorizationRequest.request_id_hash == _sha256(raw_request_id)
    )
    if lock:
        statement = statement.with_for_update()
    pending = session.scalar(statement)
    client = (
        session.get(McpOauthClient, pending.mcp_oauth_client_id)
        if pending is not None
        else None
    )
    target = (
        match_redirect_uri(settings, pending.redirect_uri)
        if pending is not None
        else None
    )
    if (
        pending is None
        or client is None
        or client.deleted_time is not None
        or target is None
    ):
        session.rollback()
        raise ConsentError("not_found")
    if pending.user_id is not None:
        session.rollback()
        raise ConsentError("decided")
    if _as_utc(pending.expires_time) <= now:
        session.rollback()
        raise ConsentError("expired")
    return pending, client, target


def _validated_authorization_parameters(
    settings: Settings, query: Mapping[str, Sequence[str]]
) -> tuple[str, str, str]:
    response_type = _single_parameter(query, "response_type")
    if response_type != "code":
        raise _RedirectedError(
            "invalid_request" if response_type is None else "unsupported_response_type"
        )
    code_challenge = _single_parameter(query, "code_challenge")
    if (
        code_challenge is None
        or _OPAQUE_256_BIT_VALUE.fullmatch(code_challenge) is None
        or _single_parameter(query, "code_challenge_method") != "S256"
    ):
        raise _RedirectedError("invalid_request")
    resources = query.get("resource", ())
    resource_scopes = canonical_resources(settings)
    if len(resources) != 1 or resources[0] not in resource_scopes:
        raise _RedirectedError("invalid_target")
    resource = resources[0]
    expected_scope = resource_scopes[resource]
    scopes = query.get("scope")
    if scopes is not None and list(scopes) != [expected_scope]:
        raise _RedirectedError("invalid_scope")
    return code_challenge, expected_scope, resource


def _single_parameter(query: Mapping[str, Sequence[str]], name: str) -> str | None:
    values = query.get(name, ())
    if len(values) > 1:
        raise _RedirectedError("invalid_request")
    return values[0] if values else None


def _enforce_pending_request_caps(
    session: Session,
    settings: Settings,
    client: McpOauthClient,
    now: datetime,
) -> None:
    live = and_(
        McpOauthAuthorizationRequest.user_id.is_(None),
        McpOauthAuthorizationRequest.expires_time > now,
    )
    client_count = session.scalar(
        select(func.count())
        .select_from(McpOauthAuthorizationRequest)
        .where(
            live,
            McpOauthAuthorizationRequest.mcp_oauth_client_id
            == client.mcp_oauth_client_id,
        )
    )
    if (
        client_count is None
        or client_count >= settings.mcp_oauth_max_pending_requests_per_client
    ):
        raise _RedirectedError("temporarily_unavailable")
    # The client row lock serialises the per-client cap; this lock, held until
    # authorize commits or rolls back, serialises the total across clients.
    advisory_transaction_lock(session, _PENDING_REQUESTS_LOCK_KEY)
    total_count = session.scalar(
        select(func.count()).select_from(McpOauthAuthorizationRequest).where(live)
    )
    if total_count is None or total_count >= settings.mcp_oauth_max_pending_requests:
        raise _RedirectedError("temporarily_unavailable")


def _registered_redirect_target(
    settings: Settings, client: McpOauthClient, redirect_uri: str
) -> RedirectTarget | None:
    """Require a registered URI; for a loopback URI only the port may differ."""
    target = match_redirect_uri(settings, redirect_uri)
    if target is None:
        return None
    if redirect_uri in client.redirect_uris:
        return target
    if not target.is_loopback:
        return None
    for registered_uri in client.redirect_uris:
        registered = match_redirect_uri(settings, registered_uri)
        if (
            registered is not None
            and registered.is_loopback
            and (registered.host, registered.path) == (target.host, target.path)
        ):
            return target
    return None


def _validated_redirect_uris(settings: Settings, value: object) -> list[str]:
    if not isinstance(value, list):
        raise OAuthError("invalid_client_metadata", "redirect_uris is required")
    items = cast(list[object], value)
    if not 1 <= len(items) <= MAX_REDIRECT_URIS:
        raise OAuthError(
            "invalid_client_metadata",
            f"redirect_uris must contain 1 to {MAX_REDIRECT_URIS} URIs",
        )
    uris: list[str] = []
    for item in items:
        if not isinstance(item, str) or not 1 <= len(item) <= MAX_REDIRECT_URI_LENGTH:
            raise OAuthError(
                "invalid_client_metadata",
                f"Each redirect URI must be a string of at most "
                f"{MAX_REDIRECT_URI_LENGTH} characters",
            )
        if match_redirect_uri(settings, item) is None:
            raise OAuthError("invalid_redirect_uri", "Redirect URI is not allowed")
        if item not in uris:
            uris.append(item)
    return uris


def _loopback_port(uri: str, host: str, path: str) -> int | None:
    try:
        parsed = urlsplit(uri)
        port = parsed.port
    except ValueError:
        return None
    if (
        parsed.scheme != "http"
        or port is None
        or not 1 <= port <= 65535
        # Rebuilding the URI rejects userinfo, query, fragment, encoded or
        # trailing-dot hosts, other paths and non-canonical port spellings.
        or uri != f"http://{host}:{port}{path}"
    ):
        return None
    return port


def _url_form_host(uri: str) -> str:
    hostname = urlsplit(uri).hostname or ""
    return f"[{hostname}]" if ":" in hostname else hostname


def advisory_transaction_lock(session: Session, lock_key: int) -> None:
    if session.get_bind().dialect.name != "postgresql":
        return
    session.execute(
        text("SELECT pg_advisory_xact_lock(:lock_key)"),
        {"lock_key": lock_key},
    )


def _sha256(value: str) -> bytes:
    return hashlib.sha256(value.encode("utf-8")).digest()


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
