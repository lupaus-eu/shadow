# pyright: reportPrivateUsage=false

import base64
import hashlib
import io
import logging
from collections.abc import Generator, Iterator, Mapping
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from urllib.parse import parse_qsl, urlsplit

import httpx2
import pytest
from auth_helpers import (
    TEST_ACTOR_USER_ID,
    TEST_CSRF_TOKEN,
    TEST_RAW_SESSION_ID,
    authenticate_test_client,
)
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import StaticPool, create_engine, event, func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

import app.api.v1.mcp_oauth.token_service as token_service
from app.api.v1.auth.logging import SensitiveQueryFilter
from app.api.v1.auth.rate_limit import FixedWindowRateLimiter
from app.api.v1.mcp_oauth.audit_log import AUDIT_HANDLER
from app.api.v1.mcp_oauth.models import (
    McpOauthAuthorizationRequest,
    McpOauthClient,
    McpOauthGrant,
    McpOauthToken,
)
from app.api.v1.mcp_oauth.service import cleanup_stale_clients
from app.api.v1.mcp_oauth.token_service import (
    McpPrincipal,
    TokenVerificationError,
    cleanup_expired_oauth_rows,
    verify_access_token,
)
from app.api.v1.users.models import User
from app.core.config import Settings
from app.core.database import get_db_session
from app.core.models import Base
from app.main import create_app

ORIGIN = "http://testserver"
RESOURCE = f"{ORIGIN}/api/mcp"
BOTH_SCOPES = "schatten.read schatten.write"
# The resources that TASK-074 replaced with `/api/mcp`.
LEGACY_RESOURCES = (f"{ORIGIN}/api/mcp/read", f"{ORIGIN}/api/mcp/write")
LOOPBACK_CALLBACK = "http://127.0.0.1:33418/callback"
VERIFIER = "v" * 64
CHALLENGE = (
    base64.urlsafe_b64encode(hashlib.sha256(VERIFIER.encode()).digest())
    .rstrip(b"=")
    .decode()
)
TOKEN_LOGGER = "app.api.v1.mcp_oauth.token_service"
OTHER_USER_ID = 42


def _enable_sqlite_foreign_keys(dbapi_connection: Any, _connection_record: Any) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


@pytest.fixture()
def session_factory() -> Iterator[sessionmaker[Session]]:
    engine: Engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    # The database's ON DELETE rules, not application code, cascade a deleted
    # grant's tokens and set references to it to null.
    event.listen(engine, "connect", _enable_sqlite_foreign_keys)
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine, autocommit=False, autoflush=False)
    engine.dispose()


def _settings(**overrides: object) -> Settings:
    return Settings.model_validate(
        {
            "MCP_ENABLED": True,
            "MCP_OAUTH_REDIRECT_URIS": "http://127.0.0.1:{port}/callback",
            **overrides,
        }
    )


@contextmanager
def _client(
    session_factory: sessionmaker[Session],
    settings: Settings | None = None,
    *,
    role: str | None = "consultant",
    existing_session: bool = False,
) -> Generator[TestClient, None, None]:
    app = create_app(settings=settings or _settings())

    def override_get_db_session() -> Iterator[Session]:
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db_session
    with TestClient(app, follow_redirects=False) as client:
        if existing_session:
            # Reuse the test User's browser session from an earlier client.
            client.cookies.set("schatten-session", TEST_RAW_SESSION_ID)
            client.headers.update({"Origin": ORIGIN, "X-CSRF-Token": TEST_CSRF_TOKEN})
        elif role is not None:
            authenticate_test_client(client, session_factory, role=role)
        yield client


@pytest.fixture()
def client(session_factory: sessionmaker[Session]) -> Iterator[TestClient]:
    with _client(session_factory) as test_client:
        yield test_client


def _register(client: TestClient, name: str = "Claude") -> str:
    response = client.post(
        "/api/oauth/register",
        json={"client_name": name, "redirect_uris": [LOOPBACK_CALLBACK]},
    )
    assert response.status_code == 201, response.text
    return str(response.json()["client_id"])


def _approved_code(client: TestClient, client_id: str, scope: str | None = None) -> str:
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": LOOPBACK_CALLBACK,
        "code_challenge": CHALLENGE,
        "code_challenge_method": "S256",
        "resource": RESOURCE,
        "state": "client-state",
    }
    if scope is not None:
        params["scope"] = scope
    authorize = client.get("/api/oauth/authorize", params=params)
    assert authorize.status_code == 303, authorize.text
    request_id = dict(parse_qsl(urlsplit(authorize.headers["location"]).query))[
        "request"
    ]
    approved = client.post(
        "/api/v1/ai/oauth/consent/approve", json={"request": request_id}
    )
    assert approved.status_code == 200, approved.text
    redirect_url = str(approved.json()["redirectUrl"])
    return dict(parse_qsl(urlsplit(redirect_url).query))["code"]


def _post_form(
    client: TestClient, path: str, form: Mapping[str, str | list[str] | None]
) -> httpx2.Response:
    data = {name: value for name, value in form.items() if value is not None}
    return client.post(path, data=data)


def _exchange(
    client: TestClient,
    client_id: str,
    code: str,
    /,
    **overrides: str | list[str] | None,
) -> httpx2.Response:
    form: dict[str, str | list[str] | None] = {
        "grant_type": "authorization_code",
        "code": code,
        "client_id": client_id,
        "redirect_uri": LOOPBACK_CALLBACK,
        "code_verifier": VERIFIER,
        "resource": RESOURCE,
        **overrides,
    }
    return _post_form(client, "/api/oauth/token", form)


def _refresh(
    client: TestClient,
    client_id: str,
    refresh_token: str,
    /,
    **overrides: str | list[str] | None,
) -> httpx2.Response:
    form: dict[str, str | list[str] | None] = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": client_id,
        "resource": RESOURCE,
        **overrides,
    }
    return _post_form(client, "/api/oauth/token", form)


def _revoke(
    client: TestClient, client_id: str | None, token: str | None
) -> httpx2.Response:
    return _post_form(
        client, "/api/oauth/revoke", {"client_id": client_id, "token": token}
    )


def _issued(
    client: TestClient, client_id: str, scope: str | None = None
) -> dict[str, Any]:
    code = _approved_code(client, client_id, scope)
    response = _exchange(client, client_id, code)
    assert response.status_code == 200, response.text
    return cast(dict[str, Any], response.json())


def _rotated(client: TestClient, client_id: str, refresh_token: str) -> dict[str, Any]:
    response = _refresh(client, client_id, refresh_token)
    assert response.status_code == 200, response.text
    return cast(dict[str, Any], response.json())


def _assert_oauth_error(response: httpx2.Response, error: str) -> None:
    assert response.status_code == 400, response.text
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["error"] == error


def _sha256(value: str) -> bytes:
    return hashlib.sha256(value.encode()).digest()


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def _only_grant(session: Session) -> McpOauthGrant:
    grants = session.scalars(select(McpOauthGrant)).all()
    assert len(grants) == 1
    return grants[0]


def _token_row(session: Session, raw_token: str) -> McpOauthToken:
    row = session.get(McpOauthToken, _sha256(raw_token))
    assert row is not None
    return row


def _verify(
    session_factory: sessionmaker[Session],
    access_token: str | None,
    resource: str = RESOURCE,
    scope: str = "schatten.read",
) -> McpPrincipal:
    with session_factory() as session:
        return verify_access_token(session, access_token, resource, scope)


def _verify_error(
    session_factory: sessionmaker[Session],
    access_token: str | None,
    resource: str = RESOURCE,
    scope: str = "schatten.read",
) -> str:
    with pytest.raises(TokenVerificationError) as raised:
        _verify(session_factory, access_token, resource, scope)
    return raised.value.error


def _add_user(session: Session, user_id: int = OTHER_USER_ID) -> User:
    user = session.get(User, user_id) or User(
        user_id=user_id,
        name=f"User {user_id}",
        email=f"user-{user_id}@example.test",
        role="consultant",
    )
    session.add(user)
    session.commit()
    return user


