import os
import uuid
from collections.abc import Generator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import LiteralString
from urllib.parse import quote

import psycopg
import pytest
from psycopg import sql
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.api.v1.auth.provider import NormalizedClaims
from app.api.v1.auth.service import resolve_identity
from app.api.v1.users.models import AuthSession, User, UserIdentity
from app.bootstrap_admin import (
    AdminBootstrapRefused,
    AdminBootstrapResult,
    bootstrap_admin,
)
from app.core.config import Settings, get_sqlalchemy_database_url
from app.core.migrations import UpCommand, execute_command
from app.seed_reference_data import seed_reference_data

TEST_DATABASE_ENV = "MIGRATION_TEST_DATABASE_URL"


@contextmanager
def _temporary_schema(base_url: str) -> Generator[str, None, None]:
    schema_name = f"admin_bootstrap_test_{uuid.uuid4().hex}"
    with psycopg.connect(base_url, autocommit=True) as connection:
        connection.execute(
            sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema_name))
        )

    separator = "&" if "?" in base_url else "?"
    schema_url = f"{base_url}{separator}options={quote(f'-csearch_path={schema_name}')}"
    try:
        yield schema_url
    finally:
        with psycopg.connect(base_url, autocommit=True) as connection:
            connection.execute(
                sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema_name))
            )


@pytest.fixture
def migration_database_url() -> Generator[str, None, None]:
    base_url = os.getenv(TEST_DATABASE_ENV)
    if base_url is None:
        pytest.skip(f"{TEST_DATABASE_ENV} is not configured")
    with _temporary_schema(base_url) as database_url:
        yield database_url


def _user_rows(database_url: str) -> list[tuple[object, ...]]:
    with psycopg.connect(database_url) as connection:
        return connection.execute(
            """
            SELECT name, email, role, created_by, modified_by, deleted_by,
                   deleted_time
            FROM users
            ORDER BY user_id
            """
        ).fetchall()


def _scalar(database_url: str, query: LiteralString) -> object:
    with psycopg.connect(database_url) as connection:
        row = connection.execute(sql.SQL(query)).fetchone()
        assert row is not None
        return row[0]


def test_bootstrap_creates_one_trimmed_active_admin(
    migration_database_url: str,
) -> None:
    execute_command(UpCommand(), database_url=migration_database_url)

    result = bootstrap_admin(
        migration_database_url,
        name="  First Administrator  ",
        email="  first.admin@example.test  ",
    )

    assert result.user_id == 101
    assert _user_rows(migration_database_url) == [
        (
            "First Administrator",
            "first.admin@example.test",
            "admin",
            None,
            None,
            None,
            None,
        )
    ]
    assert _scalar(migration_database_url, "SELECT count(*) FROM user_identities") == 0
    assert _scalar(migration_database_url, "SELECT count(*) FROM auth_sessions") == 0


@pytest.mark.parametrize("deleted", [False, True])
def test_bootstrap_refuses_any_existing_user_without_mutation(
    migration_database_url: str,
    deleted: bool,
) -> None:
    execute_command(UpCommand(), database_url=migration_database_url)
    deleted_time = datetime.now(UTC) if deleted else None
    with psycopg.connect(migration_database_url) as connection:
        connection.execute(
            """
            INSERT INTO users (name, email, role, deleted_time)
            VALUES (%s, %s, 'consultant', %s)
            """,
            ("Existing", "existing@example.test", deleted_time),
        )
    before = _user_rows(migration_database_url)

    with pytest.raises(AdminBootstrapRefused):
        bootstrap_admin(
            migration_database_url,
            name="Administrator",
            email="admin@example.test",
        )

    assert _user_rows(migration_database_url) == before


