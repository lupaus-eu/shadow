import json
import os
import subprocess
import uuid
from collections.abc import Generator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
from typing import Any, LiteralString, cast
from urllib.parse import quote

import psycopg
import pytest
from psycopg import sql

from app.core.migrations import UpCommand, execute_command
from app.seed_reference_data import ReferenceDataSeedResult, seed_reference_data

TEST_DATABASE_ENV = "MIGRATION_TEST_DATABASE_URL"
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEVELOPMENT_SEED_PATH = (
    REPOSITORY_ROOT / "db" / "init" / "002_seed_development_data.sql"
)
REFERENCE_JSON_PATH = (
    REPOSITORY_ROOT / "db" / "init" / "metamodel_state_##default##.json"
)


@contextmanager
def _temporary_schema(base_url: str) -> Generator[str, None, None]:
    schema_name = f"reference_seed_test_{uuid.uuid4().hex}"
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


def _rows(database_url: str, query: str) -> list[tuple[Any, ...]]:
    with psycopg.connect(database_url) as connection:
        return connection.execute(
            sql.SQL(cast(LiteralString, query))
        ).fetchall()


def _scalar(database_url: str, query: str) -> object:
    rows = _rows(database_url, query)
    assert len(rows) == 1
    return rows[0][0]


def _reference_snapshot(database_url: str) -> tuple[list[tuple[Any, ...]], ...]:
    return (
        _rows(
            database_url,
            """
            SELECT version
            FROM metamodels
            WHERE organisation_id IS NULL AND deleted_time IS NULL
            ORDER BY version
            """,
        ),
        _rows(
            database_url,
            """
            SELECT node_type_key, name, display_name, ui_color, ui_shape,
                   timeserie_id, timeserie_secondary_id, timeserie_id_rule
            FROM node_types
            WHERE deleted_time IS NULL
            ORDER BY node_type_key
            """,
        ),
        _rows(
            database_url,
            """
            SELECT edge_type_key, name, display_name, ui_style,
                   ui_source_end, ui_target_end
            FROM edge_types
            WHERE deleted_time IS NULL
            ORDER BY edge_type_key
            """,
        ),
        _rows(
            database_url,
            """
            SELECT type_attributes.owner_kind,
                   COALESCE(node_types.node_type_key, edge_types.edge_type_key),
                   type_attributes.attribute_key, type_attributes.name,
                   type_attributes.display_name, type_attributes.data_type,
                   type_attributes.mandatory, type_attributes.max_length,
                   type_attributes.multiline
            FROM type_attributes
            LEFT JOIN node_types
              ON node_types.node_type_id = type_attributes.owner_node_type_id
            LEFT JOIN edge_types
              ON edge_types.edge_type_id = type_attributes.owner_edge_type_id
            WHERE type_attributes.deleted_time IS NULL
            ORDER BY type_attributes.owner_kind, 2, type_attributes.attribute_key
            """,
        ),
        _rows(
            database_url,
            """
            SELECT edge_types.edge_type_key,
                   source_node_type.node_type_key,
                   target_node_type.node_type_key
            FROM allowed_connections
            JOIN edge_types
              ON edge_types.edge_type_id = allowed_connections.edge_type_id
            JOIN node_types AS source_node_type
              ON source_node_type.node_type_id = allowed_connections.source_node_type_id
            JOIN node_types AS target_node_type
              ON target_node_type.node_type_id = allowed_connections.target_node_type_id
            WHERE allowed_connections.deleted_time IS NULL
            ORDER BY 1, 2, 3
            """,
        ),
    )


def _all_reference_counts(database_url: str) -> list[tuple[Any, ...]]:
    return _rows(
        database_url,
        """
        SELECT 'allowed_connections', count(*) FROM allowed_connections
        UNION ALL SELECT 'edge_types', count(*) FROM edge_types
        UNION ALL SELECT 'metamodels', count(*) FROM metamodels
        UNION ALL SELECT 'node_types', count(*) FROM node_types
        UNION ALL SELECT 'type_attributes', count(*) FROM type_attributes
        ORDER BY 1
        """,
    )