def _add_grant(
    session: Session,
    client_id: str,
    *,
    user_id: int = OTHER_USER_ID,
    scopes: str = BOTH_SCOPES,
    revoked: bool = False,
    expired: bool = False,
    key: str | None = None,
) -> McpOauthGrant:
    if user_id != TEST_ACTOR_USER_ID:
        _add_user(session, user_id)
    stored = session.scalar(
        select(McpOauthClient).where(McpOauthClient.client_id == client_id)
    )
    assert stored is not None
    now = datetime.now(UTC)
    created = now - timedelta(days=40) if expired else now - timedelta(days=1)
    grant = McpOauthGrant(
        grant_key=key or f"grant-{user_id}-{revoked}-{expired}",
        mcp_oauth_client_id=stored.mcp_oauth_client_id,
        user_id=user_id,
        scopes=scopes,
        resource=RESOURCE,
        created_time=created,
        expires_time=created + timedelta(days=30),
        revoked_time=now if revoked else None,
    )
    session.add(grant)
    session.commit()
    return grant


def _add_token(
    session: Session, grant: McpOauthGrant, raw_token: str, kind: str = "refresh"
) -> None:
    now = datetime.now(UTC)
    session.add(
        McpOauthToken(
            token_hash=_sha256(raw_token),
            grant_id=grant.grant_id,
            kind=kind,
            created_time=now,
            expires_time=now + timedelta(hours=1),
        )
    )
    session.commit()


def _skip_cleanup(session: Session, *, now: datetime) -> None:
    return None


