# pyright: reportPrivateUsage=false

import base64
import hashlib
import logging
import os
import threading
import time
import uuid
from collections.abc import Callable, Generator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import parse_qsl, quote, urlsplit

import psycopg
import pytest
from psycopg import sql
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session, sessionmaker

import app.api.v1.mcp_oauth.service as service_module
import app.api.v1.mcp_oauth.token_service as token_service_module
from app.api.v1.mcp_oauth.models import (
    McpOauthAuthorizationRequest,
    McpOauthClient,
    McpOauthGrant,
    McpOauthToken,
)
from app.api.v1.mcp_oauth.service import (
    OAuthError,
    approve_consent,
    cleanup_stale_clients,
    start_authorization,
)
from app.api.v1.mcp_oauth.token_service import (
    IssuedTokens,
    issue_tokens,
    verify_access_token,
)
from app.api.v1.users.models import User
from app.core.config import Settings, get_sqlalchemy_database_url
from app.core.migrations import UpCommand, execute_command

TEST_DATABASE_ENV = "MIGRATION_TEST_DATABASE_URL"
TOKEN_LOGGER = "app.api.v1.mcp_oauth.token_service"
REDIRECT_URI = "http://127.0.0.1:33418/callback"
SETTINGS = Settings.model_validate(
    {"MCP_ENABLED": True, "MCP_OAUTH_REDIRECT_URIS": "http://127.0.0.1:{port}/callback"}
)
READ_RESOURCE = "http://testserver/api/mcp/read"
VERIFIER = "v" * 64
CHALLENGE = (
    base64.urlsafe_b64encode(hashlib.sha256(VERIFIER.encode()).digest())
    .rstrip(b"=")
    .decode()
)


@pytest.fixture
def mcp_postgresql_session_factory() -> Generator[sessionmaker[Session], None, None]:
    base_url = os.getenv(TEST_DATABASE_ENV)
    if base_url is None:
        pytest.skip(f"{TEST_DATABASE_ENV} is not configured")

    schema_name = f"mcp_oauth_test_{uuid.uuid4().hex}"
    with psycopg.connect(base_url, autocommit=True) as connection:
        connection.execute(
            sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema_name))
        )

    separator = "&" if "?" in base_url else "?"
    schema_url = f"{base_url}{separator}options={quote(f'-csearch_path={schema_name}')}"
    execute_command(UpCommand(), database_url=schema_url)
    settings = Settings(DATABASE_URL=schema_url)
    engine = create_engine(get_sqlalchemy_database_url(settings))
    factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    try:
        yield factory
    finally:
        engine.dispose()
        with psycopg.connect(base_url, autocommit=True) as connection:
            connection.execute(
                sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema_name))
            )


def _add_client(
    factory: sessionmaker[Session],
    client_id: str,
    *,
    age: timedelta = timedelta(),
    deleted: bool = False,
) -> None:
    now = datetime.now(UTC)
    with factory() as session:
        session.add(
            McpOauthClient(
                client_id=client_id,
                client_name="Locked Client",
                redirect_uris=[REDIRECT_URI],
                created_time=now - age,
                deleted_time=now if deleted else None,
            )
        )
        session.commit()


def _authorize_query(client_id: str) -> dict[str, list[str]]:
    return {
        "response_type": ["code"],
        "client_id": [client_id],
        "redirect_uri": [REDIRECT_URI],
        "code_challenge": [CHALLENGE],
        "code_challenge_method": ["S256"],
        "resource": [READ_RESOURCE],
    }


def _with_lock_timeout(session: Session) -> Session:
    # Fail instead of hanging if a statement unexpectedly waits for a lock.
    session.execute(text("SET lock_timeout = '2s'"))
    return session


def _wait_for_lock_waiter(factory: sessionmaker[Session]) -> None:
    deadline = time.monotonic() + 5
    with factory() as session:
        while time.monotonic() < deadline:
            waiting = session.scalar(
                text("SELECT count(*) FROM pg_locks WHERE NOT granted")
            )
            session.rollback()
            if waiting:
                return
            time.sleep(0.05)
    raise AssertionError("authorize never waited for a lock")


