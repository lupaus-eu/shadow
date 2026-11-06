import hashlib
import logging
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlencode, urlsplit

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import StaticPool, create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.api.v1.auth.logging import SensitiveQueryFilter
from app.api.v1.auth.provider import NormalizedClaims, OidcProviderError
from app.api.v1.auth.rate_limit import FixedWindowRateLimiter
from app.api.v1.auth.service import AuthenticationError, resolve_identity
from app.api.v1.users.models import (
    AuthSession,
    OidcLoginTransaction,
    User,
    UserIdentity,
)
from app.core.config import Settings
from app.core.database import get_db_session
from app.core.models import Base
from app.main import create_app

# The domain the test client stores server-set cookies under.
TEST_SERVER_COOKIE_DOMAIN = "testserver.local"


class FakeProvider:
    def __init__(self) -> None:
        self.authorization_requests: list[tuple[str, str, str]] = []
        self.exchange_requests: list[tuple[str, str, str]] = []
        self.claims = NormalizedClaims(
            issuer="https://issuer.test",
            subject="subject-1",
            email="user@example.com",
            name="Provider Name",
            id_token="fake.id.token",
        )
        self.exchange_error = False
        self.logout_hints: list[str | None] = []

    def initialize(self) -> None:
        return None

    def authorization_url(self, *, state: str, nonce: str, pkce_verifier: str) -> str:
        self.authorization_requests.append((state, nonce, pkce_verifier))
        return f"https://issuer.test/authorize?{urlencode({'state': state})}"

    def exchange_code(
        self, *, code: str, nonce: str, pkce_verifier: str
    ) -> NormalizedClaims:
        self.exchange_requests.append((code, nonce, pkce_verifier))
        if self.exchange_error:
            raise OidcProviderError("fake provider failure")
        return self.claims

    def logout_url(self, *, id_token_hint: str | None = None) -> str | None:
        self.logout_hints.append(id_token_hint)
        return (
            "https://issuer.test/logout?client_id=test-client&"
            "post_logout_redirect_uri=http%3A%2F%2Ftestserver%2Flogin"
        )


@pytest.fixture()
def session_factory() -> Iterator[sessionmaker[Session]]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    yield factory
    engine.dispose()


@pytest.fixture()
def provider() -> FakeProvider:
    return FakeProvider()


@pytest.fixture()
def client(
    session_factory: sessionmaker[Session], provider: FakeProvider
) -> Iterator[TestClient]:
    with session_factory() as session:
        session.add(
            User(
                name="Database User",
                email="user@example.com",
                role="consultant",
            )
        )
        session.commit()

    settings = Settings()
    app = create_app(settings=settings, oidc_provider=provider)

    def override_get_db_session() -> Iterator[Session]:
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db_session
    with TestClient(app, follow_redirects=False) as test_client:
        yield test_client


def _start(client: TestClient, return_to: str = "/workspace") -> tuple[str, str]:
    response = client.get("/api/v1/auth/login", params={"return_to": return_to})
    assert response.status_code == 302
    state = parse_qs(urlsplit(response.headers["location"]).query)["state"][0]
    browser_binding = client.cookies.get("shadow-preauth")
    assert browser_binding is not None
    return state, browser_binding


def _login(client: TestClient) -> str:
    state, _ = _start(client)
    response = client.get(
        "/api/v1/auth/callback", params={"state": state, "code": "provider-code"}
    )
    assert response.status_code == 303
    assert response.headers["location"] == "http://testserver/workspace"
    raw_session = client.cookies.get("shadow-session")
    assert raw_session is not None
    return raw_session


