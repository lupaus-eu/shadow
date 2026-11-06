# pyright: reportPrivateUsage=false

import base64
import hashlib
import logging
from collections.abc import Generator, Iterator, Mapping
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import cast
from urllib.parse import parse_qsl, urlsplit

import httpx2
import pytest
from auth_helpers import TEST_ACTOR_USER_ID, TEST_CSRF_TOKEN, authenticate_test_client
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import StaticPool, create_engine, delete, func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

import app.api.v1.mcp_oauth.token_service as token_service
from app.api.v1.auth.logging import SensitiveQueryFilter
from app.api.v1.auth.rate_limit import FixedWindowRateLimiter
from app.api.v1.mcp_oauth.models import (
    McpOauthAuthorizationRequest,
    McpOauthClient,
    McpOauthGrant,
)
from app.api.v1.mcp_oauth.service import cleanup_stale_clients
from app.api.v1.users.models import User
from app.core.config import Settings
from app.core.database import get_db_session
from app.core.models import Base
from app.main import create_app

ORIGIN = "http://testserver"
RESOURCE = f"{ORIGIN}/api/mcp"
BOTH_SCOPES = "shadow.read shadow.write"
# The resources that TASK-074 replaced with `/api/mcp`.
LEGACY_RESOURCES = (f"{ORIGIN}/api/mcp/read", f"{ORIGIN}/api/mcp/write")
CLAUDE_CALLBACK = "https://claude.ai/api/mcp/auth_callback"
CLAUDE_COM_CALLBACK = "https://claude.com/api/mcp/auth_callback"
LOOPBACK_CALLBACK = "http://127.0.0.1:33418/callback"
VERIFIER = "v" * 64
CHALLENGE = (
    base64.urlsafe_b64encode(hashlib.sha256(VERIFIER.encode()).digest())
    .rstrip(b"=")
    .decode()
)
OAUTH_LOGGER = "app.api.v1.mcp_oauth.service"


@pytest.fixture()
def session_factory() -> Iterator[sessionmaker[Session]]:
    engine: Engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine, autocommit=False, autoflush=False)
    engine.dispose()


# Every loopback host the matcher supports, not only the trimmed default.
TEST_REDIRECT_URIS = (
    "https://claude.ai/api/mcp/auth_callback "
    "https://claude.com/api/mcp/auth_callback "
    "http://127.0.0.1:{port}/callback http://[::1]:{port}/callback "
    "http://localhost:{port}/callback"
)


def _settings(**overrides: object) -> Settings:
    return Settings.model_validate(
        {
            "MCP_ENABLED": True,
            "MCP_OAUTH_REDIRECT_URIS": TEST_REDIRECT_URIS,
            **overrides,
        }
    )


@contextmanager
def _client(
    session_factory: sessionmaker[Session],
    settings: Settings | None = None,
    *,
    role: str | None = None,
) -> Generator[TestClient, None, None]:
    app = create_app(settings=settings or _settings())

    def override_get_db_session() -> Iterator[Session]:
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db_session
    with TestClient(app, follow_redirects=False) as client:
        if role is not None:
            authenticate_test_client(client, session_factory, role=role)
        yield client


@pytest.fixture()
def client(session_factory: sessionmaker[Session]) -> Iterator[TestClient]:
    with _client(session_factory, role="consultant") as test_client:
        yield test_client


def _register(
    client: TestClient,
    redirect_uris: list[str] | None = None,
    client_name: object = "Claude",
    **extra: object,
) -> httpx2.Response:
    metadata: dict[str, object] = {
        "redirect_uris": redirect_uris or [LOOPBACK_CALLBACK],
        "client_name": client_name,
        **extra,
    }
    return client.post("/api/oauth/register", json=metadata)


def _registered_client_id(
    client: TestClient, redirect_uris: list[str] | None = None
) -> str:
    response = _register(client, redirect_uris)
    assert response.status_code == 201, response.text
    return str(response.json()["client_id"])


def _authorize_params(
    client_id: str,
    redirect_uri: str | None = LOOPBACK_CALLBACK,
    **overrides: str | None,
) -> dict[str, str]:
    params: dict[str, str | None] = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "code_challenge": CHALLENGE,
        "code_challenge_method": "S256",
        "resource": RESOURCE,
        "scope": BOTH_SCOPES,
        "state": "client-state",
        **overrides,
    }
    return {name: value for name, value in params.items() if value is not None}


def _authorize(client: TestClient, params: Mapping[str, str]) -> httpx2.Response:
    return client.get("/api/oauth/authorize", params=params)


def _request_id(response: httpx2.Response) -> str:
    assert response.status_code == 303, response.text
    location = urlsplit(response.headers["location"])
    assert f"{location.scheme}://{location.netloc}{location.path}" == (
        f"{ORIGIN}/ai/authorize"
    )
    query = parse_qsl(location.query)
    assert [name for name, _ in query] == ["request"]
    return query[0][1]


def _start_consent(
    client: TestClient,
    redirect_uri: str = LOOPBACK_CALLBACK,
    **overrides: str | None,
) -> str:
    client_id = _registered_client_id(client, [redirect_uri])
    return _request_id(
        _authorize(client, _authorize_params(client_id, redirect_uri, **overrides))
    )


def _query(url: str) -> tuple[str, list[tuple[str, str]]]:
    parsed = urlsplit(url)
    base = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
    return base, parse_qsl(parsed.query, keep_blank_values=True)


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def _mcp_oauth_values(session: Session) -> str:
    rows: list[object] = [
        *session.scalars(select(McpOauthClient)),
        *session.scalars(select(McpOauthAuthorizationRequest)),
        *session.scalars(select(McpOauthGrant)),
    ]
    return " ".join(
        repr(value)
        for row in rows
        for name, value in vars(row).items()
        if not name.startswith("_")
    )


def _stored_client(session: Session, client_id: str) -> McpOauthClient:
    stored = session.scalar(
        select(McpOauthClient).where(McpOauthClient.client_id == client_id)
    )
    assert stored is not None
    return stored