def test_concurrent_bootstrap_attempts_create_only_one_admin(
    migration_database_url: str,
) -> None:
    execute_command(UpCommand(), database_url=migration_database_url)

    def attempt(index: int) -> AdminBootstrapResult | type[AdminBootstrapRefused]:
        try:
            return bootstrap_admin(
                migration_database_url,
                name=f"Administrator {index}",
                email=f"admin{index}@example.test",
            )
        except AdminBootstrapRefused:
            return AdminBootstrapRefused

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(attempt, range(2)))

    assert sum(isinstance(result, AdminBootstrapResult) for result in results) == 1
    assert results.count(AdminBootstrapRefused) == 1
    assert len(_user_rows(migration_database_url)) == 1


def test_bootstrap_waits_for_an_ordinary_user_writer_then_refuses(
    migration_database_url: str,
) -> None:
    execute_command(UpCommand(), database_url=migration_database_url)
    blocker = psycopg.connect(migration_database_url)
    blocker.execute(
        """
        INSERT INTO users (name, email, role)
        VALUES ('Concurrent User', 'concurrent@example.test', 'consultant')
        """
    )

    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(
                bootstrap_admin,
                migration_database_url,
                name="Administrator",
                email="admin@example.test",
            )
            with pytest.raises(TimeoutError):
                future.result(timeout=0.2)
            blocker.commit()
            with pytest.raises(AdminBootstrapRefused):
                future.result(timeout=5)
    finally:
        blocker.rollback()
        blocker.close()

    assert _user_rows(migration_database_url) == [
        (
            "Concurrent User",
            "concurrent@example.test",
            "consultant",
            None,
            None,
            None,
            None,
        )
    ]


def test_insert_failure_rolls_back_without_partial_user(
    migration_database_url: str,
) -> None:
    execute_command(UpCommand(), database_url=migration_database_url)
    with psycopg.connect(migration_database_url) as connection:
        connection.execute(
            """
            CREATE FUNCTION reject_bootstrap_insert() RETURNS trigger
            LANGUAGE plpgsql AS $$
            BEGIN
                RAISE EXCEPTION 'sensitive failure';
            END
            $$
            """
        )
        connection.execute(
            """
            CREATE TRIGGER reject_bootstrap_insert
            BEFORE INSERT ON users
            FOR EACH ROW EXECUTE FUNCTION reject_bootstrap_insert()
            """
        )

    with pytest.raises(psycopg.errors.RaiseException):
        bootstrap_admin(
            migration_database_url,
            name="Administrator",
            email="admin@example.test",
        )

    assert _user_rows(migration_database_url) == []


def test_reference_seed_then_bootstrap_supports_normal_first_link(
    migration_database_url: str,
) -> None:
    execute_command(UpCommand(), database_url=migration_database_url)
    assert seed_reference_data(migration_database_url).inserted is True
    result = bootstrap_admin(
        migration_database_url,
        name="Administrator",
        email="admin@example.test",
    )
    assert _scalar(migration_database_url, "SELECT count(*) FROM metamodels") == 1
    assert _scalar(migration_database_url, "SELECT count(*) FROM user_identities") == 0
    assert _scalar(migration_database_url, "SELECT count(*) FROM auth_sessions") == 0

    settings = Settings(DATABASE_URL=migration_database_url)
    engine = create_engine(get_sqlalchemy_database_url(settings))
    try:
        with Session(engine) as session:
            linked_user = resolve_identity(
                session,
                NormalizedClaims(
                    issuer="https://test-provider.example/tenant/v2.0",
                    subject="test-provider-subject",
                    email="admin@example.test",
                    name="Provider Name Is Not Persisted",
                ),
            )
            assert linked_user.user_id == result.user_id
            assert linked_user.role == "admin"
            assert session.scalar(select(func.count()).select_from(User)) == 1
            assert session.scalar(select(func.count()).select_from(UserIdentity)) == 1
            assert session.scalar(select(func.count()).select_from(AuthSession)) == 0
    finally:
        engine.dispose()


def test_unmigrated_database_fails_without_creating_user_table(
    migration_database_url: str,
) -> None:
    with pytest.raises(psycopg.errors.UndefinedTable):
        bootstrap_admin(
            migration_database_url,
            name="Administrator",
            email="admin@example.test",
        )

    assert (
        _scalar(migration_database_url, "SELECT to_regclass('users') IS NULL")
        is True
    )
