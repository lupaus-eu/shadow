# pyright: reportPrivateUsage=false

import hashlib
import os
import threading
import uuid
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from urllib.parse import quote

import psycopg
import pytest
from psycopg import sql
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session, sessionmaker

import app.api.v1.auth.service as service_module
from app.api.v1.auth.service import (
    ConsumedLogin,
    LoginStart,
    consume_login,
    start_login,
)
from app.api.v1.users.models import OidcLoginTransaction
from app.core.config import Settings, get_sqlalchemy_database_url
from app.core.migrations import UpCommand, execute_command

TEST_DATABASE_ENV = "MIGRATION_TEST_DATABASE_URL"


@pytest.fixture
def auth_postgresql_session_factory() -> Generator[sessionmaker[Session], None, None]:
    base_url = os.getenv(TEST_DATABASE_ENV)
    if base_url is None:
        pytest.skip(f"{TEST_DATABASE_ENV} is not configured")

    schema_name = f"auth_test_{uuid.uuid4().hex}"
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


def test_callback_consumption_waits_for_browser_binding_transaction_lock(
    auth_postgresql_session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = "S" * 43
    browser_binding = "B" * 43
    state_hash = hashlib.sha256(state.encode()).digest()
    binding_hash = hashlib.sha256(browser_binding.encode()).digest()
    now = datetime.now(UTC)
    with auth_postgresql_session_factory() as session:
        session.add(
            OidcLoginTransaction(
                state_hash=state_hash,
                browser_binding_hash=binding_hash,
                nonce="N" * 43,
                pkce_verifier="P" * 64,
                return_to="/workspace",
                created_time=now,
                expires_time=now + timedelta(minutes=10),
            )
        )
        session.commit()

    blocker = auth_postgresql_session_factory()
    lock_key = int.from_bytes(binding_hash[:8], byteorder="big", signed=True)
    blocker.execute(
        text("SELECT pg_advisory_xact_lock(:lock_key)"), {"lock_key": lock_key}
    )

    lock_attempted = threading.Event()
    finished = threading.Event()
    results: list[ConsumedLogin | None] = []
    errors: list[BaseException] = []
    original_lock = service_module._lock_binding_transaction

    def observed_lock(session: Session, observed_hash: bytes) -> None:
        lock_attempted.set()
        original_lock(session, observed_hash)

    monkeypatch.setattr(service_module, "_lock_binding_transaction", observed_lock)

    def consume() -> None:
        try:
            with auth_postgresql_session_factory() as session:
                results.append(
                    consume_login(
                        session,
                        state=state,
                        browser_binding=browser_binding,
                    )
                )
        except BaseException as exc:  # pragma: no cover - asserted below
            errors.append(exc)
        finally:
            finished.set()

    thread = threading.Thread(target=consume)
    try:
        thread.start()
        assert lock_attempted.wait(timeout=2)
        assert not finished.wait(timeout=0.2)
    finally:
        blocker.rollback()
        blocker.close()
        thread.join(timeout=5)

    assert not thread.is_alive()
    assert errors == []
    assert len(results) == 1
    assert results[0] is not None
    assert results[0].return_to == "/workspace"
    with auth_postgresql_session_factory() as session:
        assert (
            session.scalar(select(func.count()).select_from(OidcLoginTransaction))
            == 0
        )


def test_expired_callback_and_new_login_use_consistent_lock_order(
    auth_postgresql_session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = "S" * 43
    browser_binding = "B" * 43
    state_hash = hashlib.sha256(state.encode()).digest()
    binding_hash = hashlib.sha256(browser_binding.encode()).digest()
    now = datetime.now(UTC)
    with auth_postgresql_session_factory() as session:
        session.add(
            OidcLoginTransaction(
                state_hash=state_hash,
                browser_binding_hash=binding_hash,
                nonce="N" * 43,
                pkce_verifier="P" * 64,
                return_to="/expired",
                created_time=now - timedelta(minutes=11),
                expires_time=now - timedelta(minutes=1),
            )
        )
        session.commit()

    callback_has_binding_lock = threading.Event()
    login_reached_binding_lock = threading.Event()
    callback_results: list[ConsumedLogin | None] = []
    login_results: list[LoginStart] = []
    errors: list[BaseException] = []
    original_lock = service_module._lock_binding_transaction

    def observed_lock(session: Session, observed_hash: bytes) -> None:
        if threading.current_thread().name == "expired-callback":
            original_lock(session, observed_hash)
            callback_has_binding_lock.set()
            if not login_reached_binding_lock.wait(timeout=5):
                raise RuntimeError("New login did not reach the binding lock")
            return
        if threading.current_thread().name == "new-login":
            login_reached_binding_lock.set()
        original_lock(session, observed_hash)

    monkeypatch.setattr(service_module, "_lock_binding_transaction", observed_lock)

    def consume_expired_callback() -> None:
        try:
            with auth_postgresql_session_factory() as session:
                callback_results.append(
                    consume_login(
                        session,
                        state=state,
                        browser_binding=browser_binding,
                    )
                )
        except BaseException as exc:  # pragma: no cover - asserted below
            errors.append(exc)

    def start_new_login() -> None:
        try:
            with auth_postgresql_session_factory() as session:
                login_results.append(
                    start_login(
                        session,
                        Settings(),
                        return_to="/workspace",
                        existing_browser_binding=browser_binding,
                        authorization_url_factory=_authorization_url,
                    )
                )
        except BaseException as exc:  # pragma: no cover - asserted below
            errors.append(exc)

    callback_thread = threading.Thread(
        target=consume_expired_callback,
        name="expired-callback",
    )
    login_thread = threading.Thread(target=start_new_login, name="new-login")
    callback_thread.start()
    assert callback_has_binding_lock.wait(timeout=2)
    login_thread.start()
    callback_thread.join(timeout=5)
    login_thread.join(timeout=5)

    assert not callback_thread.is_alive()
    assert not login_thread.is_alive()
    assert errors == []
    assert callback_results == [None]
    assert len(login_results) == 1
    assert login_results[0].browser_binding == browser_binding
    with auth_postgresql_session_factory() as session:
        transactions = session.scalars(select(OidcLoginTransaction)).all()
        assert len(transactions) == 1
        assert transactions[0].return_to == "/workspace"


def _authorization_url(*, state: str, nonce: str, pkce_verifier: str) -> str:
    del nonce, pkce_verifier
    return f"https://issuer.test/authorize?state={state}"
