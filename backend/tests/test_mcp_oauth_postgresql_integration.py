# pyright: reportPrivateUsage=false

import base64
import hashlib
import os
import threading
import time
import uuid
from collections.abc import Callable, Generator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qsl, quote, urlsplit

import psycopg
import pytest
from psycopg import sql
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session, sessionmaker

import app.api.v1.mcp_oauth.service as service_module
from app.api.v1.mcp_oauth.models import (
    McpOauthAuthorizationRequest,
    McpOauthClient,
    McpOauthGrant,
)
from app.api.v1.mcp_oauth.service import (
    OAuthError,
    cleanup_stale_clients,
    start_authorization,
)
from app.api.v1.users.models import User
from app.core.config import Settings, get_sqlalchemy_database_url
from app.core.migrations import UpCommand, execute_command

TEST_DATABASE_ENV = "MIGRATION_TEST_DATABASE_URL"
SETTINGS = Settings.model_validate({"MCP_ENABLED": True})
REDIRECT_URI = "http://127.0.0.1:33418/callback"
READ_RESOURCE = "http://testserver/api/mcp/read"
CHALLENGE = (
    base64.urlsafe_b64encode(hashlib.sha256(b"v" * 64).digest()).rstrip(b"=").decode()
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