def _add_client(
    session: Session,
    client_id: str,
    *,
    age: timedelta = timedelta(),
    last_used_age: timedelta | None = None,
    deleted: bool = False,
) -> McpOauthClient:
    now = datetime.now(UTC)
    stored = McpOauthClient(
        client_id=client_id,
        client_name="Stored Client",
        redirect_uris=[LOOPBACK_CALLBACK],
        created_time=now - age,
        last_used_time=None if last_used_age is None else now - last_used_age,
        deleted_time=now if deleted else None,
    )
    session.add(stored)
    session.commit()
    return stored


def _add_user(session: Session) -> User:
    user = session.get(User, 41) or User(
        user_id=41, name="Grant User", email="grant@example.test", role="consultant"
    )
    session.add(user)
    session.commit()
    return user


def _add_grant(
    session: Session, stored: McpOauthClient, *, active: bool
) -> McpOauthGrant:
    now = datetime.now(UTC)
    grant = McpOauthGrant(
        grant_key=f"grant-{stored.client_id}",
        mcp_oauth_client_id=stored.mcp_oauth_client_id,
        user_id=_add_user(session).user_id,
        scopes=BOTH_SCOPES,
        resource=RESOURCE,
        created_time=now - timedelta(days=40),
        expires_time=now + timedelta(days=1) if active else now - timedelta(days=10),
    )
    session.add(grant)
    session.commit()
    return grant


def _add_authorization_request(
    session: Session, stored: McpOauthClient, *, expired: bool = True
) -> McpOauthAuthorizationRequest:
    now = datetime.now(UTC)
    created = now - timedelta(days=40) if expired else now
    request = McpOauthAuthorizationRequest(
        request_id_hash=hashlib.sha256(stored.client_id.encode()).digest(),
        mcp_oauth_client_id=stored.mcp_oauth_client_id,
        redirect_uri=LOOPBACK_CALLBACK,
        code_challenge=CHALLENGE,
        scopes=BOTH_SCOPES,
        resource=RESOURCE,
        created_time=created,
        expires_time=created + timedelta(minutes=10),
    )
    session.add(request)
    session.commit()
    return request


# Discovery


def test_authorization_server_metadata_advertises_the_contract(
    client: TestClient,
) -> None:
    response = client.get("/.well-known/oauth-authorization-server")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {
        "issuer": ORIGIN,
        "authorization_endpoint": f"{ORIGIN}/api/oauth/authorize",
        "token_endpoint": f"{ORIGIN}/api/oauth/token",
        "registration_endpoint": f"{ORIGIN}/api/oauth/register",
        "revocation_endpoint": f"{ORIGIN}/api/oauth/revoke",
        "scopes_supported": ["shadow.read", "shadow.write"],
        "response_types_supported": ["code"],
        "response_modes_supported": ["query"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "token_endpoint_auth_methods_supported": ["none"],
        "revocation_endpoint_auth_methods_supported": ["none"],
        "code_challenge_methods_supported": ["S256"],
        "authorization_response_iss_parameter_supported": True,
    }


def test_protected_resource_metadata_uses_the_one_canonical_resource(
    client: TestClient,
) -> None:
    response = client.get("/.well-known/oauth-protected-resource/api/mcp")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {
        "resource": RESOURCE,
        "authorization_servers": [ORIGIN],
        "scopes_supported": ["shadow.read", "shadow.write"],
        "bearer_methods_supported": ["header"],
    }
    assert not response.json()["resource"].endswith("/")


@pytest.mark.parametrize(
    "path",
    [
        "/.well-known/oauth-protected-resource/api/mcp/read",
        "/.well-known/oauth-protected-resource/api/mcp/write",
        "/.well-known/oauth-protected-resource/api/mcp/",
    ],
)
def test_legacy_protected_resource_metadata_is_gone(
    client: TestClient, path: str
) -> None:
    assert client.get(path).status_code == 404


# Registration


@pytest.mark.parametrize(
    "redirect_uri",
    [
        CLAUDE_CALLBACK,
        CLAUDE_COM_CALLBACK,
        "http://127.0.0.1:1/callback",
        LOOPBACK_CALLBACK,
        "http://[::1]:8080/callback",
        "http://localhost:65535/callback",
    ],
)
def test_registration_accepts_exact_and_loopback_allowlist_entries(
    client: TestClient,
    session_factory: sessionmaker[Session],
    redirect_uri: str,
) -> None:
    response = _register(
        client,
        [redirect_uri],
        token_endpoint_auth_method="none",
        grant_types=["authorization_code", "refresh_token"],
        logo_uri="https://ignored.example/logo.png",
    )

    assert response.status_code == 201, response.text
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert len(body["client_id"]) == 43
    assert body == {
        "client_id": body["client_id"],
        "client_id_issued_at": body["client_id_issued_at"],
        "client_name": "Claude",
        "redirect_uris": [redirect_uri],
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "none",
    }
    with session_factory() as session:
        stored = _stored_client(session, body["client_id"])
        assert stored.redirect_uris == [redirect_uri]
        assert stored.created_ip == "testclient"
        assert stored.deleted_time is None


@pytest.mark.parametrize(
    "redirect_uri",
    [
        "http://user@127.0.0.1:8080/callback",
        "http://127.0.0.1:8080@evil.example/callback",
        "http://127.0.0.1:8080/callback#fragment",
        "http://127.0.0.1:8080/callback#",
        "http://127.0.0.1:8080/callback?x=1",
        "http://127.0.0.1:8080/callback?",
        "http://127.0.0.1/callback",
        "http://127.0.0.1:/callback",
        "http://127.0.0.1:0/callback",
        "http://127.0.0.1:65536/callback",
        "http://127.0.0.1:08080/callback",
        "https://127.0.0.1:8080/callback",
        "HTTP://127.0.0.1:8080/callback",
        "http://127.0.0.%31:8080/callback",
        "http://%6cocalhost:8080/callback",
        "http://localhost.:8080/callback",
        "http://127.0.0.1.:8080/callback",
        "http://LOCALHOST:8080/callback",
        "http://127.0.0.2:8080/callback",
        "http://[::1]:8080/callback/",
        "http://localhost:8080/callbackx",
        "http://localhost:8080/other",
        "http://localhost:8080/Callback",
        f"{CLAUDE_CALLBACK}/",
        f"{CLAUDE_CALLBACK}?x=1",
        "https://claude.ai.evil.example/api/mcp/auth_callback",
        "https://evil.example/api/mcp/auth_callback",
        "http://claude.ai/api/mcp/auth_callback",
    ],
)
def test_registration_rejects_redirect_uris_outside_the_allowlist(
    client: TestClient,
    session_factory: sessionmaker[Session],
    redirect_uri: str,
) -> None:
    response = _register(client, [LOOPBACK_CALLBACK, redirect_uri])

    assert response.status_code == 400
    assert response.json()["error"] == "invalid_redirect_uri"
    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(McpOauthClient)) == 0