def test_production_and_stdin_development_seed_share_reference_data() -> None:
    base_url = os.getenv(TEST_DATABASE_ENV)
    if base_url is None:
        pytest.skip(f"{TEST_DATABASE_ENV} is not configured")

    with _temporary_schema(base_url) as production_url:
        execute_command(UpCommand(), database_url=production_url)
        production_result = seed_reference_data(production_url)
        production_snapshot = _reference_snapshot(production_url)

        assert production_result.inserted is True
        assert _scalar(production_url, "SELECT count(*) FROM users") == 0

    with _temporary_schema(base_url) as development_url:
        execute_command(UpCommand(), database_url=development_url)
        completed = subprocess.run(
            ["psql", "-X", development_url],
            cwd=REPOSITORY_ROOT,
            input=DEVELOPMENT_SEED_PATH.read_text(encoding="utf-8"),
            text=True,
            capture_output=True,
            check=False,
        )

        assert completed.returncode == 0, completed.stderr
        assert _scalar(development_url, "SELECT count(*) FROM users") == 2
        assert _reference_snapshot(development_url) == production_snapshot

    source = json.loads(REFERENCE_JSON_PATH.read_text(encoding="utf-8"))
    assert len(production_snapshot[1]) == len(source["node_types"])
    assert len(production_snapshot[2]) == len(source["edge_types"])
    assert len(production_snapshot[3]) == sum(
        len(type_definition.get("attributes", []))
        for type_definition in source["node_types"] + source["edge_types"]
    )
    assert len(production_snapshot[4]) == sum(
        len(connection["source_node_type_ids"])
        * len(connection["target_node_type_ids"])
        for edge_type in source["edge_types"]
        for connection in edge_type.get("allowed_connections", [])
    )


def test_seed_is_idempotent_and_leaves_business_tables_empty(
    migration_database_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    execute_command(UpCommand(), database_url=migration_database_url)
    monkeypatch.chdir(tmp_path)

    first = seed_reference_data(migration_database_url)
    before = _reference_snapshot(migration_database_url)
    second = seed_reference_data(migration_database_url)

    assert first.inserted is True
    assert second.inserted is False
    assert _reference_snapshot(migration_database_url) == before
    for table in (
        "users",
        "user_identities",
        "auth_sessions",
        "organisations",
        "scenarios",
        "graph_nodes",
        "graph_edges",
        "customers",
    ):
        assert _scalar(migration_database_url, f"SELECT count(*) FROM {table}") == 0


def test_existing_active_default_is_preserved(
    migration_database_url: str,
) -> None:
    execute_command(UpCommand(), database_url=migration_database_url)
    with psycopg.connect(migration_database_url) as connection:
        connection.execute(
            "INSERT INTO metamodels (organisation_id, version) VALUES (NULL, 77)"
        )
        connection.execute(
            """
            INSERT INTO node_types (
                metamodel_id, node_type_key, name, display_name
            )
            VALUES (101, 'existing', 'Existing', 'Existing')
            """
        )

    before = _reference_snapshot(migration_database_url)
    result = seed_reference_data(migration_database_url)

    assert result.inserted is False
    assert _reference_snapshot(migration_database_url) == before


def test_concurrent_seed_calls_create_one_complete_default(
    migration_database_url: str,
) -> None:
    execute_command(UpCommand(), database_url=migration_database_url)

    def run_seed(_index: int) -> ReferenceDataSeedResult:
        return seed_reference_data(migration_database_url)

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(run_seed, range(2)))

    assert sorted(result.inserted for result in results) == [False, True]
    assert _scalar(migration_database_url, "SELECT count(*) FROM metamodels") == 1
    counts = _all_reference_counts(migration_database_url)
    assert all(count > 0 for _table, count in counts)


def test_failure_rolls_back_partial_reference_data(
    migration_database_url: str,
    tmp_path: Path,
) -> None:
    execute_command(UpCommand(), database_url=migration_database_url)
    source_sql = (
        REPOSITORY_ROOT / "db" / "init" / "001_seed_reference_data.sql"
    ).read_text(encoding="utf-8")
    failing_sql = tmp_path / "failing_seed.sql"
    failing_sql.write_text(source_sql + "\nSELECT 1 / 0;\n", encoding="utf-8")

    with pytest.raises(psycopg.errors.DivisionByZero):
        seed_reference_data(migration_database_url, sql_path=failing_sql)

    counts = _all_reference_counts(migration_database_url)
    assert all(count == 0 for _table, count in counts)


def test_unmigrated_database_fails_without_creating_seed_tables(
    migration_database_url: str,
) -> None:
    with pytest.raises(psycopg.errors.UndefinedTable):
        seed_reference_data(migration_database_url)

    assert _scalar(
        migration_database_url,
        "SELECT to_regclass('metamodels') IS NULL",
    ) is True