def _revocation_logs(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [
        record.getMessage()
        for record in caplog.records
        if record.name == TOKEN_LOGGER and "revoked" in record.getMessage()
    ]


def _assert_no_secret_logged(
    caplog: pytest.LogCaptureFixture, secrets: list[str]
) -> None:
    rendered = "\n".join(record.getMessage() for record in caplog.records)
    for secret in secrets:
        assert secret not in rendered


# Authorization code exchange


def test_code_exchange_issues_hashed_opaque_tokens_bound_to_a_new_grant(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    client_id = _register(client)
    code = _approved_code(client, client_id)

    before = datetime.now(UTC)
    response = _exchange(client, client_id, code)
    after = datetime.now(UTC)

    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert set(body) == {
        "access_token",
        "token_type",
        "expires_in",
        "refresh_token",
        "scope",
    }
    assert body["token_type"] == "Bearer"
    assert body["scope"] == BOTH_SCOPES
    assert 3590 <= body["expires_in"] <= 3600
    access_token, refresh_token = body["access_token"], body["refresh_token"]
    # 32 random bytes (256 bits), base64url-encoded without padding.
    assert len(access_token) == len(refresh_token) == 43
    assert access_token != refresh_token
    with session_factory() as session:
        grant = _only_grant(session)
        assert (grant.user_id, grant.scopes, grant.resource) == (
            TEST_ACTOR_USER_ID,
            BOTH_SCOPES,
            RESOURCE,
        )
        assert grant.grant_key.startswith("grant_")
        expires = _as_utc(grant.expires_time)
        assert before + timedelta(days=30) <= expires <= after + timedelta(days=30)
        assert (grant.revoked_time, grant.revoked_by) == (None, None)
        access = _token_row(session, access_token)
        refresh = _token_row(session, refresh_token)
        assert (access.kind, refresh.kind) == ("access", "refresh")
        assert {access.grant_id, refresh.grant_id} == {grant.grant_id}
        access_expires = _as_utc(access.expires_time)
        refresh_expires = _as_utc(refresh.expires_time)
        assert before + timedelta(hours=1) <= access_expires
        assert access_expires <= after + timedelta(hours=1)
        assert before + timedelta(days=7) <= refresh_expires
        assert refresh_expires <= after + timedelta(days=7)
        for row in (access, refresh):
            assert (row.replaced_by_hash, row.revoked_time) == (None, None)
        pending = session.scalar(select(McpOauthAuthorizationRequest))
        assert pending is not None
        assert pending.consumed_time is not None
        assert pending.grant_id == grant.grant_id
        stored_values = " ".join(
            repr(value)
            for row in [
                *session.scalars(select(McpOauthToken)),
                *session.scalars(select(McpOauthGrant)),
                *session.scalars(select(McpOauthAuthorizationRequest)),
            ]
            for name, value in vars(row).items()
            if not name.startswith("_")
        )
        for secret in (access_token, refresh_token, code):
            assert secret not in stored_values
    principal = _verify(session_factory, access_token)
    assert principal.user_id == TEST_ACTOR_USER_ID


@pytest.mark.parametrize(
    ("overrides", "error"),
    [
        pytest.param({"code_verifier": "w" * 64}, "invalid_grant", id="wrong-verifier"),
        pytest.param({"code_verifier": "v" * 42}, "invalid_grant", id="short-verifier"),
        pytest.param({"code_verifier": None}, "invalid_request", id="no-verifier"),
        pytest.param(
            {"redirect_uri": "http://127.0.0.1:1/callback"},
            "invalid_grant",
            id="other-redirect-port",
        ),
        pytest.param({"redirect_uri": None}, "invalid_request", id="no-redirect"),
        pytest.param({"resource": None}, "invalid_target", id="no-resource"),
        pytest.param(
            {"resource": LEGACY_RESOURCES[0]}, "invalid_target", id="legacy-read"
        ),
        pytest.param(
            {"resource": LEGACY_RESOURCES[1]}, "invalid_target", id="legacy-write"
        ),
        pytest.param(
            {"resource": f"{RESOURCE}/"}, "invalid_target", id="trailing-slash"
        ),
        pytest.param(
            {"resource": [RESOURCE, RESOURCE]},
            "invalid_target",
            id="two-resources",
        ),
        pytest.param({"client_id": None}, "invalid_client", id="no-client"),
        pytest.param({"client_id": "unknown"}, "invalid_client", id="unknown-client"),
        pytest.param({"client_id": "nul\x00"}, "invalid_request", id="nul-client"),
        pytest.param({"code": "A" * 43}, "invalid_grant", id="unknown-code"),
        pytest.param({"code": "short"}, "invalid_grant", id="malformed-code"),
        pytest.param({"code": None}, "invalid_request", id="no-code"),
        pytest.param(
            {"grant_type": ["authorization_code", "authorization_code"]},
            "invalid_request",
            id="repeated-grant-type",
        ),
        pytest.param({"grant_type": None}, "invalid_request", id="no-grant-type"),
        pytest.param(
            {"grant_type": "password"}, "unsupported_grant_type", id="password"
        ),
    ],
)
def test_failed_code_exchange_issues_nothing_and_leaves_the_code_redeemable(
    client: TestClient,
    session_factory: sessionmaker[Session],
    overrides: dict[str, str | list[str] | None],
    error: str,
) -> None:
    client_id = _register(client)
    code = _approved_code(client, client_id)

    response = _exchange(client, client_id, code, **overrides)

    _assert_oauth_error(response, error)
    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(McpOauthGrant)) == 0
        assert session.scalar(select(func.count()).select_from(McpOauthToken)) == 0
        pending = session.scalar(select(McpOauthAuthorizationRequest))
        assert pending is not None
        assert pending.consumed_time is None
    assert _exchange(client, client_id, code).status_code == 200


def test_code_exchange_rejects_another_clients_code(client: TestClient) -> None:
    client_id = _register(client)
    other_client_id = _register(client, "Other")
    code = _approved_code(client, client_id)

    _assert_oauth_error(_exchange(client, other_client_id, code), "invalid_grant")
    assert _exchange(client, client_id, code).status_code == 200


def test_expired_code_is_rejected(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    client_id = _register(client)
    code = _approved_code(client, client_id)
    with session_factory() as session:
        pending = session.scalar(select(McpOauthAuthorizationRequest))
        assert pending is not None
        pending.code_expires_time = datetime.now(UTC) - timedelta(seconds=1)
        session.commit()

    response = _exchange(client, client_id, code)

    _assert_oauth_error(response, "invalid_grant")
    assert response.json()["error_description"] == "Authorization code expired"
    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(McpOauthGrant)) == 0


def test_reused_code_fails_and_revokes_the_grant_and_its_tokens(
    client: TestClient,
    session_factory: sessionmaker[Session],
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger=TOKEN_LOGGER)
    client_id = _register(client)
    code = _approved_code(client, client_id)
    first = _exchange(client, client_id, code).json()
    rotated = _rotated(client, client_id, first["refresh_token"])

    reused = _exchange(client, client_id, code)

    _assert_oauth_error(reused, "invalid_grant")
    with session_factory() as session:
        grant = _only_grant(session)
        assert grant.revoked_time is not None
        assert grant.revoked_by is None
        tokens = session.scalars(select(McpOauthToken)).all()
        assert len(tokens) == 4
        assert all(token.revoked_time is not None for token in tokens)
        grant_key = grant.grant_key
    for access_token in (first["access_token"], rotated["access_token"]):
        assert _verify_error(session_factory, access_token) == "invalid_token"
    _assert_oauth_error(
        _refresh(client, client_id, rotated["refresh_token"]), "invalid_grant"
    )
    assert _revocation_logs(caplog) == [
        f"MCP OAuth grant revoked: reason=code_reuse actor=system "
        f"user_id={TEST_ACTOR_USER_ID} grant_key={grant_key} client_id={client_id} "
        f"self_declared_client_name='Claude' revoked_tokens=4"
    ]
    _assert_no_secret_logged(
        caplog,
        [
            code,
            first["access_token"],
            first["refresh_token"],
            rotated["access_token"],
            rotated["refresh_token"],
        ],
    )


def test_soft_deleted_client_or_user_cannot_redeem_a_code(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    client_id = _register(client)
    code = _approved_code(client, client_id)
    other_client_id = _register(client, "Other")
    other_code = _approved_code(client, other_client_id)
    with session_factory() as session:
        stored = session.scalar(
            select(McpOauthClient).where(McpOauthClient.client_id == client_id)
        )
        assert stored is not None
        stored.deleted_time = datetime.now(UTC)
        session.commit()

    _assert_oauth_error(_exchange(client, client_id, code), "invalid_client")

    with session_factory() as session:
        user = session.get(User, TEST_ACTOR_USER_ID)
        assert user is not None
        user.deleted_time = datetime.now(UTC)
        session.commit()
    _assert_oauth_error(_exchange(client, other_client_id, other_code), "invalid_grant")


@pytest.mark.parametrize(
    ("content", "headers"),
    [
        pytest.param(b'{"grant_type": "refresh_token"}', {}, id="json"),
        pytest.param(
            b"grant_type=refresh_token&" + b"x" * 17_000,
            {"Content-Type": "application/x-www-form-urlencoded"},
            id="too-large",
        ),
        pytest.param(
            b"grant_type=%ff",
            {"Content-Type": "application/x-www-form-urlencoded"},
            id="not-utf8",
        ),
        pytest.param(
            b"&".join(b"f%d=1" % index for index in range(30)),
            {"Content-Type": "application/x-www-form-urlencoded"},
            id="too-many-fields",
        ),
    ],
)
def test_token_endpoint_requires_a_bounded_form_body(
    client: TestClient, content: bytes, headers: dict[str, str]
) -> None:
    response = client.post(
        "/api/oauth/token",
        content=content,
        headers={"Content-Type": "application/json", **headers},
    )

    _assert_oauth_error(response, "invalid_request")


# Grant reuse


def test_reauthorization_reuses_the_active_grant_and_revokes_its_tokens(
    client: TestClient,
    session_factory: sessionmaker[Session],
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger=TOKEN_LOGGER)
    client_id = _register(client)
    first = _issued(client, client_id)
    rotated = _rotated(client, client_id, first["refresh_token"])
    with session_factory() as session:
        grant = _only_grant(session)
        original_expiry = datetime.now(UTC) + timedelta(days=12)
        grant.expires_time = original_expiry
        session.commit()
        grant_key = grant.grant_key

    second = _issued(client, client_id)

    with session_factory() as session:
        grant = _only_grant(session)
        assert grant.grant_key == grant_key
        assert grant.revoked_time is None
        assert _as_utc(grant.expires_time) == original_expiry
        for raw in (
            first["access_token"],
            first["refresh_token"],
            rotated["access_token"],
            rotated["refresh_token"],
        ):
            assert _token_row(session, raw).revoked_time is not None
        for raw in (second["access_token"], second["refresh_token"]):
            assert _token_row(session, raw).revoked_time is None
        requests = session.scalars(select(McpOauthAuthorizationRequest)).all()
        assert {request.grant_id for request in requests} == {grant.grant_id}
    assert _verify_error(session_factory, first["access_token"]) == "invalid_token"
    assert _verify(session_factory, second["access_token"]).grant_key == grant_key
    assert _revocation_logs(caplog) == [
        f"MCP OAuth grant tokens revoked: reason=reauthorization "
        f"actor=user:{TEST_ACTOR_USER_ID} user_id={TEST_ACTOR_USER_ID} "
        f"grant_key={grant_key} client_id={client_id} "
        f"self_declared_client_name='Claude' revoked_tokens=4"
    ]


@pytest.mark.parametrize("state", ["revoked", "expired"])
def test_a_revoked_or_expired_grant_is_not_reused(
    client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
    state: str,
) -> None:
    client_id = _register(client)
    _issued(client, client_id)
    with session_factory() as session:
        grant = _only_grant(session)
        old_key = grant.grant_key
        now = datetime.now(UTC)
        if state == "revoked":
            grant.revoked_time = now
        else:
            grant.created_time = now - timedelta(days=31)
            grant.expires_time = now - timedelta(seconds=1)
        session.commit()
    # Lazy cleanup would delete the inactive grant first; keep it, so the
    # reuse lookup itself must skip it.
    monkeypatch.setattr(token_service, "cleanup_expired_oauth_rows", _skip_cleanup)

    before = datetime.now(UTC)
    second = _issued(client, client_id)

    with session_factory() as session:
        grants = {
            grant.grant_key: grant for grant in session.scalars(select(McpOauthGrant))
        }
        assert len(grants) == 2
        old = grants.pop(old_key)
        assert (old.revoked_time is not None) == (state == "revoked")
        new = next(iter(grants.values()))
        assert new.revoked_time is None
        assert _as_utc(new.expires_time) >= before + timedelta(days=30)
    assert _verify(session_factory, second["access_token"]).grant_key == new.grant_key


def test_one_grant_covers_reading_and_writing(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    client_id = _register(client)
    issued = _issued(client, client_id)

    assert issued["scope"] == BOTH_SCOPES
    with session_factory() as session:
        grant = _only_grant(session)
        assert (grant.scopes, grant.resource) == (BOTH_SCOPES, RESOURCE)
    assert _verify(session_factory, issued["access_token"]).scopes == {
        "schatten.read",
        "schatten.write",
    }


def test_a_read_only_request_gets_a_read_only_grant(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    client_id = _register(client)
    issued = _issued(client, client_id, "schatten.read")

    assert issued["scope"] == "schatten.read"
    with session_factory() as session:
        assert _only_grant(session).scopes == "schatten.read"
    assert _verify(session_factory, issued["access_token"]).scopes == {"schatten.read"}


def test_token_responses_report_the_effective_scopes_of_the_role(
    client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client_id = _register(client)
    code = _approved_code(client, client_id)
    # The role is limited after consent: the grant keeps both scopes, and the
    # responses name only those the role allows (RFC 6749 section 5.1).
    monkeypatch.setitem(
        token_service.ROLE_SCOPES, "consultant", frozenset({"schatten.read"})
    )

    exchanged = _exchange(client, client_id, code).json()
    rotated = _rotated(client, client_id, exchanged["refresh_token"])

    assert exchanged["scope"] == rotated["scope"] == "schatten.read"
    with session_factory() as session:
        assert _only_grant(session).scopes == BOTH_SCOPES
    assert _verify(session_factory, rotated["access_token"]).scopes == {"schatten.read"}


def test_reauthorization_takes_the_newest_consents_scopes(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    client_id = _register(client)
    _issued(client, client_id)
    with session_factory() as session:
        grant_key = _only_grant(session).grant_key

    read_only = _issued(client, client_id, "schatten.read")
    with session_factory() as session:
        narrowed = _only_grant(session)
        assert (narrowed.grant_key, narrowed.scopes) == (grant_key, "schatten.read")
    both = _issued(client, client_id)

    assert read_only["scope"] == "schatten.read"
    assert both["scope"] == BOTH_SCOPES
    with session_factory() as session:
        widened = _only_grant(session)
        assert (widened.grant_key, widened.scopes) == (grant_key, BOTH_SCOPES)


# Refresh tokens


def test_refresh_rotates_and_only_links_the_old_token(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    client_id = _register(client)
    first = _issued(client, client_id)

    before = datetime.now(UTC)
    rotated = _rotated(client, client_id, first["refresh_token"])

    assert rotated["scope"] == BOTH_SCOPES
    assert rotated["token_type"] == "Bearer"
    assert rotated["refresh_token"] != first["refresh_token"]
    with session_factory() as session:
        old = _token_row(session, first["refresh_token"])
        assert old.replaced_by_hash == _sha256(rotated["refresh_token"])
        assert old.revoked_time is None
        new = _token_row(session, rotated["refresh_token"])
        assert (new.replaced_by_hash, new.revoked_time) == (None, None)
        assert _as_utc(new.expires_time) >= before + timedelta(days=7)
    for access_token in (first["access_token"], rotated["access_token"]):
        assert _verify(session_factory, access_token).user_id == TEST_ACTOR_USER_ID
    assert _rotated(client, client_id, rotated["refresh_token"])["scope"] == (
        BOTH_SCOPES
    )


@pytest.mark.parametrize(
    ("overrides", "error"),
    [
        pytest.param({"resource": None}, "invalid_target", id="no-resource"),
        pytest.param(
            {"resource": LEGACY_RESOURCES[0]}, "invalid_target", id="legacy-resource"
        ),
        pytest.param({"scope": "openid"}, "invalid_scope", id="unknown-scope"),
        pytest.param(
            {"scope": "schatten.read openid"}, "invalid_scope", id="unknown-in-set"
        ),
        pytest.param(
            {"scope": ["schatten.read", "schatten.read"]},
            "invalid_request",
            id="repeated-scope",
        ),
        pytest.param({"refresh_token": "A" * 43}, "invalid_grant", id="unknown"),
        pytest.param({"refresh_token": None}, "invalid_request", id="no-token"),
        pytest.param({"client_id": "unknown"}, "invalid_client", id="unknown-client"),
    ],
)
def test_invalid_refresh_requests_have_no_effect(
    client: TestClient,
    session_factory: sessionmaker[Session],
    overrides: dict[str, str | None],
    error: str,
) -> None:
    client_id = _register(client)
    issued = _issued(client, client_id)

    response = _refresh(client, client_id, issued["refresh_token"], **overrides)

    _assert_oauth_error(response, error)
    with session_factory() as session:
        assert _only_grant(session).revoked_time is None
        refresh = _token_row(session, issued["refresh_token"])
        assert (refresh.replaced_by_hash, refresh.revoked_time) == (None, None)
    assert _rotated(client, client_id, issued["refresh_token"])


@pytest.mark.parametrize(
    "scope",
    ["schatten.read", "schatten.write", BOTH_SCOPES, "schatten.write schatten.read"],
)
def test_a_refresh_scope_never_narrows_or_widens_the_token(
    client: TestClient, session_factory: sessionmaker[Session], scope: str
) -> None:
    client_id = _register(client)
    issued = _issued(client, client_id)

    response = _refresh(client, client_id, issued["refresh_token"], scope=scope)

    assert response.status_code == 200, response.text
    assert response.json()["scope"] == BOTH_SCOPES
    rotated = response.json()["access_token"]
    assert _verify(session_factory, rotated).scopes == {
        "schatten.read",
        "schatten.write",
    }


def test_refresh_rejects_another_clients_token_and_an_access_token(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    client_id = _register(client)
    other_client_id = _register(client, "Other")
    issued = _issued(client, client_id)

    _assert_oauth_error(
        _refresh(client, other_client_id, issued["refresh_token"]), "invalid_grant"
    )
    _assert_oauth_error(
        _refresh(client, client_id, issued["access_token"]), "invalid_grant"
    )
    with session_factory() as session:
        assert _only_grant(session).revoked_time is None


def test_refresh_token_expires_after_its_idle_lifetime(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    client_id = _register(client)
    issued = _issued(client, client_id)
    with session_factory() as session:
        refresh = _token_row(session, issued["refresh_token"])
        refresh.created_time = datetime.now(UTC) - timedelta(days=7, seconds=2)
        refresh.expires_time = datetime.now(UTC) - timedelta(seconds=1)
        session.commit()

    response = _refresh(client, client_id, issued["refresh_token"])

    _assert_oauth_error(response, "invalid_grant")
    assert response.json()["error_description"] == "Refresh token expired"
    with session_factory() as session:
        assert _only_grant(session).revoked_time is None
        assert _token_row(session, issued["refresh_token"]).replaced_by_hash is None


def test_grant_absolute_expiry_stops_refresh_without_further_effect(
    client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client_id = _register(client)
    first = _issued(client, client_id)
    rotated = _rotated(client, client_id, first["refresh_token"])
    with session_factory() as session:
        grant = _only_grant(session)
        grant.created_time = datetime.now(UTC) - timedelta(days=31)
        grant.expires_time = datetime.now(UTC) - timedelta(seconds=1)
        session.commit()
    # Lazy cleanup would delete the expired grant first; without it, ADR-015's
    # first check decides, even for the rotated token, and has no effect.
    monkeypatch.setattr(token_service, "cleanup_expired_oauth_rows", _skip_cleanup)

    for refresh_token in (rotated["refresh_token"], first["refresh_token"]):
        response = _refresh(client, client_id, refresh_token)
        _assert_oauth_error(response, "invalid_grant")
        assert response.json()["error_description"] == (
            "The grant is revoked or expired"
        )

    with session_factory() as session:
        assert _only_grant(session).revoked_time is None
        assert all(
            token.revoked_time is None
            for token in session.scalars(select(McpOauthToken))
        )
    assert _verify_error(session_factory, rotated["access_token"]) == "invalid_token"
    monkeypatch.undo()
    _assert_oauth_error(
        _refresh(client, client_id, rotated["refresh_token"]), "invalid_grant"
    )
    with session_factory() as session:
        assert session.scalar(select(McpOauthGrant)) is None
        assert session.scalar(select(McpOauthToken)) is None


def test_tokens_never_outlive_their_grant(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    client_id = _register(client)
    issued = _issued(client, client_id)
    grant_expiry = datetime.now(UTC) + timedelta(minutes=10)
    with session_factory() as session:
        _only_grant(session).expires_time = grant_expiry
        session.commit()

    rotated = _rotated(client, client_id, issued["refresh_token"])

    assert rotated["expires_in"] <= 600
    with session_factory() as session:
        for raw in (rotated["access_token"], rotated["refresh_token"]):
            assert _as_utc(_token_row(session, raw).expires_time) == grant_expiry


def test_refresh_token_reuse_revokes_the_grant_and_all_its_tokens(
    client: TestClient,
    session_factory: sessionmaker[Session],
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger=TOKEN_LOGGER)
    client_id = _register(client)
    first = _issued(client, client_id)
    rotated = _rotated(client, client_id, first["refresh_token"])

    replayed = _refresh(client, client_id, first["refresh_token"])

    _assert_oauth_error(replayed, "invalid_grant")
    with session_factory() as session:
        grant = _only_grant(session)
        assert grant.revoked_time is not None
        assert grant.revoked_by is None
        assert all(
            token.revoked_time is not None
            for token in session.scalars(select(McpOauthToken))
        )
        grant_key = grant.grant_key
    _assert_oauth_error(
        _refresh(client, client_id, rotated["refresh_token"]), "invalid_grant"
    )
    assert _verify_error(session_factory, rotated["access_token"]) == "invalid_token"
    assert _revocation_logs(caplog) == [
        f"MCP OAuth grant revoked: reason=refresh_token_reuse actor=system "
        f"user_id={TEST_ACTOR_USER_ID} grant_key={grant_key} client_id={client_id} "
        f"self_declared_client_name='Claude' revoked_tokens=4"
    ]


def test_rotated_token_triggers_reuse_detection_even_after_its_idle_expiry(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    client_id = _register(client)
    first = _issued(client, client_id)
    _rotated(client, client_id, first["refresh_token"])
    with session_factory() as session:
        old = _token_row(session, first["refresh_token"])
        old.created_time = datetime.now(UTC) - timedelta(days=8)
        old.expires_time = datetime.now(UTC) - timedelta(days=1)
        session.commit()

    response = _refresh(client, client_id, first["refresh_token"])

    _assert_oauth_error(response, "invalid_grant")
    assert response.json()["error_description"] == "Refresh token already used"
    with session_factory() as session:
        assert _only_grant(session).revoked_time is not None


def test_revoked_refresh_token_fails_without_revoking_the_grant(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    client_id = _register(client)
    first = _issued(client, client_id)
    rotated = _rotated(client, client_id, first["refresh_token"])
    # Re-authorization revokes the rotated and the current refresh token.
    second = _issued(client, client_id)

    for stale in (first["refresh_token"], rotated["refresh_token"]):
        response = _refresh(client, client_id, stale)
        _assert_oauth_error(response, "invalid_grant")
        assert response.json()["error_description"] == "Refresh token revoked"

    with session_factory() as session:
        assert _only_grant(session).revoked_time is None
        assert _token_row(session, first["refresh_token"]).replaced_by_hash
    assert _rotated(client, client_id, second["refresh_token"])


def test_token_issuance_updates_client_last_used_time_at_most_every_five_minutes(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    client_id = _register(client)
    code = _approved_code(client, client_id)

    def set_last_used(age: timedelta) -> datetime:
        with session_factory() as session:
            stored = session.scalar(
                select(McpOauthClient).where(McpOauthClient.client_id == client_id)
            )
            assert stored is not None
            value = datetime.now(UTC) - age
            stored.last_used_time = value
            session.commit()
            return value

    def last_used() -> datetime:
        with session_factory() as session:
            stored = session.scalar(
                select(McpOauthClient).where(McpOauthClient.client_id == client_id)
            )
            assert stored is not None and stored.last_used_time is not None
            return _as_utc(stored.last_used_time)

    set_last_used(timedelta(minutes=10))
    before = datetime.now(UTC)
    issued = _exchange(client, client_id, code).json()
    exchanged_at = last_used()
    assert exchanged_at >= before

    rotated = _rotated(client, client_id, issued["refresh_token"])
    assert last_used() == exchanged_at

    recent = set_last_used(timedelta(minutes=4))
    rotated = _rotated(client, client_id, rotated["refresh_token"])
    assert last_used() == recent

    set_last_used(timedelta(minutes=5, seconds=1))
    before = datetime.now(UTC)
    _rotated(client, client_id, rotated["refresh_token"])
    assert last_used() >= before

    second_code = _approved_code(client, client_id)
    authorized_at = last_used()
    assert _exchange(client, client_id, second_code).status_code == 200
    assert last_used() == authorized_at


# Lazy cleanup


def test_cleanup_deletes_a_revoked_grant_that_a_request_still_references(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    client_id = _register(client)
    first_code = _approved_code(client, client_id)
    first = _exchange(client, client_id, first_code).json()
    with session_factory() as session:
        first_key = _only_grant(session).grant_key
    assert client.delete(f"/api/v1/ai/connections/{first_key}").status_code == 204

    second = _issued(client, client_id)

    with session_factory() as session:
        # The revoked grant is gone (SQLite may reuse its row id, so compare
        # keys), its tokens cascaded and the first request's reference is null.
        new_grant = _only_grant(session)
        assert new_grant.grant_key != first_key
        for raw in (first["access_token"], first["refresh_token"]):
            assert session.get(McpOauthToken, _sha256(raw)) is None
        requests = session.scalars(select(McpOauthAuthorizationRequest)).all()
        assert len(requests) == 2
        assert all(request.consumed_time is not None for request in requests)
        assert sorted(
            [request.grant_id for request in requests], key=lambda value: value or 0
        ) == [None, new_grant.grant_id]

    # The first code's grant is gone, so its replay has nothing to revoke.
    _assert_oauth_error(_exchange(client, client_id, first_code), "invalid_grant")
    with session_factory() as session:
        assert _only_grant(session).revoked_time is None
    assert _verify(session_factory, second["access_token"])


def test_reuse_detection_survives_a_cleanup_pass(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    client_id = _register(client)
    first = _issued(client, client_id)
    rotated = _rotated(client, client_id, first["refresh_token"])
    now = datetime.now(UTC)
    with session_factory() as session:
        for token in session.scalars(select(McpOauthToken)):
            token.created_time = now - timedelta(days=8)
            if token.kind == "access" or token.replaced_by_hash is not None:
                token.expires_time = now - timedelta(days=1)
        for pending in session.scalars(select(McpOauthAuthorizationRequest)):
            pending.created_time = now - timedelta(days=8)
            pending.expires_time = now - timedelta(days=8) + timedelta(minutes=10)
            pending.code_expires_time = now - timedelta(days=8) + timedelta(minutes=1)
        session.commit()

    with session_factory() as session:
        cleanup_expired_oauth_rows(session, now=datetime.now(UTC))

    with session_factory() as session:
        assert session.scalar(select(McpOauthAuthorizationRequest)) is None
        remaining = session.scalars(select(McpOauthToken)).all()
        assert {(token.kind, token.token_hash) for token in remaining} == {
            ("refresh", _sha256(first["refresh_token"])),
            ("refresh", _sha256(rotated["refresh_token"])),
        }
        assert _only_grant(session).revoked_time is None

    replayed = _refresh(client, client_id, first["refresh_token"])

    _assert_oauth_error(replayed, "invalid_grant")
    assert replayed.json()["error_description"] == "Refresh token already used"
    with session_factory() as session:
        assert _only_grant(session).revoked_time is not None


def test_cleanup_keeps_a_request_whose_code_is_still_live(
    session_factory: sessionmaker[Session],
) -> None:
    with _client(session_factory) as client:
        client_id = _register(client)
        code = _approved_code(client, client_id)
        now = datetime.now(UTC)
        with session_factory() as session:
            pending = session.scalar(select(McpOauthAuthorizationRequest))
            assert pending is not None
            pending.created_time = now - timedelta(minutes=10, seconds=30)
            pending.expires_time = now - timedelta(seconds=30)
            session.commit()

        assert _exchange(client, client_id, code).status_code == 200


def test_client_is_hard_deleted_once_its_last_request_and_grant_are_gone(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    client_id = _register(client)
    _issued(client, client_id)
    live_client_id = _register(client, "Live")
    now = datetime.now(UTC)
    with session_factory() as session:
        stale = session.scalar(
            select(McpOauthClient).where(McpOauthClient.client_id == client_id)
        )
        assert stale is not None
        stale.created_time = now - timedelta(days=45)
        stale.last_used_time = now - timedelta(days=45)
        grant = _only_grant(session)
        grant.created_time = now - timedelta(days=45)
        grant.expires_time = now - timedelta(days=15)
        for pending in session.scalars(select(McpOauthAuthorizationRequest)):
            pending.created_time = now - timedelta(days=45)
            pending.expires_time = now - timedelta(days=45) + timedelta(minutes=10)
            pending.code_expires_time = now - timedelta(days=45) + timedelta(minutes=1)
        session.commit()

    # Client cleanup alone soft-deletes the stale client but keeps the row
    # while the expired request and grant still reference it.
    with session_factory() as session:
        cleanup_stale_clients(session, now=datetime.now(UTC))
    with session_factory() as session:
        stale = session.scalar(
            select(McpOauthClient).where(McpOauthClient.client_id == client_id)
        )
        assert stale is not None and stale.deleted_time is not None

    # Any token request runs the full lazy cleanup first.
    response = _refresh(client, live_client_id, "A" * 43)

    _assert_oauth_error(response, "invalid_grant")
    with session_factory() as session:
        assert session.scalar(select(McpOauthGrant)) is None
        assert session.scalar(select(McpOauthAuthorizationRequest)) is None
        assert session.scalar(select(McpOauthToken)) is None
        assert set(session.scalars(select(McpOauthClient.client_id))) == {
            live_client_id
        }


# RFC 7009 revocation


def test_revoking_an_access_token_revokes_only_that_token(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    client_id = _register(client)
    issued = _issued(client, client_id)

    response = _revoke(client, client_id, issued["access_token"])

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert _verify_error(session_factory, issued["access_token"]) == "invalid_token"
    with session_factory() as session:
        assert _only_grant(session).revoked_time is None
    assert _rotated(client, client_id, issued["refresh_token"])


def test_revoking_a_refresh_token_revokes_its_grant(
    client: TestClient,
    session_factory: sessionmaker[Session],
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger=TOKEN_LOGGER)
    client_id = _register(client)
    issued = _issued(client, client_id)

    response = _revoke(client, client_id, issued["refresh_token"])

    assert response.status_code == 200
    with session_factory() as session:
        grant = _only_grant(session)
        assert grant.revoked_time is not None
        assert grant.revoked_by is None
        grant_key = grant.grant_key
    assert _verify_error(session_factory, issued["access_token"]) == "invalid_token"
    assert client.get("/api/v1/ai/connections").json() == []
    assert _revocation_logs(caplog) == [
        f"MCP OAuth grant revoked: reason=client_revoke actor=client "
        f"user_id={TEST_ACTOR_USER_ID} grant_key={grant_key} client_id={client_id} "
        f"self_declared_client_name='Claude' revoked_tokens=2"
    ]
    _assert_no_secret_logged(caplog, [issued["access_token"], issued["refresh_token"]])


def test_revoke_answers_200_for_unknown_or_foreign_tokens(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    client_id = _register(client)
    other_client_id = _register(client, "Other")
    issued = _issued(client, client_id)

    responses = [
        _revoke(client, client_id, "A" * 43),
        _revoke(client, client_id, "not-a-token"),
        _revoke(client, other_client_id, issued["refresh_token"]),
        _post_form(
            client,
            "/api/oauth/revoke",
            {
                "client_id": client_id,
                "token": "A" * 43,
                "token_type_hint": "unknown_hint",
            },
        ),
    ]

    assert [response.status_code for response in responses] == [200] * 4
    with session_factory() as session:
        assert _only_grant(session).revoked_time is None
    assert _verify(session_factory, issued["access_token"])


@pytest.mark.parametrize(
    ("client_id", "token", "error"),
    [
        pytest.param("registered", None, "invalid_request", id="no-token"),
        pytest.param(None, "A" * 43, "invalid_client", id="no-client"),
        pytest.param("unknown", "A" * 43, "invalid_client", id="unknown-client"),
    ],
)
def test_revoke_requires_a_token_and_a_known_client(
    client: TestClient, client_id: str | None, token: str | None, error: str
) -> None:
    registered = _register(client)

    response = _revoke(
        client, registered if client_id == "registered" else client_id, token
    )

    _assert_oauth_error(response, error)


def test_token_and_revoke_buckets_never_consume_the_login_limiter(
    session_factory: sessionmaker[Session],
) -> None:
    settings = _settings(
        MCP_OAUTH_TOKEN_RATE_LIMIT_PER_MINUTE=1,
        MCP_OAUTH_REVOKE_RATE_LIMIT_PER_MINUTE=1,
    )
    with _client(session_factory, settings) as client:
        client_id = _register(client)
        _assert_oauth_error(_refresh(client, client_id, "A" * 43), "invalid_grant")
        limited_token = _refresh(client, client_id, "A" * 43)
        assert _revoke(client, client_id, "A" * 43).status_code == 200
        limited_revoke = _revoke(client, client_id, "A" * 43)
        state = cast(FastAPI, client.app).state
        auth_limiter = cast(FixedWindowRateLimiter, state.auth_rate_limiter)
        oauth_limiter = cast(FixedWindowRateLimiter, state.oauth_rate_limiter)

    for response in (limited_token, limited_revoke):
        assert response.status_code == 429
        assert response.json()["error"] == "temporarily_unavailable"
    assert auth_limiter._entries == {}
    assert {bucket for bucket, _, _ in oauth_limiter._entries} == {
        "register",
        "token",
        "revoke",
    }


# Token verification


def test_verify_access_token_returns_the_principal_and_throttles_last_used(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    client_id = _register(client)
    issued = _issued(client, client_id)

    before = datetime.now(UTC)
    principal = _verify(session_factory, issued["access_token"])

    with session_factory() as session:
        grant = _only_grant(session)
        assert grant.last_used_time is not None
        first_use = _as_utc(grant.last_used_time)
        assert first_use >= before
        expected = McpPrincipal(
            user_id=TEST_ACTOR_USER_ID,
            role="consultant",
            grant_id=grant.grant_id,
            grant_key=grant.grant_key,
            client_id=client_id,
            client_name="Claude",
            scopes=frozenset({"schatten.read", "schatten.write"}),
        )
    assert principal == expected

    _verify(session_factory, issued["access_token"])
    with session_factory() as session:
        grant = _only_grant(session)
        assert grant.last_used_time is not None
        assert _as_utc(grant.last_used_time) == first_use
        grant.last_used_time = datetime.now(UTC) - timedelta(minutes=5, seconds=1)
        session.commit()

    before = datetime.now(UTC)
    _verify(session_factory, issued["access_token"])
    with session_factory() as session:
        last_used = _only_grant(session).last_used_time
        assert last_used is not None and _as_utc(last_used) >= before


def _expire_access_token(session: Session, issued: dict[str, Any]) -> None:
    token = _token_row(session, issued["access_token"])
    token.created_time = datetime.now(UTC) - timedelta(hours=2)
    token.expires_time = datetime.now(UTC) - timedelta(seconds=1)


def _revoke_access_token(session: Session, issued: dict[str, Any]) -> None:
    _token_row(session, issued["access_token"]).revoked_time = datetime.now(UTC)


def _revoke_grant_row(session: Session, _issued: dict[str, Any]) -> None:
    _only_grant(session).revoked_time = datetime.now(UTC)


def _expire_grant(session: Session, _issued: dict[str, Any]) -> None:
    grant = _only_grant(session)
    grant.created_time = datetime.now(UTC) - timedelta(days=31)
    grant.expires_time = datetime.now(UTC) - timedelta(seconds=1)


def _delete_user(session: Session, _issued: dict[str, Any]) -> None:
    user = session.get(User, TEST_ACTOR_USER_ID)
    assert user is not None
    user.deleted_time = datetime.now(UTC)


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(_expire_access_token, id="expired-token"),
        pytest.param(_revoke_access_token, id="revoked-token"),
        pytest.param(_revoke_grant_row, id="revoked-grant"),
        pytest.param(_expire_grant, id="expired-grant"),
        pytest.param(_delete_user, id="deleted-user"),
    ],
)
def test_verify_access_token_rejects_invalid_state(
    client: TestClient, session_factory: sessionmaker[Session], mutate: Any
) -> None:
    client_id = _register(client)
    issued = _issued(client, client_id)
    with session_factory() as session:
        mutate(session, issued)
        session.commit()

    assert _verify_error(session_factory, issued["access_token"]) == "invalid_token"


def test_verify_access_token_rejects_unknown_tokens_and_the_other_resource(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    client_id = _register(client)
    read = _issued(client, client_id)

    for token in (None, "", "A" * 43, "short", "A" * 44, read["refresh_token"]):
        assert _verify_error(session_factory, token) == "invalid_token"
    # The token presented for a legacy or another origin's resource.
    for resource in (*LEGACY_RESOURCES, "https://other.example/api/mcp"):
        assert (
            _verify_error(session_factory, read["access_token"], resource)
            == "invalid_token"
        )
    assert (
        _verify_error(session_factory, read["access_token"], RESOURCE, "x")
        == "insufficient_scope"
    )
    with session_factory() as session:
        assert _only_grant(session).last_used_time is None


def test_role_change_takes_effect_on_the_next_verification(
    session_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    # Both current roles have both scopes; limit one to show the role re-read.
    monkeypatch.setitem(
        token_service.ROLE_SCOPES, "consultant", frozenset({"schatten.read"})
    )
    with _client(session_factory, role="admin") as client:
        client_id = _register(client)
        issued = _issued(client, client_id)

    def set_role(role: str) -> None:
        with session_factory() as session:
            user = session.get(User, TEST_ACTOR_USER_ID)
            assert user is not None
            user.role = role
            session.commit()

    admin = _verify(session_factory, issued["access_token"])
    set_role("consultant")
    consultant = _verify(session_factory, issued["access_token"])
    write_required = _verify_error(
        session_factory, issued["access_token"], scope="schatten.write"
    )
    set_role("admin")

    assert admin.role == "admin"
    assert admin.scopes == {"schatten.read", "schatten.write"}
    assert consultant.scopes == {"schatten.read"}
    assert write_required == "insufficient_scope"
    assert _verify(session_factory, issued["access_token"]).scopes == {
        "schatten.read",
        "schatten.write",
    }


# Connections API


def test_connections_list_only_the_current_users_active_grants(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    client_id = _register(client)
    other_client_id = _register(client, "Claude Code")
    used = _issued(client, client_id)
    _issued(client, other_client_id, "schatten.read")
    _verify(session_factory, used["access_token"])
    with session_factory() as session:
        own = {
            grant.mcp_oauth_client_id: grant
            for grant in session.scalars(select(McpOauthGrant))
        }
        stored_ids = {
            stored.client_id: stored.mcp_oauth_client_id
            for stored in session.scalars(select(McpOauthClient))
        }
        _add_grant(session, client_id, user_id=OTHER_USER_ID)
        _add_grant(session, client_id, user_id=TEST_ACTOR_USER_ID, revoked=True)
        _add_grant(session, client_id, user_id=TEST_ACTOR_USER_ID, expired=True)
        expected = [
            {
                "grantKey": grant.grant_key,
                "clientId": grant_client_id,
                "clientName": client_name,
                "scope": grant.scopes,
                "resource": RESOURCE,
                "createdTime": _as_utc(grant.created_time),
                "lastUsedTime": (
                    None
                    if grant.last_used_time is None
                    else _as_utc(grant.last_used_time)
                ),
                "expiresTime": _as_utc(grant.expires_time),
            }
            for grant, grant_client_id, client_name in (
                (
                    own[stored_ids[other_client_id]],
                    other_client_id,
                    "Claude Code",
                ),
                (own[stored_ids[client_id]], client_id, "Claude"),
            )
        ]

    response = client.get("/api/v1/ai/connections")

    assert response.status_code == 200
    body = response.json()
    for item in body:
        for name in ("createdTime", "expiresTime"):
            item[name] = datetime.fromisoformat(item[name])
        if item["lastUsedTime"] is not None:
            item["lastUsedTime"] = datetime.fromisoformat(item["lastUsedTime"])
    assert body == expected
    assert body[1]["lastUsedTime"] is not None


def test_connections_report_the_effective_scopes_of_the_role(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    client_id = _register(client)
    _issued(client, client_id)
    monkeypatch.setitem(
        token_service.ROLE_SCOPES, "consultant", frozenset({"schatten.read"})
    )

    response = client.get("/api/v1/ai/connections")

    assert response.status_code == 200
    assert [item["scope"] for item in response.json()] == ["schatten.read"]


def test_users_revoke_their_own_connection_and_its_tokens(
    client: TestClient,
    session_factory: sessionmaker[Session],
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger=TOKEN_LOGGER)
    client_id = _register(client)
    issued = _issued(client, client_id)
    with session_factory() as session:
        grant_key = _only_grant(session).grant_key

    response = client.delete(f"/api/v1/ai/connections/{grant_key}")

    assert response.status_code == 204
    with session_factory() as session:
        grant = _only_grant(session)
        assert grant.revoked_time is not None
        assert grant.revoked_by == TEST_ACTOR_USER_ID
        assert all(
            token.revoked_time is not None
            for token in session.scalars(select(McpOauthToken))
        )
    assert client.get("/api/v1/ai/connections").json() == []
    assert _verify_error(session_factory, issued["access_token"]) == "invalid_token"
    _assert_oauth_error(
        _refresh(client, client_id, issued["refresh_token"]), "invalid_grant"
    )
    assert _revocation_logs(caplog) == [
        f"MCP OAuth grant revoked: reason=user_revoke "
        f"actor=user:{TEST_ACTOR_USER_ID} user_id={TEST_ACTOR_USER_ID} "
        f"grant_key={grant_key} client_id={client_id} "
        f"self_declared_client_name='Claude' revoked_tokens=2"
    ]
    _assert_no_secret_logged(caplog, [issued["access_token"], issued["refresh_token"]])
    repeated = client.delete(f"/api/v1/ai/connections/{grant_key}")
    assert repeated.status_code == 404


def test_users_cannot_revoke_another_users_connection(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    client_id = _register(client)
    with session_factory() as session:
        foreign = _add_grant(session, client_id, user_id=OTHER_USER_ID)
        _add_token(session, foreign, "f" * 43)
        foreign_key = foreign.grant_key

    responses = [
        client.delete(f"/api/v1/ai/connections/{foreign_key}"),
        client.delete("/api/v1/ai/connections/unknown"),
        client.delete("/api/v1/ai/connections/nul%00key"),
    ]

    for response in responses:
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "CONNECTION_NOT_FOUND"
    with session_factory() as session:
        grant = _only_grant(session)
        assert grant.revoked_time is None
        assert _token_row(session, "f" * 43).revoked_time is None


@pytest.mark.parametrize(
    "headers",
    [
        pytest.param({}, id="missing"),
        pytest.param(
            {"Origin": "https://attacker.example", "X-CSRF-Token": TEST_CSRF_TOKEN},
            id="cross-origin",
        ),
        pytest.param({"Origin": ORIGIN, "X-CSRF-Token": "wrong"}, id="wrong-csrf"),
    ],
)
def test_connection_revocation_requires_csrf_and_exact_origin(
    client: TestClient,
    session_factory: sessionmaker[Session],
    headers: dict[str, str],
) -> None:
    client_id = _register(client)
    _issued(client, client_id)
    with session_factory() as session:
        grant_key = _only_grant(session).grant_key
    del client.headers["Origin"]
    del client.headers["X-CSRF-Token"]

    response = client.delete(f"/api/v1/ai/connections/{grant_key}", headers=headers)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"
    with session_factory() as session:
        assert _only_grant(session).revoked_time is None


def test_admin_revokes_every_active_connection_of_one_user(
    session_factory: sessionmaker[Session], caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger=TOKEN_LOGGER)
    with _client(session_factory, role="admin") as client:
        client_id = _register(client)
        own = _issued(client, client_id)
        with session_factory() as session:
            targets = [
                _add_grant(session, client_id, key="grant-target-1"),
                _add_grant(
                    session, client_id, scopes="schatten.read", key="grant-target-2"
                ),
            ]
            _add_token(session, targets[0], "t" * 43)
            _add_grant(session, client_id, revoked=True)
            target_keys = [grant.grant_key for grant in targets]

        response = client.post(f"/api/v1/ai/users/{OTHER_USER_ID}/connections/revoke")
        repeated = client.post(f"/api/v1/ai/users/{OTHER_USER_ID}/connections/revoke")

    assert response.status_code == 200
    assert response.json() == {"revokedCount": 2}
    assert repeated.json() == {"revokedCount": 0}
    with session_factory() as session:
        for key in target_keys:
            grant = session.scalar(
                select(McpOauthGrant).where(McpOauthGrant.grant_key == key)
            )
            assert grant is not None
            assert grant.revoked_time is not None
            assert grant.revoked_by == TEST_ACTOR_USER_ID
        assert _token_row(session, "t" * 43).revoked_time is not None
    assert _verify(session_factory, own["access_token"])
    assert _revocation_logs(caplog) == [
        f"MCP OAuth grant revoked: reason=admin_revoke "
        f"actor=user:{TEST_ACTOR_USER_ID} user_id={OTHER_USER_ID} "
        f"grant_key={key} client_id={client_id} "
        f"self_declared_client_name='Claude' revoked_tokens={count}"
        for key, count in zip(target_keys, (1, 0), strict=True)
    ]


def test_admin_revocation_covers_soft_deleted_users_and_rejects_unknown_users(
    session_factory: sessionmaker[Session],
) -> None:
    with _client(session_factory, role="admin") as client:
        client_id = _register(client)
        with session_factory() as session:
            _add_grant(session, client_id)
            user = session.get(User, OTHER_USER_ID)
            assert user is not None
            user.deleted_time = datetime.now(UTC)
            session.commit()

        deleted_user = client.post(
            f"/api/v1/ai/users/{OTHER_USER_ID}/connections/revoke"
        )
        unknown_user = client.post("/api/v1/ai/users/999/connections/revoke")

    assert deleted_user.json() == {"revokedCount": 1}
    assert unknown_user.status_code == 404
    assert unknown_user.json()["error"]["code"] == "USER_NOT_FOUND"


@pytest.mark.parametrize(
    ("role", "headers"),
    [
        pytest.param("consultant", None, id="consultant"),
        pytest.param("admin", {}, id="admin-missing-csrf"),
        pytest.param(
            "admin",
            {"Origin": "https://attacker.example", "X-CSRF-Token": TEST_CSRF_TOKEN},
            id="admin-cross-origin",
        ),
        pytest.param(
            "admin", {"Origin": ORIGIN, "X-CSRF-Token": "wrong"}, id="admin-wrong-csrf"
        ),
    ],
)
def test_admin_revocation_rejects_consultants_and_csrf_or_origin_failures(
    session_factory: sessionmaker[Session],
    role: str,
    headers: dict[str, str] | None,
) -> None:
    with _client(session_factory, role=role) as client:
        client_id = _register(client)
        with session_factory() as session:
            _add_grant(session, client_id)
        if headers is not None:
            del client.headers["Origin"]
            del client.headers["X-CSRF-Token"]
        response = client.post(
            f"/api/v1/ai/users/{OTHER_USER_ID}/connections/revoke", headers=headers
        )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"
    with session_factory() as session:
        assert _only_grant(session).revoked_time is None


def test_connections_stay_registered_while_mcp_is_disabled(
    session_factory: sessionmaker[Session],
) -> None:
    with _client(session_factory, role="admin") as enabled:
        client_id = _register(enabled)
        issued = _issued(enabled, client_id)
    with session_factory() as session:
        grant_key = _only_grant(session).grant_key

    with _client(session_factory, Settings(), existing_session=True) as disabled:
        token = _refresh(disabled, client_id, issued["refresh_token"])
        revoke = _revoke(disabled, client_id, issued["refresh_token"])
        listed = disabled.get("/api/v1/ai/connections")
        deleted = disabled.delete(f"/api/v1/ai/connections/{grant_key}")
        admin = disabled.post(
            f"/api/v1/ai/users/{TEST_ACTOR_USER_ID}/connections/revoke"
        )

    assert (token.status_code, revoke.status_code) == (404, 404)
    assert listed.status_code == 200
    assert [item["grantKey"] for item in listed.json()] == [grant_key]
    assert deleted.status_code == 204
    assert admin.json() == {"revokedCount": 0}


def test_refresh_fails_for_a_soft_deleted_user(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    client_id = _register(client)
    issued = _issued(client, client_id)
    with session_factory() as session:
        user = session.get(User, TEST_ACTOR_USER_ID)
        assert user is not None
        user.deleted_time = datetime.now(UTC)
        session.commit()

    _assert_oauth_error(
        _refresh(client, client_id, issued["refresh_token"]), "invalid_grant"
    )
    with session_factory() as session:
        assert _token_row(session, issued["refresh_token"]).replaced_by_hash is None


def test_admin_revocation_treats_an_out_of_range_user_id_as_unknown(
    session_factory: sessionmaker[Session],
) -> None:
    with _client(session_factory, role="admin") as client:
        response = client.post(
            f"/api/v1/ai/users/{2**63}/connections/revoke",
        )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "USER_NOT_FOUND"


def test_audit_entries_are_emitted_when_the_root_logger_drops_info(
    session_factory: sessionmaker[Session],
) -> None:
    # `fastapi run` leaves the root logger at WARNING without a handler.
    root = logging.getLogger()
    root_level = root.level
    stream = io.StringIO()
    previous_stream = AUDIT_HANDLER.setStream(stream)
    try:
        root.setLevel(logging.WARNING)
        with _client(session_factory) as client:
            client_id = _register(client)
            issued = _issued(client, client_id)
            with session_factory() as session:
                grant_key = _only_grant(session).grant_key
            assert client.delete(f"/api/v1/ai/connections/{grant_key}").status_code == (
                204
            )
    finally:
        root.setLevel(root_level)
        if previous_stream is not None:
            AUDIT_HANDLER.setStream(previous_stream)

    output = stream.getvalue()
    assert "MCP OAuth client registered" in output
    assert (
        f"MCP OAuth grant revoked: reason=user_revoke "
        f"actor=user:{TEST_ACTOR_USER_ID}" in output
    )
    for secret in (issued["access_token"], issued["refresh_token"]):
        assert secret not in output


@pytest.mark.parametrize(
    "path",
    [
        "/api/oauth/token?refresh_token=SECRETTOKEN&grant_type=refresh_token",
        "/api/oauth/revoke?token=SECRETTOKEN",
        "/api/mcp?access_token=SECRETTOKEN",
        "/api/oauth/token?code=SECRETTOKEN&code_verifier=SECRETTOKEN",
    ],
)
def test_access_log_filter_redacts_misplaced_tokens(path: str) -> None:
    record = logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        "",
        0,
        '%s - "%s %s HTTP/%s" %d',
        ("192.0.2.1", "POST", path, "1.1", 400),
        None,
    )

    assert SensitiveQueryFilter().filter(record)
    assert "SECRETTOKEN" not in record.getMessage()


def test_token_values_never_appear_in_logs(
    client: TestClient,
    session_factory: sessionmaker[Session],
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    client_id = _register(client)
    code = _approved_code(client, client_id)
    first = _exchange(client, client_id, code).json()
    rotated = _rotated(client, client_id, first["refresh_token"])
    second = _issued(client, client_id)
    _verify(session_factory, second["access_token"])
    _refresh(client, client_id, first["refresh_token"])
    _exchange(client, client_id, code)
    _revoke(client, client_id, second["refresh_token"])

    assert len(_revocation_logs(caplog)) == 2
    _assert_no_secret_logged(
        caplog,
        [
            code,
            first["access_token"],
            first["refresh_token"],
            rotated["access_token"],
            rotated["refresh_token"],
            second["access_token"],
            second["refresh_token"],
        ],
    )