def test_login_persists_only_hashed_state_and_browser_binding(
    client: TestClient,
    provider: FakeProvider,
    session_factory: sessionmaker[Session],
) -> None:
    response = client.get("/api/v1/auth/login", params={"return_to": "/workspace"})
    assert response.status_code == 302
    state = parse_qs(urlsplit(response.headers["location"]).query)["state"][0]
    browser_binding = client.cookies.get("shadow-preauth")
    assert browser_binding is not None

    assert provider.authorization_requests[0][0] == state
    with session_factory() as session:
        transaction = session.scalar(select(OidcLoginTransaction))
        assert transaction is not None
        assert transaction.state_hash == hashlib.sha256(state.encode()).digest()
        assert (
            transaction.browser_binding_hash
            == hashlib.sha256(browser_binding.encode()).digest()
        )
        assert state not in transaction.pkce_verifier
    cookie_header = response.headers["set-cookie"]
    assert "HttpOnly" in cookie_header
    assert "SameSite=lax" in cookie_header
    assert "Max-Age=600" in cookie_header
    assert "Domain=" not in cookie_header


@pytest.mark.parametrize(
    "return_to",
    [
        "https://attacker.test/path",
        "//attacker.test/path",
        "/path#fragment",
        "/path\\escape",
        "/bad%zz",
    ],
)
def test_login_rejects_unsafe_return_paths(client: TestClient, return_to: str) -> None:
    response = client.get("/api/v1/auth/login", params={"return_to": return_to})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_RETURN_PATH"
    assert response.headers["cache-control"] == "no-store"


def test_valid_callback_first_links_and_creates_opaque_session(
    client: TestClient,
    provider: FakeProvider,
    session_factory: sessionmaker[Session],
) -> None:
    raw_session = _login(client)

    response = client.get("/api/v1/auth/session")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {
        "user": {
            "id": 1,
            "name": "Database User",
            "email": "user@example.com",
            "role": "consultant",
        },
        "csrfToken": response.json()["csrfToken"],
        "features": {"mcp": False, "mcpChangeSetReview": False},
    }
    serialized = response.text
    assert "provider-code" not in serialized
    assert "access_token" not in serialized
    with session_factory() as session:
        identity = session.scalar(select(UserIdentity))
        stored_session = session.scalar(select(AuthSession))
        assert identity is not None
        assert (identity.issuer, identity.subject) == (
            "https://issuer.test",
            "subject-1",
        )
        assert stored_session is not None
        assert (
            stored_session.session_id_hash
            == hashlib.sha256(raw_session.encode()).digest()
        )
        assert not session.scalars(select(OidcLoginTransaction)).all()
    assert len(provider.exchange_requests) == 1


def test_callback_sets_strict_host_only_application_cookie(
    client: TestClient,
) -> None:
    state, _ = _start(client)

    response = client.get(
        "/api/v1/auth/callback", params={"state": state, "code": "provider-code"}
    )

    cookie_headers = response.headers.get_list("set-cookie")
    session_cookie = next(
        header for header in cookie_headers if header.startswith("shadow-session=")
    )
    assert "HttpOnly" in session_cookie
    assert "SameSite=strict" in session_cookie
    assert "Max-Age=28800" in session_cookie
    assert "Path=/" in session_cookie
    assert "Domain=" not in session_cookie


def test_callback_replay_is_rejected_without_second_exchange(
    client: TestClient, provider: FakeProvider
) -> None:
    state, _ = _start(client)
    first = client.get(
        "/api/v1/auth/callback", params={"state": state, "code": "first-code"}
    )
    replay = client.get(
        "/api/v1/auth/callback", params={"state": state, "code": "replay-code"}
    )

    assert first.status_code == 303
    assert replay.status_code == 303
    assert replay.headers["location"].endswith("/login?error=authentication_failed")
    assert [request[0] for request in provider.exchange_requests] == ["first-code"]


def test_swapped_browser_binding_does_not_consume_transaction(
    client: TestClient,
    provider: FakeProvider,
    session_factory: sessionmaker[Session],
) -> None:
    state, valid_binding = _start(client)
    swapped_binding = "A" * 43
    assert swapped_binding != valid_binding
    # Replace the server-set cookie instead of adding a second one with the
    # same name: the Cookie header order of such duplicates is client-specific.
    client.cookies.set(
        "shadow-preauth", swapped_binding, domain=TEST_SERVER_COOKIE_DOMAIN
    )

    response = client.get(
        "/api/v1/auth/callback", params={"state": state, "code": "secret-code"}
    )

    assert response.status_code == 303
    assert not provider.exchange_requests
    with session_factory() as session:
        assert (
            session.scalar(select(func.count()).select_from(OidcLoginTransaction)) == 1
        )
    client.cookies.set(
        "shadow-preauth", valid_binding, domain=TEST_SERVER_COOKIE_DOMAIN
    )


