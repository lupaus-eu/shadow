from __future__ import annotations

import os
import shutil
import threading
import uuid
from collections.abc import Generator
from pathlib import Path
from typing import LiteralString, cast
from urllib.parse import quote

import psycopg
import pytest
from psycopg import sql

from app.core.migrations import (
    CREATE_HISTORY_SQL,
    BaselineCommand,
    DownCommand,
    MigrationError,
    UpCommand,
    discover_migrations,
    execute_command,
)

TEST_DATABASE_ENV = "MIGRATION_TEST_DATABASE_URL"


@pytest.fixture
def migration_database_url() -> Generator[str, None, None]:
    base_url = os.getenv(TEST_DATABASE_ENV)
    if base_url is None:
        pytest.skip(f"{TEST_DATABASE_ENV} is not configured")

    schema_name = f"migration_test_{uuid.uuid4().hex}"
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


def _scalar(database_url: str, query: str) -> object:
    with psycopg.connect(database_url) as connection:
        row = connection.execute(sql.SQL(cast(LiteralString, query))).fetchone()
    assert row is not None
    return row[0]


def _rollback_to_version_four(database_url: str) -> None:
    for migration in reversed(discover_migrations()[4:]):
        execute_command(DownCommand(migration.down_name), database_url=database_url)


def _insert_graph_fixture(database_url: str, *, org_state_count: int) -> None:
    with psycopg.connect(database_url) as connection:
        connection.execute(
            "INSERT INTO users (name, role) VALUES ('Migration Tester', 'admin')"
        )
        connection.execute(
            """
            INSERT INTO organisations (organisation_key, name, created_by)
            VALUES ('migration-org', 'Migration Org', 101)
            """
        )
        connection.execute(
            """
            INSERT INTO scenarios (
                organisation_id, scenario_key, name, created_by
            )
            VALUES (101, 'migration-scenario', 'Migration Scenario', 101)
            """
        )
        for index in range(org_state_count):
            connection.execute(
                """
                INSERT INTO org_states (
                    scenario_id, org_state_key, name, target_date, created_by
                )
                VALUES (101, %s, %s, DATE '2026-01-01', 101)
                """,
                (f"state-{index}", f"State {index}"),
            )
        connection.execute(
            "INSERT INTO metamodels (version, created_by) VALUES (1, 101)"
        )
        connection.execute(
            """
            INSERT INTO node_types (
                metamodel_id, node_type_key, name, display_name, created_by
            )
            VALUES (101, 'unit', 'Unit', 'Unit', 101)
            """
        )
        connection.execute(
            """
            INSERT INTO graph_nodes (
                scenario_id, node_key, name, node_type_id, create_date, created_by
            )
            VALUES (101, 'node-1', 'Node 1', 101, DATE '2026-01-01', 101)
            """
        )


def test_full_up_down_and_reapply_lifecycle(migration_database_url: str) -> None:
    execute_command(UpCommand(), database_url=migration_database_url)

    assert (
        _scalar(migration_database_url, "SELECT count(*) FROM schema_migrations")
        == 8
    )
    assert _scalar(
        migration_database_url,
        "SELECT to_regclass('customer_addresses') IS NOT NULL",
    )

    execute_command(UpCommand(), database_url=migration_database_url)

    for migration in reversed(discover_migrations()):
        execute_command(
            DownCommand(migration.down_name), database_url=migration_database_url
        )

    assert (
        _scalar(migration_database_url, "SELECT count(*) FROM schema_migrations")
        == 0
    )
    assert not _scalar(
        migration_database_url, "SELECT to_regclass('users') IS NOT NULL"
    )

    execute_command(UpCommand(), database_url=migration_database_url)
    assert (
        _scalar(migration_database_url, "SELECT count(*) FROM schema_migrations")
        == 8
    )


def test_rejects_non_latest_and_unapplied_down_migrations(
    migration_database_url: str,
) -> None:
    execute_command(UpCommand(), database_url=migration_database_url)

    with pytest.raises(MigrationError, match="Unknown down migration"):
        execute_command(
            DownCommand("009_unknown.down.sql"),
            database_url=migration_database_url,
        )

    with pytest.raises(MigrationError, match="not the latest applied"):
        execute_command(
            DownCommand("007_create_contacts.down.sql"),
            database_url=migration_database_url,
        )

    execute_command(
        DownCommand("008_create_customer_addresses.down.sql"),
        database_url=migration_database_url,
    )
    with pytest.raises(MigrationError, match="not the latest applied"):
        execute_command(
            DownCommand("008_create_customer_addresses.down.sql"),
            database_url=migration_database_url,
        )