@contextmanager
def _authorize_in_thread(
    factory: sessionmaker[Session], client_id: str, settings: Settings = SETTINGS
) -> Generator[Callable[[], str | BaseException], None, None]:
    finished = threading.Event()
    outcome: list[str | BaseException] = []

    def run() -> None:
        try:
            with factory() as session:
                outcome.append(
                    start_authorization(session, settings, _authorize_query(client_id))
                )
        except BaseException as exc:  # pragma: no cover - asserted by callers
            outcome.append(exc)
        finally:
            finished.set()

    thread = threading.Thread(target=run)
    thread.start()

    def result() -> str | BaseException:
        thread.join(timeout=5)
        assert not thread.is_alive()
        assert len(outcome) == 1
        return outcome[0]

    try:
        yield result
    finally:
        thread.join(timeout=5)


def _add_user(factory: sessionmaker[Session], email: str) -> int:
    with factory() as session:
        user = User(name="Token User", email=email, role="consultant")
        session.add(user)
        session.commit()
        return user.user_id


def _approved_code(factory: sessionmaker[Session], client_id: str, user_id: int) -> str:
    with factory() as session:
        location = start_authorization(session, SETTINGS, _authorize_query(client_id))
    with factory() as session:
        redirect_url = approve_consent(
            session,
            SETTINGS,
            dict(parse_qsl(urlsplit(location).query))["request"],
            user_id=user_id,
        )
    return dict(parse_qsl(urlsplit(redirect_url).query))["code"]


def _exchange_parameters(client_id: str, code: str) -> dict[str, list[str]]:
    return {
        "grant_type": ["authorization_code"],
        "code": [code],
        "client_id": [client_id],
        "redirect_uri": [REDIRECT_URI],
        "code_verifier": [VERIFIER],
        "resource": [READ_RESOURCE],
    }


def _refresh_parameters(client_id: str, refresh_token: str) -> dict[str, list[str]]:
    return {
        "grant_type": ["refresh_token"],
        "refresh_token": [refresh_token],
        "client_id": [client_id],
        "resource": [READ_RESOURCE],
    }


@contextmanager
def _token_request_in_thread(
    factory: sessionmaker[Session], parameters: dict[str, list[str]]
) -> Generator[tuple[threading.Event, Callable[[], object]], None, None]:
    finished = threading.Event()
    outcome: list[object] = []

    def run() -> None:
        try:
            with factory() as session:
                outcome.append(issue_tokens(session, SETTINGS, parameters))
        except BaseException as exc:  # pragma: no cover - asserted by callers
            outcome.append(exc)
        finally:
            finished.set()

    thread = threading.Thread(target=run)
    thread.start()

    def result() -> object:
        thread.join(timeout=5)
        assert not thread.is_alive()
        assert len(outcome) == 1
        return outcome[0]

    try:
        yield finished, result
    finally:
        thread.join(timeout=5)


@contextmanager
def _paused_first_call(
    monkeypatch: pytest.MonkeyPatch, module: object, name: str
) -> Generator[tuple[threading.Event, threading.Event], None, None]:
    """Pause the first call of `module.name` after it returns, keeping its locks."""
    reached = threading.Event()
    release = threading.Event()
    original = getattr(module, name)

    def paused(*args: Any, **kwargs: Any) -> Any:
        result = original(*args, **kwargs)
        if not reached.is_set():
            reached.set()
            if not release.wait(timeout=5):
                raise RuntimeError("The test did not release the paused call")
        return result

    monkeypatch.setattr(module, name, paused)
    try:
        yield reached, release
    finally:
        release.set()