def test_provider_error_consumes_all_browser_bound_transactions(
    client: TestClient,
    provider: FakeProvider,
    session_factory: sessionmaker[Session],
) -> None:
    first_state, _ = _start(client)
    _start(client)
    provider.exchange_error = True

    response = client.get(
        "/api/v1/auth/callback",
        params={"state": first_state, "code": "sensitive-code"},
    )

    assert response.status_code == 303
    assert response.headers["location"].endswith("/login?error=authentication_failed")
    with session_factory() as session:
        assert (
            session.scalar(select(func.count()).select_from(OidcLoginTransaction)) == 0
        )


def test_browser_transaction_cap_returns_429_before_provider(
    client: TestClient, provider: FakeProvider
) -> None:
    for _ in range(5):
        assert client.get("/api/v1/auth/login").status_code == 302
    response = client.get("/api/v1/auth/login")

    assert response.status_code == 429
    assert response.json()["error"]["code"] == "RATE_LIMITED"
    assert len(provider.authorization_requests) == 5


def test_public_endpoint_address_rate_limits_are_applied_before_provider(
    client: TestClient, provider: FakeProvider
) -> None:
    for _ in range(20):
        client.cookies.clear()
        assert client.get("/api/v1/auth/login").status_code == 302
    login_limited = client.get("/api/v1/auth/login")
    assert login_limited.status_code == 429
    assert len(provider.authorization_requests) == 20


def test_callback_address_rate_limit_returns_429_before_exchange(
    client: TestClient, provider: FakeProvider
) -> None:
    for _ in range(60):
        response = client.get(
            "/api/v1/auth/callback", params={"state": "invalid", "code": "secret"}
        )
        assert response.status_code == 303
    limited = client.get(
        "/api/v1/auth/callback", params={"state": "invalid", "code": "secret"}
    )

    assert limited.status_code == 429
    assert not provider.exchange_requests


def test_session_rechecks_current_role_and_soft_delete(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    _login(client)
    with session_factory() as session:
        user = session.scalar(select(User))
        assert user is not None
        user.role = "admin"
        session.commit()
    refreshed = client.get("/api/v1/auth/session")
    assert refreshed.json()["user"]["role"] == "admin"

    with session_factory() as session:
        user = session.scalar(select(User))
        assert user is not None
        user.deleted_time = datetime.now(UTC)
        session.commit()
    denied = client.get("/api/v1/auth/session")
    assert denied.status_code == 401
    assert denied.json() == {
        "error": {
            "code": "AUTHENTICATION_REQUIRED",
            "message": "Authentication required",
        }
    }


@pytest.mark.parametrize("expiry_kind", ["idle", "absolute"])
def test_expired_sessions_are_deleted(
    client: TestClient,
    session_factory: sessionmaker[Session],
    expiry_kind: str,
) -> None:
    _login(client)
    with session_factory() as session:
        auth_session = session.scalar(select(AuthSession))
        assert auth_session is not None
        if expiry_kind == "idle":
            old_activity = datetime.now(UTC) - timedelta(minutes=31)
            auth_session.created_time = old_activity - timedelta(seconds=1)
            auth_session.last_activity_time = old_activity
        else:
            auth_session.created_time = datetime.now(UTC) - timedelta(hours=9)
            auth_session.last_activity_time = auth_session.created_time
            auth_session.absolute_expires_time = datetime.now(UTC) - timedelta(
                seconds=1
            )
        session.commit()

    response = client.get("/api/v1/auth/session")
    assert response.status_code == 401
    assert "shadow-session=" in response.headers["set-cookie"]
    assert "Max-Age=0" in response.headers["set-cookie"]
    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(AuthSession)) == 0