@pytest.mark.parametrize(
    "method", ["client_secret_basic", "client_secret_post", "private_key_jwt", None]
)
def test_registration_rejects_non_public_clients(
    client: TestClient, method: str | None
) -> None:
    response = _register(client, token_endpoint_auth_method=method)

    assert response.status_code == 400
    assert response.json()["error"] == "invalid_client_metadata"


@pytest.mark.parametrize(
    "client_name",
    [
        pytest.param(None, id="missing"),
        pytest.param(123, id="not-a-string"),
        pytest.param("", id="empty"),
        pytest.param("   ", id="only-spaces"),
        pytest.param("a" * 101, id="too-long"),
        pytest.param(" " + "a" * 101 + " ", id="too-long-after-trim"),
        pytest.param("\tClaude", id="leading-tab"),
        pytest.param("Claude\t", id="trailing-tab"),
        pytest.param("Clau\tde", id="inner-tab"),
        pytest.param("\nClaude", id="leading-newline"),
        pytest.param("Claude\n", id="trailing-newline"),
        pytest.param("Clau\nde", id="inner-newline"),
        pytest.param("\u2028Claude", id="leading-line-separator"),
        pytest.param("Claude\u2028", id="trailing-line-separator"),
        pytest.param("Clau\u2028de", id="inner-line-separator"),
        pytest.param("Cl\u202eaude", id="bidi-override"),
        pytest.param("Cl\u200baude", id="zero-width-space"),
        pytest.param("\u3164", id="hangul-filler"),
        pytest.param("Cl\u3164aude", id="inner-hangul-filler"),
        pytest.param("\u0421laude", id="cyrillic-lookalike"),
        pytest.param("Claude\u00a0Code", id="no-break-space"),
        pytest.param("Claude <script>", id="angle-bracket"),
        pytest.param('Claude "Code"', id="double-quote"),
        pytest.param("Jonatan's client", id="apostrophe"),
        pytest.param("...", id="only-punctuation"),
        pytest.param(" (-) ", id="spaces-and-punctuation"),
    ],
)
def test_registration_rejects_client_names_outside_the_ascii_allowlist(
    client: TestClient,
    session_factory: sessionmaker[Session],
    client_name: object,
) -> None:
    metadata: dict[str, object] = {"redirect_uris": [LOOPBACK_CALLBACK]}
    if client_name is not None:
        metadata["client_name"] = client_name

    response = client.post("/api/oauth/register", json=metadata)

    assert response.status_code == 400
    assert response.json()["error"] == "invalid_client_metadata"
    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(McpOauthClient)) == 0


@pytest.mark.parametrize(
    ("client_name", "stored_name"),
    [
        ("Claude", "Claude"),
        ("Claude Code (CLI)", "Claude Code (CLI)"),
        ("my-client_2", "my-client_2"),
        ("Tool v1.2: a/b+c", "Tool v1.2: a/b+c"),
        ("  Claude  ", "Claude"),
        ("a" * 100, "a" * 100),
        ("  " + "b" * 100 + "  ", "b" * 100),
    ],
)
def test_registration_stores_the_trimmed_allowlisted_client_name(
    client: TestClient,
    session_factory: sessionmaker[Session],
    client_name: str,
    stored_name: str,
) -> None:
    response = _register(client, client_name=client_name)

    assert response.status_code == 201
    assert response.json()["client_name"] == stored_name
    with session_factory() as session:
        stored = _stored_client(session, response.json()["client_id"])
        assert stored.client_name == stored_name


def test_registration_bounds_redirect_uris(
    session_factory: sessionmaker[Session],
) -> None:
    long_exact = "https://client.example/" + "a" * (2048 - 23)
    assert len(long_exact) == 2048
    settings = _settings(
        MCP_OAUTH_REDIRECT_URIS=f"http://127.0.0.1:{{port}}/callback {long_exact}"
    )
    ten_loopbacks = [f"http://127.0.0.1:{port}/callback" for port in range(1, 11)]
    with _client(session_factory, settings) as client:
        assert _register(client, ten_loopbacks).status_code == 201
        assert _register(client, [long_exact]).status_code == 201
        for redirect_uris in (
            [*ten_loopbacks, "http://127.0.0.1:11/callback"],
            [long_exact + "a"],
            [],
            "http://127.0.0.1:1/callback",
            [42],
            None,
        ):
            response = client.post(
                "/api/oauth/register",
                json={"client_name": "Claude", "redirect_uris": redirect_uris},
            )
            assert response.status_code == 400, redirect_uris
            assert response.json()["error"] == "invalid_client_metadata"