def test_detects_checksum_drift(
    migration_database_url: str, tmp_path: Path
) -> None:
    migration_copy = tmp_path / "migrations"
    shutil.copytree(discover_migrations()[0].up_path.parent, migration_copy)
    execute_command(
        UpCommand(),
        database_url=migration_database_url,
        migrations_directory=migration_copy,
    )
    changed = migration_copy / "001_create_core_schema.sql"
    changed.write_text(changed.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    with pytest.raises(MigrationError, match="checksum drift"):
        execute_command(
            UpCommand(),
            database_url=migration_database_url,
            migrations_directory=migration_copy,
        )


def test_failed_migration_is_atomic(
    migration_database_url: str, tmp_path: Path
) -> None:
    (tmp_path / "001_fail.sql").write_text(
        "CREATE TABLE partial_table (id INTEGER); SELECT 1 / 0;\n",
        encoding="utf-8",
    )
    (tmp_path / "001_fail.down.sql").write_text(
        "DROP TABLE partial_table;\n", encoding="utf-8"
    )

    with pytest.raises(psycopg.Error):
        execute_command(
            UpCommand(),
            database_url=migration_database_url,
            migrations_directory=tmp_path,
        )

    assert not _scalar(
        migration_database_url,
        "SELECT to_regclass('partial_table') IS NOT NULL",
    )
    assert (
        _scalar(migration_database_url, "SELECT count(*) FROM schema_migrations")
        == 0
    )


def test_existing_schema_requires_explicit_baseline(
    migration_database_url: str,
) -> None:
    with psycopg.connect(migration_database_url) as connection:
        connection.execute("CREATE TABLE preexisting (id INTEGER)")

    with pytest.raises(MigrationError, match="use 'baseline NNN'"):
        execute_command(UpCommand(), database_url=migration_database_url)

    assert not _scalar(
        migration_database_url,
        "SELECT to_regclass('schema_migrations') IS NOT NULL",
    )

    execute_command(BaselineCommand(8), database_url=migration_database_url)
    assert (
        _scalar(migration_database_url, "SELECT count(*) FROM schema_migrations")
        == 8
    )
    execute_command(UpCommand(), database_url=migration_database_url)


def test_existing_schema_with_empty_history_requires_explicit_baseline(
    migration_database_url: str,
) -> None:
    with psycopg.connect(migration_database_url) as connection:
        connection.execute(CREATE_HISTORY_SQL)
        connection.execute("CREATE TABLE preexisting (id INTEGER)")

    with pytest.raises(MigrationError, match="use 'baseline NNN'"):
        execute_command(UpCommand(), database_url=migration_database_url)

    assert (
        _scalar(migration_database_url, "SELECT count(*) FROM schema_migrations")
        == 0
    )
    assert _scalar(
        migration_database_url,
        "SELECT to_regclass('preexisting') IS NOT NULL",
    )


def test_migration_four_down_restores_unambiguous_legacy_graph(
    migration_database_url: str,
) -> None:
    execute_command(UpCommand(), database_url=migration_database_url)
    _rollback_to_version_four(migration_database_url)
    _insert_graph_fixture(migration_database_url, org_state_count=1)

    execute_command(
        DownCommand("004_alter_graphs_to_scenarios.down.sql"),
        database_url=migration_database_url,
    )

    assert _scalar(migration_database_url, "SELECT count(*) FROM graphs") == 1
    assert _scalar(
        migration_database_url,
        """
        SELECT count(*)
        FROM graph_nodes gn
        JOIN graphs g ON g.graph_id = gn.graph_id
        JOIN org_states os ON os.org_state_id = g.org_state_id
        WHERE os.scenario_id = 101
        """,
    ) == 1


def test_migration_four_down_fails_atomically_when_mapping_is_ambiguous(
    migration_database_url: str,
) -> None:
    execute_command(UpCommand(), database_url=migration_database_url)
    _rollback_to_version_four(migration_database_url)
    _insert_graph_fixture(migration_database_url, org_state_count=2)

    with pytest.raises(psycopg.Error, match="exactly one org_state"):
        execute_command(
            DownCommand("004_alter_graphs_to_scenarios.down.sql"),
            database_url=migration_database_url,
        )

    assert not _scalar(
        migration_database_url, "SELECT to_regclass('graphs') IS NOT NULL"
    )
    assert _scalar(
        migration_database_url,
        "SELECT max(version) FROM schema_migrations",
    ) == 4


def test_concurrent_up_commands_are_serialized(
    migration_database_url: str, tmp_path: Path
) -> None:
    (tmp_path / "001_slow.sql").write_text(
        "SELECT pg_sleep(0.25); CREATE TABLE concurrent_table (id INTEGER);\n",
        encoding="utf-8",
    )
    (tmp_path / "001_slow.down.sql").write_text(
        "DROP TABLE concurrent_table;\n", encoding="utf-8"
    )
    barrier = threading.Barrier(2)
    errors: list[BaseException] = []

    def run_up() -> None:
        try:
            barrier.wait()
            execute_command(
                UpCommand(),
                database_url=migration_database_url,
                migrations_directory=tmp_path,
            )
        except BaseException as error:  # pragma: no cover - asserted below
            errors.append(error)

    threads = [threading.Thread(target=run_up) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    assert (
        _scalar(migration_database_url, "SELECT count(*) FROM schema_migrations")
        == 1
    )