@pytest.mark.parametrize(
    ("origin", "csrf", "expected"),
    [
        (None, "valid", 403),
        ("null", "valid", 403),
        ("http://attacker.test", "valid", 403),
        ("http://testserver", "invalid", 403),
        ("http://testserver", "valid", 200),
    ],
)
def test_logout_requires_exact_origin_and_csrf(
    client: TestClient,
    origin: str | None,
    csrf: str,
    expected: int,
) -> None:
    _login(client)
    csrf_token = client.get("/api/v1/auth/session").json()["csrfToken"]
    headers = {"X-CSRF-Token": csrf_token if csrf == "valid" else "wrong"}
    if origin is not None:
        headers["Origin"] = origin

    response = client.post("/api/v1/auth/logout", headers=headers)

    assert response.status_code == expected
    if expected == 200:
        assert response.json()["logoutUrl"].startswith("https://issuer.test/logout?")
        assert client.get("/api/v1/auth/session").status_code == 401


def test_the_id_token_is_kept_with_the_session_and_sent_as_the_logout_hint(
    client: TestClient,
    provider: FakeProvider,
    session_factory: sessionmaker[Session],
) -> None:
    _login(client)
    with session_factory() as session:
        stored = session.scalars(select(AuthSession.id_token)).one()
    assert stored == "fake.id.token"
    csrf_token = client.get("/api/v1/auth/session").json()["csrfToken"]

    response = client.post(
        "/api/v1/auth/logout",
        headers={"Origin": "http://testserver", "X-CSRF-Token": csrf_token},
    )

    assert response.status_code == 200
    assert provider.logout_hints == ["fake.id.token"]
    with session_factory() as session:
        assert session.scalars(select(AuthSession.id_token)).all() == []


def test_a_session_without_an_id_token_logs_out_without_a_hint(
    client: TestClient,
    provider: FakeProvider,
    session_factory: sessionmaker[Session],
) -> None:
    provider.claims = NormalizedClaims(
        issuer="https://issuer.test",
        subject="subject-1",
        email="user@example.com",
        name="Provider Name",
    )
    _login(client)
    csrf_token = client.get("/api/v1/auth/session").json()["csrfToken"]

    response = client.post(
        "/api/v1/auth/logout",
        headers={"Origin": "http://testserver", "X-CSRF-Token": csrf_token},
    )

    assert response.status_code == 200
    assert provider.logout_hints == [None]


def test_the_id_token_is_never_returned_by_the_session_endpoint(
    client: TestClient,
) -> None:
    _login(client)
    body = client.get("/api/v1/auth/session").text
    assert "fake.id.token" not in body