@contextmanager
def _paused_after_client_lock(
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[tuple[threading.Event, threading.Event], None, None]:
    """Pause authorize after it has locked the client row."""
    locked = threading.Event()
    release = threading.Event()
    original = service_module._registered_redirect_target

    def paused(
        settings: Settings, client: McpOauthClient, redirect_uri: str
    ) -> service_module.RedirectTarget | None:
        locked.set()
        if not release.wait(timeout=5):
            raise RuntimeError("The test did not release the paused authorize")
        return original(settings, client, redirect_uri)

    monkeypatch.setattr(service_module, "_registered_redirect_target", paused)
    try:
        yield locked, release
    finally:
        release.set()


@contextmanager
def _paused_after_pending_caps(
    monkeypatch: pytest.MonkeyPatch, client_id: str
) -> Generator[tuple[threading.Event, threading.Event], None, None]:
    """Pause one client's authorize after its pending caps passed, before commit."""
    checked = threading.Event()
    release = threading.Event()
    original = service_module._enforce_pending_request_caps

    def paused(
        session: Session, settings: Settings, client: McpOauthClient, now: datetime
    ) -> None:
        original(session, settings, client, now)
        if client.client_id == client_id:
            checked.set()
            if not release.wait(timeout=5):
                raise RuntimeError("The test did not release the paused authorize")

    monkeypatch.setattr(service_module, "_enforce_pending_request_caps", paused)
    try:
        yield checked, release
    finally:
        release.set()


def test_cleanup_skips_a_client_locked_by_an_inflight_authorize(
    mcp_postgresql_session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    factory = mcp_postgresql_session_factory
    _add_client(factory, "held", age=timedelta(days=45))
    _add_client(factory, "unlocked-stale", age=timedelta(days=45))

    with (
        _paused_after_client_lock(monkeypatch) as (locked, release),
        _authorize_in_thread(factory, "held") as result,
    ):
        assert locked.wait(timeout=5)
        with factory() as session:
            started = time.monotonic()
            cleanup_stale_clients(_with_lock_timeout(session), now=datetime.now(UTC))
            assert time.monotonic() - started < 1.5
        with factory() as session:
            remaining = {
                row.client_id: row.deleted_time
                for row in session.scalars(select(McpOauthClient))
            }
        # The locked client was skipped, not soft-deleted; the other stale
        # client was soft-deleted and, unreferenced, hard-deleted.
        assert remaining == {"held": None}
        release.set()
        location = result()

    assert isinstance(location, str)
    assert "/ai/authorize?request=" in location
    with factory() as session:
        held = session.scalar(select(McpOauthClient))
        assert held is not None
        assert held.last_used_time is not None
        assert (
            session.scalar(
                select(func.count()).select_from(McpOauthAuthorizationRequest)
            )
            == 1
        )
        cleanup_stale_clients(session, now=datetime.now(UTC))
        session.refresh(held)
        assert held.deleted_time is None


def test_grant_insert_for_the_same_client_does_not_wait_for_authorize(
    mcp_postgresql_session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    factory = mcp_postgresql_session_factory
    _add_client(factory, "shared")
    with factory() as session:
        user = User(name="Grant User", email="grant@example.test", role="consultant")
        session.add(user)
        session.commit()
        user_id = user.user_id
        client_row_id = session.scalar(select(McpOauthClient.mcp_oauth_client_id))
        assert client_row_id is not None

    with (
        _paused_after_client_lock(monkeypatch) as (locked, release),
        _authorize_in_thread(factory, "shared") as result,
    ):
        assert locked.wait(timeout=5)
        now = datetime.now(UTC)
        with factory() as session:
            started = time.monotonic()
            session = _with_lock_timeout(session)
            session.add(
                McpOauthGrant(
                    grant_key="raw-grant",
                    mcp_oauth_client_id=client_row_id,
                    user_id=user_id,
                    scopes="schatten.read",
                    resource=READ_RESOURCE,
                    created_time=now,
                    expires_time=now + timedelta(days=30),
                )
            )
            session.commit()
            assert time.monotonic() - started < 1.5
        release.set()
        location = result()

    assert isinstance(location, str)
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(McpOauthGrant)) == 1


def test_authorize_for_an_already_soft_deleted_client_stores_nothing(
    mcp_postgresql_session_factory: sessionmaker[Session],
) -> None:
    factory = mcp_postgresql_session_factory
    _add_client(factory, "deleted", age=timedelta(days=45), deleted=True)

    with factory() as session:
        with pytest.raises(OAuthError) as raised:
            start_authorization(session, SETTINGS, _authorize_query("deleted"))

    assert raised.value.error == "invalid_client"
    with factory() as session:
        assert session.scalar(select(McpOauthAuthorizationRequest)) is None
        deleted = session.scalar(select(McpOauthClient))
        assert deleted is not None
        assert deleted.last_used_time is None


def test_authorize_waiting_on_a_cleanup_soft_delete_fails_as_invalid_client(
    mcp_postgresql_session_factory: sessionmaker[Session],
) -> None:
    factory = mcp_postgresql_session_factory
    _add_client(factory, "being-cleaned", age=timedelta(days=45))
    cleanup = factory()
    stale = cleanup.scalar(select(McpOauthClient).with_for_update(skip_locked=True))
    assert stale is not None
    stale.deleted_time = datetime.now(UTC)
    cleanup.flush()

    try:
        with _authorize_in_thread(factory, "being-cleaned") as result:
            _wait_for_lock_waiter(factory)
            cleanup.commit()
            outcome = result()
    finally:
        cleanup.close()

    assert isinstance(outcome, OAuthError)
    assert outcome.error == "invalid_client"
    with factory() as session:
        assert session.scalar(select(McpOauthAuthorizationRequest)) is None


def test_total_pending_cap_serialises_authorizes_for_different_clients(
    mcp_postgresql_session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    factory = mcp_postgresql_session_factory
    settings = Settings.model_validate(
        {
            "MCP_ENABLED": True,
            "MCP_OAUTH_REDIRECT_URIS": "http://127.0.0.1:{port}/callback",
            "MCP_OAUTH_MAX_PENDING_REQUESTS_PER_CLIENT": 1,
            "MCP_OAUTH_MAX_PENDING_REQUESTS": 1,
        }
    )
    _add_client(factory, "first")
    _add_client(factory, "second")

    with (
        _paused_after_pending_caps(monkeypatch, "first") as (checked, release),
        _authorize_in_thread(factory, "first", settings) as first,
    ):
        assert checked.wait(timeout=5)
        with _authorize_in_thread(factory, "second", settings) as second:
            # The second client's total count waits for the first authorize.
            _wait_for_lock_waiter(factory)
            release.set()
            first_location = first()
            second_location = second()

    assert isinstance(first_location, str)
    assert "/ai/authorize?request=" in first_location
    assert isinstance(second_location, str)
    assert parse_qsl(urlsplit(second_location).query) == [
        ("error", "temporarily_unavailable"),
        ("iss", "http://testserver"),
    ]
    with factory() as session:
        assert (
            session.scalar(
                select(func.count()).select_from(McpOauthAuthorizationRequest)
            )
            == 1
        )


def test_authorize_rejects_nul_client_id_and_state_before_postgresql(
    mcp_postgresql_session_factory: sessionmaker[Session],
) -> None:
    factory = mcp_postgresql_session_factory
    _add_client(factory, "nul-client")
    nul_state = _authorize_query("nul-client")
    nul_state["state"] = ["client\x00state"]

    with factory() as session:
        with pytest.raises(OAuthError) as raised:
            start_authorization(session, SETTINGS, _authorize_query("nul\x00client"))
    with factory() as session:
        location = start_authorization(session, SETTINGS, nul_state)

    assert raised.value.error == "invalid_client"
    assert parse_qsl(urlsplit(location).query) == [
        ("error", "invalid_request"),
        ("iss", "http://testserver"),
    ]
    with factory() as session:
        assert session.scalar(select(McpOauthAuthorizationRequest)) is None
        stored = session.scalar(select(McpOauthClient))
        assert stored is not None
        assert stored.last_used_time is None


def test_token_client_update_waits_for_authorize_but_the_grant_insert_does_not(
    mcp_postgresql_session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    factory = mcp_postgresql_session_factory
    _add_client(factory, "shared")
    with factory() as session:
        user = User(name="Token User", email="token@example.test", role="consultant")
        session.add(user)
        session.commit()
        user_id = user.user_id
    with factory() as session:
        location = start_authorization(session, SETTINGS, _authorize_query("shared"))
    request_id = dict(parse_qsl(urlsplit(location).query))["request"]
    with factory() as session:
        redirect_url = approve_consent(session, SETTINGS, request_id, user_id=user_id)
    code = dict(parse_qsl(urlsplit(redirect_url).query))["code"]
    with factory() as session:
        stored = session.scalar(select(McpOauthClient))
        assert stored is not None
        # Old enough that the throttled token-time update must write it.
        stored.last_used_time = datetime.now(UTC) - timedelta(minutes=10)
        session.commit()

    rows_inserted = threading.Event()
    original_touch = token_service_module._touch_client

    def observed_touch(session: Session, client: McpOauthClient, now: datetime) -> None:
        # The grant and token rows have been inserted (flushed) by now.
        rows_inserted.set()
        original_touch(session, client, now)

    monkeypatch.setattr(token_service_module, "_touch_client", observed_touch)

    with (
        _paused_after_client_lock(monkeypatch) as (locked, release),
        _authorize_in_thread(factory, "shared") as authorize_result,
    ):
        assert locked.wait(timeout=5)
        with _token_request_in_thread(
            factory, _exchange_parameters("shared", code)
        ) as (finished, exchange_result):
            # The grant insert's key-share lock on the client does not conflict
            # with authorize's FOR NO KEY UPDATE, so it completes at once ...
            assert rows_inserted.wait(timeout=5)
            # ... while the client's last_used_time update waits for authorize.
            _wait_for_lock_waiter(factory)
            assert not finished.is_set()
            release.set()
            authorize_location = authorize_result()
            issued = exchange_result()

    assert isinstance(authorize_location, str)
    assert "/ai/authorize?request=" in authorize_location
    assert isinstance(issued, IssuedTokens)
    with factory() as session:
        grant = session.scalar(select(McpOauthGrant))
        assert grant is not None
        assert grant.user_id == user_id
        assert session.scalar(select(func.count()).select_from(McpOauthToken)) == 2
        stored = session.scalar(select(McpOauthClient))
        assert stored is not None and stored.last_used_time is not None
        assert datetime.now(UTC) - stored.last_used_time < timedelta(minutes=1)
        assert (
            session.scalar(
                select(func.count()).select_from(McpOauthAuthorizationRequest)
            )
            == 2
        )


def test_token_lifecycle_and_cleanup_cascade_on_postgresql(
    mcp_postgresql_session_factory: sessionmaker[Session],
) -> None:
    factory = mcp_postgresql_session_factory
    _add_client(factory, "lifecycle")
    with factory() as session:
        user = User(name="Life User", email="life@example.test", role="admin")
        session.add(user)
        session.commit()
        user_id = user.user_id
    with factory() as session:
        location = start_authorization(session, SETTINGS, _authorize_query("lifecycle"))
    with factory() as session:
        redirect_url = approve_consent(
            session,
            SETTINGS,
            dict(parse_qsl(urlsplit(location).query))["request"],
            user_id=user_id,
        )
    code = dict(parse_qsl(urlsplit(redirect_url).query))["code"]

    def token_request(**parameters: str) -> IssuedTokens:
        with factory() as session:
            return issue_tokens(
                session,
                SETTINGS,
                {
                    "client_id": ["lifecycle"],
                    "resource": [READ_RESOURCE],
                    **{name: [value] for name, value in parameters.items()},
                },
            )

    issued = token_request(
        grant_type="authorization_code",
        code=code,
        redirect_uri=REDIRECT_URI,
        code_verifier=VERIFIER,
    )
    with factory() as session:
        principal = verify_access_token(
            session, issued.access_token, READ_RESOURCE, "schatten.read"
        )
    assert (principal.user_id, principal.role) == (user_id, "admin")
    rotated = token_request(
        grant_type="refresh_token", refresh_token=issued.refresh_token
    )

    with pytest.raises(OAuthError) as replayed:
        token_request(grant_type="refresh_token", refresh_token=issued.refresh_token)

    assert replayed.value.error == "invalid_grant"
    with factory() as session:
        grant = session.scalar(select(McpOauthGrant))
        assert grant is not None and grant.revoked_time is not None
        assert (
            session.scalar(
                select(func.count())
                .select_from(McpOauthToken)
                .where(McpOauthToken.revoked_time.is_(None))
            )
            == 0
        )

    # The next token request's cleanup deletes the revoked grant; PostgreSQL
    # cascades its tokens and sets the consumed request's grant_id to null.
    with pytest.raises(OAuthError):
        token_request(grant_type="refresh_token", refresh_token=rotated.refresh_token)
    with factory() as session:
        assert session.scalar(select(McpOauthGrant)) is None
        assert session.scalar(select(McpOauthToken)) is None
        pending = session.scalar(select(McpOauthAuthorizationRequest))
        assert pending is not None
        assert pending.consumed_time is not None
        assert pending.grant_id is None


def _token_hash(raw: str) -> bytes:
    return hashlib.sha256(raw.encode()).digest()


def test_concurrent_cleanups_do_not_deadlock(
    mcp_postgresql_session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    factory = mcp_postgresql_session_factory
    now = datetime.now(UTC)
    _add_client(factory, "cleanup")
    user_id = _add_user(factory, "cleanup@example.test")
    with factory() as session:
        client_row_id = session.scalar(select(McpOauthClient.mcp_oauth_client_id))
        assert client_row_id is not None
        revoked = McpOauthGrant(
            grant_key="revoked",
            mcp_oauth_client_id=client_row_id,
            user_id=user_id,
            scopes="schatten.read",
            resource=READ_RESOURCE,
            created_time=now - timedelta(days=1),
            expires_time=now + timedelta(days=29),
            revoked_time=now - timedelta(seconds=1),
        )
        expiring = McpOauthGrant(
            grant_key="expiring",
            mcp_oauth_client_id=client_row_id,
            user_id=user_id,
            scopes="schatten.read",
            resource=READ_RESOURCE,
            created_time=now - timedelta(days=30),
            expires_time=now + timedelta(seconds=5),
        )
        session.add_all([revoked, expiring])
        session.flush()
        session.add_all(
            [
                # Expires between the two cleanups' times.
                McpOauthToken(
                    token_hash=_token_hash("revoked-access"),
                    grant_id=revoked.grant_id,
                    kind="access",
                    created_time=now - timedelta(minutes=55),
                    expires_time=now + timedelta(seconds=5),
                ),
                McpOauthToken(
                    token_hash=_token_hash("expiring-access"),
                    grant_id=expiring.grant_id,
                    kind="access",
                    created_time=now - timedelta(hours=2),
                    expires_time=now - timedelta(hours=1),
                ),
            ]
        )
        session.commit()

    # Each cleanup locks one grant and then waits for the other at its grant
    # deletion. Before the steps committed separately, each still held the
    # other grant's expired access token from its own access-token step, and
    # the cascades deadlocked.
    original_delete = token_service_module.delete
    at_grant_deletion = threading.Barrier(2, timeout=10)
    first_ready = threading.Event()

    def delete_after_barrier(entity: Any) -> Any:
        if entity is McpOauthGrant:
            if threading.current_thread().name == "first":
                first_ready.set()
            at_grant_deletion.wait()
        return original_delete(entity)

    monkeypatch.setattr(token_service_module, "delete", delete_after_barrier)
    outcome: dict[str, object] = {}

    def run(cleanup_now: datetime) -> None:
        try:
            with factory() as session:
                token_service_module.cleanup_expired_oauth_rows(
                    session, now=cleanup_now
                )
            outcome[threading.current_thread().name] = "ok"
        except BaseException as exc:  # pragma: no cover - asserted below
            outcome[threading.current_thread().name] = exc

    first = threading.Thread(target=run, args=(now,), name="first")
    first.start()
    assert first_ready.wait(timeout=5)
    second = threading.Thread(
        target=run, args=(now + timedelta(seconds=10),), name="second"
    )
    second.start()
    first.join(timeout=10)
    second.join(timeout=10)

    assert outcome == {"first": "ok", "second": "ok"}
    with factory() as session:
        assert session.scalar(select(McpOauthGrant)) is None
        assert session.scalar(select(McpOauthToken)) is None


def test_cleanup_skips_a_grant_deletion_that_would_wait(
    mcp_postgresql_session_factory: sessionmaker[Session],
    caplog: pytest.LogCaptureFixture,
) -> None:
    factory = mcp_postgresql_session_factory
    now = datetime.now(UTC)
    _add_client(factory, "busy")
    user_id = _add_user(factory, "busy@example.test")
    with factory() as session:
        client_row_id = session.scalar(select(McpOauthClient.mcp_oauth_client_id))
        assert client_row_id is not None
        grant = McpOauthGrant(
            grant_key="revoked",
            mcp_oauth_client_id=client_row_id,
            user_id=user_id,
            scopes="schatten.read",
            resource=READ_RESOURCE,
            created_time=now - timedelta(days=1),
            expires_time=now + timedelta(days=29),
            revoked_time=now,
        )
        session.add(grant)
        session.flush()
        session.add(
            McpOauthToken(
                token_hash=_token_hash("held-refresh"),
                grant_id=grant.grant_id,
                kind="refresh",
                created_time=now,
                expires_time=now + timedelta(days=7),
            )
        )
        session.commit()

    holder = factory()
    held = holder.scalar(select(McpOauthToken).with_for_update())
    assert held is not None
    try:
        with factory() as session:
            started = time.monotonic()
            cleanup_service = token_service_module.cleanup_expired_oauth_rows
            with caplog.at_level(logging.WARNING, logger=TOKEN_LOGGER):
                cleanup_service(session, now=datetime.now(UTC))
            # The cascade gave way after the short lock_timeout, well before
            # the 2 s that a wait for the holder would otherwise take.
            assert time.monotonic() - started < 2
        with factory() as session:
            assert session.scalar(select(McpOauthGrant)) is not None
        assert any(
            "_delete_inactive_grants skipped after a lock conflict"
            in record.getMessage()
            for record in caplog.records
        )
    finally:
        holder.rollback()
        holder.close()

    with factory() as session:
        token_service_module.cleanup_expired_oauth_rows(session, now=datetime.now(UTC))
    with factory() as session:
        assert session.scalar(select(McpOauthGrant)) is None
        assert session.scalar(select(McpOauthToken)) is None


def test_concurrent_first_exchanges_share_one_grant(
    mcp_postgresql_session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    factory = mcp_postgresql_session_factory
    _add_client(factory, "pair")
    user_id = _add_user(factory, "pair@example.test")
    first_code = _approved_code(factory, "pair", user_id)
    second_code = _approved_code(factory, "pair", user_id)

    with _paused_first_call(monkeypatch, token_service_module, "_reusable_grant") as (
        reached,
        release,
    ):
        with _token_request_in_thread(
            factory, _exchange_parameters("pair", first_code)
        ) as (_, first_result):
            assert reached.wait(timeout=5)
            with _token_request_in_thread(
                factory, _exchange_parameters("pair", second_code)
            ) as (second_finished, second_result):
                # The second exchange waits on the advisory lock per client,
                # User and resource instead of creating its own grant.
                _wait_for_lock_waiter(factory)
                assert not second_finished.is_set()
                release.set()
                first = first_result()
                second = second_result()

    assert isinstance(first, IssuedTokens)
    assert isinstance(second, IssuedTokens)
    with factory() as session:
        grants = session.scalars(select(McpOauthGrant)).all()
        assert len(grants) == 1
        assert grants[0].revoked_time is None
        tokens = {
            token.token_hash: token for token in session.scalars(select(McpOauthToken))
        }
        for raw in (first.access_token, first.refresh_token):
            assert tokens[_token_hash(raw)].revoked_time is not None
        for raw in (second.access_token, second.refresh_token):
            assert tokens[_token_hash(raw)].revoked_time is None


def test_concurrent_double_redemption_revokes_the_grant(
    mcp_postgresql_session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    factory = mcp_postgresql_session_factory
    _add_client(factory, "twice")
    user_id = _add_user(factory, "twice@example.test")
    code = _approved_code(factory, "twice", user_id)

    with _paused_first_call(monkeypatch, token_service_module, "_issue_token_pair") as (
        reached,
        release,
    ):
        with _token_request_in_thread(factory, _exchange_parameters("twice", code)) as (
            _,
            first_result,
        ):
            assert reached.wait(timeout=5)
            with _token_request_in_thread(
                factory, _exchange_parameters("twice", code)
            ) as (second_finished, second_result):
                # The second redemption waits for the request row lock.
                _wait_for_lock_waiter(factory)
                assert not second_finished.is_set()
                release.set()
                first = first_result()
                second = second_result()

    assert isinstance(first, IssuedTokens)
    assert isinstance(second, OAuthError)
    assert second.error == "invalid_grant"
    with factory() as session:
        grant = session.scalar(select(McpOauthGrant))
        assert grant is not None and grant.revoked_time is not None
        assert all(
            token.revoked_time is not None
            for token in session.scalars(select(McpOauthToken))
        )


def test_concurrent_refresh_with_one_token_revokes_the_grant(
    mcp_postgresql_session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    factory = mcp_postgresql_session_factory
    _add_client(factory, "racing")
    user_id = _add_user(factory, "racing@example.test")
    with factory() as session:
        issued = issue_tokens(
            session,
            SETTINGS,
            _exchange_parameters("racing", _approved_code(factory, "racing", user_id)),
        )

    with _paused_first_call(monkeypatch, token_service_module, "_issue_token_pair") as (
        reached,
        release,
    ):
        with _token_request_in_thread(
            factory, _refresh_parameters("racing", issued.refresh_token)
        ) as (_, first_result):
            assert reached.wait(timeout=5)
            with _token_request_in_thread(
                factory, _refresh_parameters("racing", issued.refresh_token)
            ) as (second_finished, second_result):
                # The second refresh waits for the grant lock, then sees the
                # token already replaced.
                _wait_for_lock_waiter(factory)
                assert not second_finished.is_set()
                release.set()
                first = first_result()
                second = second_result()

    assert isinstance(first, IssuedTokens)
    assert isinstance(second, OAuthError)
    assert second.error == "invalid_grant"
    with factory() as session:
        grant = session.scalar(select(McpOauthGrant))
        assert grant is not None and grant.revoked_time is not None