@pytest.mark.parametrize(
    "body",
    [b"not json", b"[]", b'"Claude"', b"{" + b" " * (64 * 1024) + b"}"],
)
def test_registration_rejects_malformed_or_oversized_metadata(
    client: TestClient, body: bytes
) -> None:
    response = client.post(
        "/api/oauth/register",
        content=body,
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 400
    assert response.json()["error"] == "invalid_client_metadata"


def test_registration_runs_cleanup_before_the_client_cap(
    session_factory: sessionmaker[Session],
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger=OAUTH_LOGGER)
    with session_factory() as session:
        _add_client(session, "stale", age=timedelta(days=31))
        _add_client(session, "fresh")
        _add_client(session, "already-deleted", deleted=True)

    settings = _settings(MCP_OAUTH_MAX_CLIENTS=2)
    with _client(session_factory, settings) as client:
        reclaimed = _register(client)
        assert reclaimed.status_code == 201
        with session_factory() as session:
            client_ids = set(session.scalars(select(McpOauthClient.client_id)))
        assert client_ids == {"fresh", reclaimed.json()["client_id"]}

        full = _register(client)

    assert full.status_code == 503
    assert full.json()["error"] == "temporarily_unavailable"
    warnings = [
        record for record in caplog.records if record.levelno == logging.WARNING
    ]
    assert len(warnings) == 1
    assert "cap of 2 non-deleted clients" in warnings[0].getMessage()


def test_cleanup_soft_deletes_stale_clients_then_hard_deletes_unreferenced(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        stale_with_request = _add_client(
            session, "stale-request", age=timedelta(days=60)
        )
        _add_authorization_request(session, stale_with_request)
        stale_with_old_grant = _add_client(
            session, "stale-old-grant", age=timedelta(days=60)
        )
        _add_grant(session, stale_with_old_grant, active=False)
        stale_with_active_grant = _add_client(
            session, "stale-active-grant", age=timedelta(days=60)
        )
        _add_grant(session, stale_with_active_grant, active=True)
        _add_client(session, "stale-unreferenced", age=timedelta(days=60))
        _add_client(
            session,
            "recently-used",
            age=timedelta(days=60),
            last_used_age=timedelta(days=29),
        )

        cleanup_stale_clients(session, now=datetime.now(UTC))

        remaining = {
            row.client_id: row.deleted_time is not None
            for row in session.scalars(select(McpOauthClient))
        }
    assert remaining == {
        "stale-request": True,
        "stale-old-grant": True,
        "stale-active-grant": False,
        "recently-used": False,
    }

    with _client(session_factory) as client:
        response = _authorize(client, _authorize_params("stale-request"))
    assert response.status_code == 400
    assert response.json()["error"] == "invalid_client"
    assert "location" not in response.headers

    with session_factory() as session:
        session.execute(delete(McpOauthAuthorizationRequest))
        session.execute(
            delete(McpOauthGrant).where(McpOauthGrant.expires_time < datetime.now(UTC))
        )
        session.commit()
        cleanup_stale_clients(session, now=datetime.now(UTC))
        remaining_ids = set(session.scalars(select(McpOauthClient.client_id)))
    assert remaining_ids == {"stale-active-grant", "recently-used"}


def test_valid_authorize_updates_last_used_time_so_cleanup_keeps_the_client(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        _add_client(session, "old-client", age=timedelta(days=45))

    before = datetime.now(UTC)
    response = _authorize(client, _authorize_params("old-client"))
    _request_id(response)

    with session_factory() as session:
        stored = _stored_client(session, "old-client")
        assert stored.last_used_time is not None
        assert _as_utc(stored.last_used_time) >= before
        cleanup_stale_clients(session, now=datetime.now(UTC) + timedelta(minutes=10))
        session.refresh(stored)
        assert stored.deleted_time is None


@pytest.mark.parametrize(
    "overrides",
    [
        {"redirect_uri": "http://127.0.0.1:33418/other"},
        {"scope": "shadow.write"},
        {"resource": RESOURCE + "/"},
        {"code_challenge": None},
    ],
)
def test_failing_authorize_does_not_update_last_used_time(
    client: TestClient,
    session_factory: sessionmaker[Session],
    overrides: dict[str, str | None],
) -> None:
    with session_factory() as session:
        _add_client(session, "old-client", age=timedelta(days=45))

    response = _authorize(client, _authorize_params("old-client", **overrides))

    assert response.status_code in {303, 400}
    with session_factory() as session:
        assert _stored_client(session, "old-client").last_used_time is None
        assert (
            session.scalar(
                select(func.count()).select_from(McpOauthAuthorizationRequest)
            )
            == 0
        )


# Authorize


def test_authorize_stores_only_a_hashed_pending_request(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    client_id = _registered_client_id(client)

    response = _authorize(client, _authorize_params(client_id, scope=None))
    request_id = _request_id(response)

    assert response.headers["cache-control"] == "no-store"
    assert len(request_id) == 43
    with session_factory() as session:
        pending = session.scalar(select(McpOauthAuthorizationRequest))
        assert pending is not None
        assert pending.request_id_hash == hashlib.sha256(request_id.encode()).digest()
        assert pending.redirect_uri == LOOPBACK_CALLBACK
        assert pending.state == "client-state"
        assert pending.code_challenge == CHALLENGE
        assert (pending.scopes, pending.resource) == (BOTH_SCOPES, RESOURCE)
        assert pending.expires_time - pending.created_time == timedelta(minutes=10)
        assert (pending.user_id, pending.code_hash) == (None, None)
        assert request_id not in _mcp_oauth_values(session)


@pytest.mark.parametrize(
    "client_id",
    [
        pytest.param(None, id="missing"),
        pytest.param("unknown", id="unknown"),
        pytest.param("x" * 129, id="too-long"),
        pytest.param("unknown\x00", id="nul"),
    ],
)
def test_authorize_shows_invalid_client_errors_without_redirect(
    client: TestClient, client_id: str | None
) -> None:
    params = _authorize_params(_registered_client_id(client))
    del params["client_id"]
    if client_id is not None:
        params["client_id"] = client_id

    response = _authorize(client, params)

    assert response.status_code == 400
    assert response.json()["error"] == "invalid_client"
    assert "location" not in response.headers


def test_authorize_shows_duplicate_client_id_error_without_redirect(
    client: TestClient,
) -> None:
    client_id = _registered_client_id(client)
    params = (*_authorize_params(client_id).items(), ("client_id", client_id))

    response = client.get("/api/oauth/authorize", params=params)

    assert response.status_code == 400
    assert response.json()["error"] == "invalid_client"


@pytest.mark.parametrize(
    "redirect_uri",
    [
        None,
        CLAUDE_CALLBACK,
        "http://localhost:33418/callback",
        "http://127.0.0.1:33418/other",
        "https://127.0.0.1:33418/callback",
        "http://127.0.0.1:33418/callback?x=1",
        "https://evil.example/callback",
    ],
)
def test_authorize_shows_invalid_redirect_uri_errors_without_redirect(
    client: TestClient,
    session_factory: sessionmaker[Session],
    redirect_uri: str | None,
) -> None:
    client_id = _registered_client_id(client)

    response = _authorize(
        client, _authorize_params(client_id, redirect_uri=redirect_uri)
    )

    assert response.status_code == 400
    assert response.json() == {
        "error": "invalid_request",
        "error_description": "Invalid redirect_uri",
    }
    assert "location" not in response.headers
    with session_factory() as session:
        assert session.scalar(select(McpOauthAuthorizationRequest)) is None


def test_authorize_requires_exact_registered_uri_for_exact_entries(
    client: TestClient,
) -> None:
    client_id = _registered_client_id(client, [CLAUDE_CALLBACK])

    accepted = _authorize(client, _authorize_params(client_id, CLAUDE_CALLBACK))
    rejected = _authorize(client, _authorize_params(client_id, CLAUDE_COM_CALLBACK))

    _request_id(accepted)
    assert rejected.status_code == 400


def test_authorize_accepts_a_loopback_port_change_only(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    client_id = _registered_client_id(client, [LOOPBACK_CALLBACK])
    changed_port = "http://127.0.0.1:50000/callback"

    request_id = _request_id(
        _authorize(client, _authorize_params(client_id, changed_port))
    )

    with session_factory() as session:
        pending = session.scalar(select(McpOauthAuthorizationRequest))
        assert pending is not None
        assert pending.redirect_uri == changed_port
    approved = client.post(
        "/api/v1/ai/oauth/consent/approve", json={"request": request_id}
    )
    base, _ = _query(approved.json()["redirectUrl"])
    assert base == changed_port


@pytest.mark.parametrize(
    ("overrides", "error"),
    [
        pytest.param({"code_challenge": None}, "invalid_request", id="pkce-missing"),
        pytest.param(
            {"code_challenge_method": "plain"}, "invalid_request", id="pkce-plain"
        ),
        pytest.param(
            {"code_challenge_method": None}, "invalid_request", id="pkce-no-method"
        ),
        pytest.param(
            {"code_challenge": "short"}, "invalid_request", id="pkce-malformed"
        ),
        pytest.param({"response_type": None}, "invalid_request", id="no-type"),
        pytest.param(
            {"response_type": "token"}, "unsupported_response_type", id="token-type"
        ),
        pytest.param({"scope": "openid"}, "invalid_scope", id="unknown-scope"),
        pytest.param(
            {"scope": "shadow.read openid"}, "invalid_scope", id="unknown-in-set"
        ),
        pytest.param({"scope": "shadow.write"}, "invalid_scope", id="write-only"),
        pytest.param(
            {"scope": "shadow.read shadow.read"}, "invalid_scope", id="duplicate"
        ),
        pytest.param(
            {"scope": "shadow.read  shadow.write"},
            "invalid_scope",
            id="double-space",
        ),
        pytest.param({"scope": "SHADOW.READ"}, "invalid_scope", id="scope-case"),
        pytest.param({"scope": ""}, "invalid_scope", id="empty-scope"),
        pytest.param({"resource": None}, "invalid_target", id="resource-missing"),
        pytest.param(
            {"resource": RESOURCE + "/"}, "invalid_target", id="trailing-slash"
        ),
        pytest.param({"resource": RESOURCE + "?x=1"}, "invalid_target", id="query"),
        pytest.param({"resource": RESOURCE + "#x"}, "invalid_target", id="fragment"),
        pytest.param(
            {"resource": "https://testserver/api/mcp"},
            "invalid_target",
            id="other-origin",
        ),
        pytest.param({"resource": f"{ORIGIN}/api/MCP"}, "invalid_target", id="case"),
        pytest.param(
            {"resource": LEGACY_RESOURCES[0]}, "invalid_target", id="legacy-read"
        ),
        pytest.param(
            {"resource": LEGACY_RESOURCES[1]}, "invalid_target", id="legacy-write"
        ),
    ],
)
@pytest.mark.parametrize("state", ["client-state", None])
def test_authorize_redirects_other_errors_with_error_state_and_iss_only(
    client: TestClient,
    session_factory: sessionmaker[Session],
    overrides: dict[str, str | None],
    error: str,
    state: str | None,
) -> None:
    client_id = _registered_client_id(client)

    response = _authorize(
        client, _authorize_params(client_id, state=state, **overrides)
    )

    assert response.status_code == 303
    base, query = _query(response.headers["location"])
    assert base == LOOPBACK_CALLBACK
    expected = [("error", error)]
    if state is not None:
        expected.append(("state", state))
    assert query == [*expected, ("iss", ORIGIN)]
    with session_factory() as session:
        assert session.scalar(select(McpOauthAuthorizationRequest)) is None


def test_authorize_rejects_two_resources_and_duplicate_parameters(
    client: TestClient,
) -> None:
    client_id = _registered_client_id(client)
    base_params = tuple(_authorize_params(client_id).items())

    two_resources = client.get(
        "/api/oauth/authorize", params=(*base_params, ("resource", RESOURCE))
    )
    two_scopes = client.get(
        "/api/oauth/authorize", params=(*base_params, ("scope", "shadow.read"))
    )
    duplicate_state = client.get(
        "/api/oauth/authorize", params=(*base_params, ("state", "other"))
    )
    duplicate_challenge = client.get(
        "/api/oauth/authorize", params=(*base_params, ("code_challenge", CHALLENGE))
    )

    assert _query(two_resources.headers["location"])[1] == [
        ("error", "invalid_target"),
        ("state", "client-state"),
        ("iss", ORIGIN),
    ]
    assert _query(two_scopes.headers["location"])[1] == [
        ("error", "invalid_scope"),
        ("state", "client-state"),
        ("iss", ORIGIN),
    ]
    assert _query(duplicate_state.headers["location"])[1] == [
        ("error", "invalid_request"),
        ("iss", ORIGIN),
    ]
    assert _query(duplicate_challenge.headers["location"])[1][0] == (
        "error",
        "invalid_request",
    )


def test_authorize_redirects_a_nul_state_as_invalid_request_without_echoing_it(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    client_id = _registered_client_id(client)

    response = _authorize(client, _authorize_params(client_id, state="client\x00state"))

    assert response.status_code == 303
    assert _query(response.headers["location"]) == (
        LOOPBACK_CALLBACK,
        [("error", "invalid_request"), ("iss", ORIGIN)],
    )
    with session_factory() as session:
        assert session.scalar(select(McpOauthAuthorizationRequest)) is None
        assert _stored_client(session, client_id).last_used_time is None


@pytest.mark.parametrize(
    ("scope", "stored"),
    [
        pytest.param(None, BOTH_SCOPES, id="omitted"),
        pytest.param("shadow.read", "shadow.read", id="read"),
        pytest.param(BOTH_SCOPES, BOTH_SCOPES, id="both"),
        pytest.param("shadow.write shadow.read", BOTH_SCOPES, id="reversed"),
    ],
)
def test_authorize_normalises_the_requested_scopes(
    client: TestClient,
    session_factory: sessionmaker[Session],
    scope: str | None,
    stored: str,
) -> None:
    client_id = _registered_client_id(client)

    _request_id(_authorize(client, _authorize_params(client_id, scope=scope)))

    with session_factory() as session:
        pending = session.scalar(select(McpOauthAuthorizationRequest))
        assert pending is not None
        assert (pending.scopes, pending.resource) == (stored, RESOURCE)


def test_authorize_caps_live_pending_requests_per_client_and_in_total(
    session_factory: sessionmaker[Session],
) -> None:
    settings = _settings(
        MCP_OAUTH_MAX_PENDING_REQUESTS_PER_CLIENT=2,
        MCP_OAUTH_MAX_PENDING_REQUESTS=3,
    )
    with _client(session_factory, settings, role="consultant") as client:
        first_client = _registered_client_id(client)
        second_client = _registered_client_id(client)
        params = _authorize_params(first_client)
        first_request = _request_id(_authorize(client, params))
        _request_id(_authorize(client, params))

        per_client = _authorize(client, params)
        assert _query(per_client.headers["location"])[1] == [
            ("error", "temporarily_unavailable"),
            ("state", "client-state"),
            ("iss", ORIGIN),
        ]

        second_params = _authorize_params(second_client)
        _request_id(_authorize(client, second_params))
        total = _authorize(client, second_params)
        assert _query(total.headers["location"])[1][0] == (
            "error",
            "temporarily_unavailable",
        )

        # Decided and expired requests are no longer live.
        assert (
            client.post(
                "/api/v1/ai/oauth/consent/deny", json={"request": first_request}
            ).status_code
            == 200
        )
        _request_id(_authorize(client, second_params))
        with session_factory() as session:
            for pending in session.scalars(select(McpOauthAuthorizationRequest)):
                pending.created_time = datetime.now(UTC) - timedelta(minutes=20)
                pending.expires_time = datetime.now(UTC) - timedelta(minutes=10)
            session.commit()
        _request_id(_authorize(client, params))


# Consent


@pytest.mark.parametrize(
    ("redirect_uri", "is_loopback", "host"),
    [
        (LOOPBACK_CALLBACK, True, "127.0.0.1"),
        ("http://[::1]:8080/callback", True, "[::1]"),
        ("http://localhost:8080/callback", True, "localhost"),
        (CLAUDE_CALLBACK, False, "claude.ai"),
        (CLAUDE_COM_CALLBACK, False, "claude.com"),
    ],
)
def test_consent_returns_client_redirect_classification_scope_and_expiry(
    client: TestClient,
    redirect_uri: str,
    is_loopback: bool,
    host: str,
) -> None:
    request_id = _start_consent(client, redirect_uri, scope=None)

    response = client.get("/api/v1/ai/oauth/consent", params={"request": request_id})

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    expires = datetime.fromisoformat(body.pop("expiresTime"))
    assert body == {
        "clientName": "Claude",
        "clientNameSelfDeclared": True,
        "redirectIsLoopback": is_loopback,
        "redirectHost": host,
        "scope": BOTH_SCOPES,
        "resource": RESOURCE,
    }
    assert timedelta(minutes=9) < expires - datetime.now(UTC) <= timedelta(minutes=10)


@pytest.mark.parametrize("state", ["client-state", None])
def test_approve_records_user_and_returns_server_built_code_redirect(
    client: TestClient,
    session_factory: sessionmaker[Session],
    state: str | None,
) -> None:
    request_id = _start_consent(client, CLAUDE_CALLBACK, state=state)

    before = datetime.now(UTC)
    response = client.post(
        "/api/v1/ai/oauth/consent/approve", json={"request": request_id}
    )
    after = datetime.now(UTC)

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    base, query = _query(response.json()["redirectUrl"])
    assert base == CLAUDE_CALLBACK
    assert [name for name, _ in query] == (
        ["code", "state", "iss"] if state is not None else ["code", "iss"]
    )
    values = dict(query)
    code = values["code"]
    assert len(code) == 43
    assert values.get("state") == state
    assert values["iss"] == ORIGIN
    with session_factory() as session:
        pending = session.scalar(select(McpOauthAuthorizationRequest))
        assert pending is not None
        assert pending.user_id == TEST_ACTOR_USER_ID
        assert pending.code_hash == hashlib.sha256(code.encode()).digest()
        assert pending.code_expires_time is not None
        code_expiry = _as_utc(pending.code_expires_time)
        assert before + timedelta(seconds=60) <= code_expiry
        assert code_expiry <= after + timedelta(seconds=60)
        assert pending.consumed_time is None
        stored_values = _mcp_oauth_values(session)
        assert code not in stored_values
        assert request_id not in stored_values


def _stub_role_scopes(
    monkeypatch: pytest.MonkeyPatch, role: str, scopes: frozenset[str]
) -> None:
    monkeypatch.setitem(token_service.ROLE_SCOPES, role, scopes)


def test_consent_shows_and_approval_grants_only_the_role_scopes(
    client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_role_scopes(monkeypatch, "consultant", frozenset({"shadow.read"}))
    request_id = _start_consent(client, CLAUDE_CALLBACK, scope=BOTH_SCOPES)

    consent = client.get("/api/v1/ai/oauth/consent", params={"request": request_id})
    approve = client.post(
        "/api/v1/ai/oauth/consent/approve", json={"request": request_id}
    )

    assert consent.json()["scope"] == "shadow.read"
    assert [name for name, _ in _query(approve.json()["redirectUrl"])[1]] == [
        "code",
        "state",
        "iss",
    ]
    with session_factory() as session:
        pending = session.scalar(select(McpOauthAuthorizationRequest))
        assert pending is not None
        assert pending.scopes == "shadow.read"


@pytest.mark.parametrize(
    ("role_scopes", "consent_scope"),
    [(frozenset({"shadow.write"}), "shadow.write"), (frozenset[str](), "")],
    ids=["write-only-role", "role-without-ai-access"],
)
def test_approval_without_the_read_scope_returns_access_denied(
    client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
    role_scopes: frozenset[str],
    consent_scope: str,
) -> None:
    # Neither role can hold `shadow.read`. A role without AI access gets an
    # empty consent scope, which the consent page shows as "No access" with
    # only Deny.
    _stub_role_scopes(monkeypatch, "consultant", role_scopes)
    request_id = _start_consent(client, CLAUDE_CALLBACK)

    consent = client.get("/api/v1/ai/oauth/consent", params={"request": request_id})
    response = client.post(
        "/api/v1/ai/oauth/consent/approve", json={"request": request_id}
    )

    assert consent.status_code == 200, consent.text
    assert consent.json()["scope"] == consent_scope
    assert response.status_code == 200
    assert _query(response.json()["redirectUrl"]) == (
        CLAUDE_CALLBACK,
        [("error", "access_denied"), ("state", "client-state"), ("iss", ORIGIN)],
    )
    with session_factory() as session:
        pending = session.scalar(select(McpOauthAuthorizationRequest))
        assert pending is not None
        assert pending.user_id == TEST_ACTOR_USER_ID
        assert (pending.code_hash, pending.scopes) == (None, BOTH_SCOPES)


def test_deny_records_user_and_returns_access_denied_redirect(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    request_id = _start_consent(client)

    response = client.post(
        "/api/v1/ai/oauth/consent/deny", json={"request": request_id}
    )

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    base, query = _query(response.json()["redirectUrl"])
    assert base == LOOPBACK_CALLBACK
    assert query == [
        ("error", "access_denied"),
        ("state", "client-state"),
        ("iss", ORIGIN),
    ]
    with session_factory() as session:
        pending = session.scalar(select(McpOauthAuthorizationRequest))
        assert pending is not None
        assert pending.user_id == TEST_ACTOR_USER_ID
        assert (pending.code_hash, pending.code_expires_time) == (None, None)


@pytest.mark.parametrize(
    ("first", "second"),
    [
        ("approve", "approve"),
        ("approve", "deny"),
        ("deny", "approve"),
        ("deny", "deny"),
    ],
)
def test_request_can_be_decided_only_once(
    client: TestClient,
    session_factory: sessionmaker[Session],
    first: str,
    second: str,
) -> None:
    request_id = _start_consent(client)
    path = "/api/v1/ai/oauth/consent"
    assert (
        client.post(f"{path}/{first}", json={"request": request_id}).status_code == 200
    )
    with session_factory() as session:
        decided = session.scalar(select(McpOauthAuthorizationRequest))
        assert decided is not None
        code_hash = decided.code_hash

    repeated = client.post(f"{path}/{second}", json={"request": request_id})
    lookup = client.get(path, params={"request": request_id})

    for response in (repeated, lookup):
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "AUTHORIZATION_REQUEST_DECIDED"
    with session_factory() as session:
        unchanged = session.scalar(select(McpOauthAuthorizationRequest))
        assert unchanged is not None
        assert unchanged.code_hash == code_hash


def test_expired_request_cannot_be_viewed_or_decided(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    request_id = _start_consent(client)
    with session_factory() as session:
        pending = session.scalar(select(McpOauthAuthorizationRequest))
        assert pending is not None
        pending.created_time = datetime.now(UTC) - timedelta(minutes=11)
        pending.expires_time = datetime.now(UTC) - timedelta(seconds=1)
        session.commit()

    path = "/api/v1/ai/oauth/consent"
    responses = [
        client.get(path, params={"request": request_id}),
        client.post(f"{path}/approve", json={"request": request_id}),
        client.post(f"{path}/deny", json={"request": request_id}),
    ]

    for response in responses:
        assert response.status_code == 410
        assert response.json()["error"]["code"] == "AUTHORIZATION_REQUEST_EXPIRED"
    with session_factory() as session:
        expired = session.scalar(select(McpOauthAuthorizationRequest))
        assert expired is not None
        assert (expired.user_id, expired.code_hash) == (None, None)


@pytest.mark.parametrize("request_id", [None, "", "short", "!" * 43, "A" * 43])
def test_unknown_or_malformed_request_ids_are_not_found(
    client: TestClient, request_id: str | None
) -> None:
    _start_consent(client)
    params = {} if request_id is None else {"request": request_id}

    lookup = client.get("/api/v1/ai/oauth/consent", params=params)

    assert lookup.status_code == 404
    assert lookup.json()["error"]["code"] == "AUTHORIZATION_REQUEST_NOT_FOUND"
    if request_id:
        for decision in ("approve", "deny"):
            response = client.post(
                f"/api/v1/ai/oauth/consent/{decision}", json={"request": request_id}
            )
            assert response.status_code == 404


@pytest.mark.parametrize(
    "headers",
    [
        pytest.param({}, id="missing"),
        pytest.param({"Origin": "null", "X-CSRF-Token": TEST_CSRF_TOKEN}, id="null"),
        pytest.param(
            {"Origin": "https://attacker.example", "X-CSRF-Token": TEST_CSRF_TOKEN},
            id="cross-origin",
        ),
        pytest.param({"Origin": ORIGIN}, id="no-csrf"),
        pytest.param({"Origin": ORIGIN, "X-CSRF-Token": "wrong"}, id="wrong-csrf"),
    ],
)
@pytest.mark.parametrize("decision", ["approve", "deny"])
def test_consent_decisions_require_csrf_and_exact_origin(
    client: TestClient,
    session_factory: sessionmaker[Session],
    headers: dict[str, str],
    decision: str,
) -> None:
    request_id = _start_consent(client)
    del client.headers["Origin"]
    del client.headers["X-CSRF-Token"]

    response = client.post(
        f"/api/v1/ai/oauth/consent/{decision}",
        json={"request": request_id},
        headers=headers,
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"
    with session_factory() as session:
        pending = session.scalar(select(McpOauthAuthorizationRequest))
        assert pending is not None
        assert pending.user_id is None


def test_consent_requires_an_authenticated_session(
    session_factory: sessionmaker[Session],
) -> None:
    with _client(session_factory) as client:
        request_id = _start_consent(client)
        lookup = client.get("/api/v1/ai/oauth/consent", params={"request": request_id})
        approve = client.post(
            "/api/v1/ai/oauth/consent/approve", json={"request": request_id}
        )

    for response in (lookup, approve):
        assert response.status_code == 401
        assert response.headers["cache-control"] == "no-store"


# Rate limiting, feature flag and logging


def test_oauth_rate_limiter_buckets_never_consume_the_login_limiter(
    session_factory: sessionmaker[Session],
) -> None:
    settings = _settings(
        MCP_OAUTH_REGISTER_RATE_LIMIT_PER_MINUTE=2,
        MCP_OAUTH_AUTHORIZE_RATE_LIMIT_PER_MINUTE=1,
    )
    with _client(session_factory, settings) as client:
        client_id = _registered_client_id(client)
        assert _register(client).status_code == 201
        limited_register = _register(client)
        _request_id(_authorize(client, _authorize_params(client_id)))
        limited_authorize = _authorize(client, _authorize_params(client_id))
        state = cast(FastAPI, client.app).state
        auth_limiter = state.auth_rate_limiter
        oauth_limiter = state.oauth_rate_limiter

    for response in (limited_register, limited_authorize):
        assert response.status_code == 429
        assert response.json()["error"] == "temporarily_unavailable"
        assert "location" not in response.headers
    assert isinstance(auth_limiter, FixedWindowRateLimiter)
    assert isinstance(oauth_limiter, FixedWindowRateLimiter)
    assert oauth_limiter is not auth_limiter
    assert auth_limiter._entries == {}
    assert {bucket for bucket, _, _ in oauth_limiter._entries} == {
        "register",
        "authorize",
    }


def test_mcp_disabled_registers_no_endpoint_and_reports_feature_off(
    session_factory: sessionmaker[Session],
) -> None:
    with _client(session_factory, Settings(), role="consultant") as client:
        session_body = client.get("/api/v1/auth/session").json()
        responses = [
            client.get("/.well-known/oauth-authorization-server"),
            client.get("/.well-known/oauth-protected-resource/api/mcp"),
            client.get("/.well-known/oauth-protected-resource/api/mcp/read"),
            client.post("/api/oauth/register", json={"client_name": "Claude"}),
            client.get("/api/oauth/authorize", params={"client_id": "x"}),
            client.get("/api/v1/ai/oauth/consent", params={"request": "A" * 43}),
            client.post("/api/v1/ai/oauth/consent/approve", json={"request": "x"}),
            client.post("/api/v1/ai/oauth/consent/deny", json={"request": "x"}),
        ]

    assert session_body["features"] == {"mcp": False, "mcpChangeSetReview": False}
    assert [response.status_code for response in responses] == [404] * len(responses)


def test_session_reports_mcp_feature_when_enabled(client: TestClient) -> None:
    assert client.get("/api/v1/auth/session").json()["features"] == {
        "mcp": True,
        "mcpChangeSetReview": False,
    }


@pytest.mark.parametrize(
    ("mcp_enabled", "review_enabled", "expected"),
    [(True, True, True), (False, True, False), (True, False, False)],
)
def test_session_reports_mcp_change_set_review_only_with_mcp(
    session_factory: sessionmaker[Session],
    mcp_enabled: bool,
    review_enabled: bool,
    expected: bool,
) -> None:
    settings = _settings(
        MCP_ENABLED=mcp_enabled, MCP_CHANGE_SET_REVIEW_ENABLED=review_enabled
    )
    with _client(session_factory, settings, role="consultant") as client:
        features = client.get("/api/v1/auth/session").json()["features"]
    assert features == {"mcp": mcp_enabled, "mcpChangeSetReview": expected}


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/ai/oauth/consent?request=SECRETREQUEST&x=1",
        "/ai/authorize?request=SECRETREQUEST",
        "/api/v1/auth/login?return_to=%2Fai%2Fauthorize%3Frequest%3DSECRETREQUEST",
        "/api/oauth/authorize?state=SECRETREQUEST&client_id=c",
    ],
)
def test_access_log_filter_redacts_request_and_return_to(path: str) -> None:
    record = logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        "",
        0,
        '%s - "%s %s HTTP/%s" %d',
        ("192.0.2.1", "GET", path, "1.1", 200),
        None,
    )

    assert SensitiveQueryFilter().filter(record)
    rendered = record.getMessage()
    assert "SECRETREQUEST" not in rendered
    assert "=REDACTED" in rendered


def test_application_logs_never_contain_request_ids_or_codes(
    client: TestClient,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    request_id = _start_consent(client)
    approved = client.post(
        "/api/v1/ai/oauth/consent/approve", json={"request": request_id}
    )
    code = dict(_query(approved.json()["redirectUrl"])[1])["code"]

    rendered = "\n".join(record.getMessage() for record in caplog.records)
    assert request_id not in rendered
    assert code not in rendered
    registered = [
        record.getMessage() for record in caplog.records if record.name == OAUTH_LOGGER
    ]
    assert len(registered) == 1
    assert "self_declared_client_name='Claude'" in registered[0]