def test_rejected_unsafe_request_does_not_extend_session_activity(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    _login(client)
    old_activity = datetime.now(UTC) - timedelta(minutes=6)
    with session_factory() as session:
        auth_session = session.scalar(select(AuthSession))
        assert auth_session is not None
        auth_session.created_time = old_activity - timedelta(seconds=1)
        auth_session.last_activity_time = old_activity
        session.commit()

    response = client.post(
        "/api/v1/auth/logout",
        headers={"Origin": "null", "X-CSRF-Token": "wrong"},
    )

    assert response.status_code == 403
    with session_factory() as session:
        auth_session = session.scalar(select(AuthSession))
        assert auth_session is not None
        stored = auth_session.last_activity_time
        assert stored.replace(tzinfo=UTC) == old_activity


def test_host_and_untrusted_forwarded_client_headers_fail_closed(
    client: TestClient,
) -> None:
    invalid_host = client.get("/api/v1/auth/session", headers={"Host": "evil.test"})
    untrusted_forward = client.get(
        "/api/v1/auth/session", headers={"X-Shadow-Client-IP": "192.0.2.1"}
    )

    assert invalid_host.status_code == 400
    assert invalid_host.json()["error"]["code"] == "INVALID_HOST"
    assert untrusted_forward.status_code == 400
    assert untrusted_forward.json()["error"]["code"] == "UNTRUSTED_FORWARDED_HEADER"
    assert invalid_host.headers["cache-control"] == "no-store"


def test_forwarded_client_header_is_accepted_only_from_configured_caddy_peer(
    provider: FakeProvider,
) -> None:
    settings = Settings.model_validate({"TRUSTED_CADDY_PEER_CIDRS": "127.0.0.0/8"})
    app = create_app(settings=settings, oidc_provider=provider)

    with TestClient(app, client=("127.0.0.1", 50000)) as trusted_client:
        response = trusted_client.get(
            "/health", headers={"X-Shadow-Client-IP": "192.0.2.10"}
        )

    assert response.status_code == 200


@pytest.mark.parametrize("path", ["/health/", "/api/v1/auth/session/"])
@pytest.mark.parametrize("method", ["GET", "POST"])
def test_trailing_slash_is_not_redirected(
    client: TestClient, path: str, method: str
) -> None:
    # A slash redirect builds Location from the scheme FastAPI sees, which is
    # http behind Caddy (TASK-071).
    response = client.request(method, path, headers={"X-Forwarded-Proto": "https"})

    assert response.status_code == 404
    assert "location" not in response.headers


def test_fixed_window_rate_limiter_is_bounded_and_resets() -> None:
    limiter = FixedWindowRateLimiter(max_entries=1)
    first_window = datetime(2026, 8, 15, 10, 0, tzinfo=UTC)

    assert limiter.allow("login", "192.0.2.1", 1, now=first_window)
    assert not limiter.allow("login", "192.0.2.1", 1, now=first_window)
    assert not limiter.allow("login", "192.0.2.2", 1, now=first_window)
    assert limiter.allow(
        "login", "192.0.2.2", 1, now=first_window + timedelta(minutes=1)
    )


def test_access_log_filter_removes_complete_callback_query() -> None:
    record = logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        "",
        0,
        '%s - "%s %s HTTP/%s" %d',
        (
            "192.0.2.1",
            "GET",
            "/api/v1/auth/callback?code=secret&id_token_hint=secret-session"
            "&state=state&email=user@example.com",
            "1.1",
            303,
        ),
        None,
    )

    assert SensitiveQueryFilter().filter(record)
    rendered = record.getMessage()
    assert rendered.endswith('GET /api/v1/auth/callback HTTP/1.1" 303')
    assert "secret" not in rendered
    assert "user@example.com" not in rendered


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        (
            "/api/v1/auth/login?id_token_hint=SECRETTOKEN&visible=kept",
            "/api/v1/auth/login?id_token_hint=REDACTED&visible=kept",
        ),
        (
            "/login?visible=kept&ID_TOKEN_HINT=SECRETTOKEN",
            "/login?visible=kept&ID_TOKEN_HINT=REDACTED",
        ),
    ],
)
def test_access_log_filter_redacts_the_id_token_hint(path: str, expected: str) -> None:
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
    assert f"GET {expected} HTTP/1.1" in rendered
    assert "SECRETSESSION" not in rendered


def test_identity_linking_rejects_missing_or_conflicting_candidates(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        session.add(
            User(
                name="Database User",
                email="user@example.com",
                role="consultant",
            )
        )
        session.commit()
        with pytest.raises(AuthenticationError):
            resolve_identity(
                session,
                NormalizedClaims(
                    issuer="https://issuer.test",
                    subject="unknown-subject",
                    email=None,
                    name=None,
                ),
            )
        user = session.scalar(select(User))
        assert user is not None
        session.add(
            UserIdentity(
                user_id=user.user_id,
                issuer="https://issuer.test",
                subject="existing-subject",
            )
        )
        session.commit()
        with pytest.raises(AuthenticationError):
            resolve_identity(
                session,
                NormalizedClaims(
                    issuer="https://issuer.test",
                    subject="different-subject",
                    email="user@example.com",
                    name=None,
                ),
            )
