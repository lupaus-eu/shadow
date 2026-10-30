from __future__ import annotations

import os
import shutil
import threading
import uuid
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
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

    assert _scalar(
        migration_database_url, "SELECT count(*) FROM schema_migrations"
    ) == len(discover_migrations())
    assert _scalar(
        migration_database_url,
        "SELECT to_regclass('auth_sessions') IS NOT NULL",
    )

    execute_command(UpCommand(), database_url=migration_database_url)

    for migration in reversed(discover_migrations()):
        execute_command(
            DownCommand(migration.down_name), database_url=migration_database_url
        )

    assert (
        _scalar(migration_database_url, "SELECT count(*) FROM schema_migrations") == 0
    )
    assert not _scalar(
        migration_database_url, "SELECT to_regclass('users') IS NOT NULL"
    )

    execute_command(UpCommand(), database_url=migration_database_url)
    assert _scalar(
        migration_database_url, "SELECT count(*) FROM schema_migrations"
    ) == len(discover_migrations())


def test_rejects_non_latest_and_unapplied_down_migrations(
    migration_database_url: str,
) -> None:
    execute_command(UpCommand(), database_url=migration_database_url)

    with pytest.raises(MigrationError, match="Unknown down migration"):
        execute_command(
            DownCommand("010_unknown.down.sql"),
            database_url=migration_database_url,
        )

    with pytest.raises(MigrationError, match="not the latest applied"):
        execute_command(
            DownCommand("007_create_contacts.down.sql"),
            database_url=migration_database_url,
        )

    execute_command(
        DownCommand("019_add_ai_change_set_review_channel.down.sql"),
        database_url=migration_database_url,
    )
    execute_command(
        DownCommand("018_create_ai_change_sets.down.sql"),
        database_url=migration_database_url,
    )
    execute_command(
        DownCommand("017_create_mcp_oauth_schema.down.sql"),
        database_url=migration_database_url,
    )
    execute_command(
        DownCommand("016_add_prophet_result_kind.down.sql"),
        database_url=migration_database_url,
    )
    execute_command(
        DownCommand("015_create_prediction_requests.down.sql"),
        database_url=migration_database_url,
    )
    execute_command(
        DownCommand("014_add_prediction_intervals.down.sql"),
        database_url=migration_database_url,
    )
    execute_command(
        DownCommand("013_create_derived_metrics.down.sql"),
        database_url=migration_database_url,
    )
    execute_command(
        DownCommand("012_add_timeserie_short_name.down.sql"),
        database_url=migration_database_url,
    )
    execute_command(
        DownCommand("011_alter_prediction_target_observation_source.down.sql"),
        database_url=migration_database_url,
    )
    execute_command(
        DownCommand("010_create_prediction_schema.down.sql"),
        database_url=migration_database_url,
    )
    execute_command(
        DownCommand("009_add_auth_identity_session_schema.down.sql"),
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


def test_detects_checksum_drift(migration_database_url: str, tmp_path: Path) -> None:
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
        _scalar(migration_database_url, "SELECT count(*) FROM schema_migrations") == 0
    )


def test_existing_schema_requires_explicit_baseline(
    migration_database_url: str,
) -> None:
    migrations = discover_migrations()
    with psycopg.connect(migration_database_url) as connection:
        connection.execute("CREATE TABLE preexisting (id INTEGER)")

    with pytest.raises(MigrationError, match="use 'baseline NNN'"):
        execute_command(UpCommand(), database_url=migration_database_url)

    assert not _scalar(
        migration_database_url,
        "SELECT to_regclass('schema_migrations') IS NOT NULL",
    )

    execute_command(
        BaselineCommand(migrations[-1].version), database_url=migration_database_url
    )
    assert _scalar(
        migration_database_url, "SELECT count(*) FROM schema_migrations"
    ) == len(migrations)
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
        _scalar(migration_database_url, "SELECT count(*) FROM schema_migrations") == 0
    )
    assert _scalar(
        migration_database_url,
        "SELECT to_regclass('preexisting') IS NOT NULL",
    )


def test_migration_nine_upgrades_an_empty_version_eight_database(
    migration_database_url: str,
    tmp_path: Path,
) -> None:
    migrations = discover_migrations()
    migration_copy = tmp_path / "migrations_through_008"
    migration_copy.mkdir()
    for migration in migrations[:8]:
        shutil.copy2(migration.up_path, migration_copy / migration.up_name)
        shutil.copy2(migration.down_path, migration_copy / migration.down_name)

    execute_command(
        UpCommand(),
        database_url=migration_database_url,
        migrations_directory=migration_copy,
    )
    assert (
        _scalar(
            migration_database_url,
            "SELECT max(version) FROM schema_migrations",
        )
        == 8
    )

    execute_command(UpCommand(), database_url=migration_database_url)

    assert (
        _scalar(
            migration_database_url,
            "SELECT max(version) FROM schema_migrations",
        )
        == migrations[-1].version
    )
    assert _scalar(
        migration_database_url,
        "SELECT is_nullable = 'NO' FROM information_schema.columns "
        "WHERE table_schema = current_schema() "
        "AND table_name = 'users' AND column_name = 'email'",
    )
    assert _scalar(
        migration_database_url,
        "SELECT to_regclass('user_identities') IS NOT NULL",
    )
    assert _scalar(
        migration_database_url,
        "SELECT to_regclass('oidc_login_transactions') IS NOT NULL",
    )
    assert _scalar(
        migration_database_url,
        "SELECT to_regclass('auth_sessions') IS NOT NULL",
    )
    assert _scalar(
        migration_database_url,
        "SELECT to_regclass('prediction_versions') IS NOT NULL",
    )


def test_migration_nine_constraints_and_down_scope(
    migration_database_url: str,
) -> None:
    execute_command(UpCommand(), database_url=migration_database_url)

    with psycopg.connect(migration_database_url) as connection:
        connection.execute(
            "INSERT INTO users (name, email, role) "
            "VALUES ('First', 'First@Example.Local', 'admin')"
        )
        connection.commit()

    with psycopg.connect(migration_database_url) as connection:
        with pytest.raises(psycopg.errors.UniqueViolation):
            connection.execute(
                "INSERT INTO users (name, email, role) "
                "VALUES ('Duplicate', 'first@example.local', 'consultant')"
            )

    with psycopg.connect(migration_database_url) as connection:
        connection.execute(
            "UPDATE users SET deleted_time = now() "
            "WHERE lower(email) = 'first@example.local'"
        )
        replacement = connection.execute(
            "INSERT INTO users (name, email, role) "
            "VALUES ('Replacement', 'first@example.local', 'consultant') "
            "RETURNING user_id"
        ).fetchone()
        assert replacement is not None
        connection.execute(
            "INSERT INTO user_identities (user_id, issuer, subject) "
            "VALUES (%s, 'https://issuer.example', 'subject-1')",
            (replacement[0],),
        )
        connection.commit()

    with psycopg.connect(migration_database_url) as connection:
        with pytest.raises(psycopg.errors.UniqueViolation):
            connection.execute(
                "INSERT INTO user_identities (user_id, issuer, subject) "
                "VALUES (%s, 'https://issuer.example', 'subject-2')",
                (replacement[0],),
            )

    for migration in reversed(discover_migrations()[8:]):
        execute_command(
            DownCommand(migration.down_name), database_url=migration_database_url
        )

    assert (
        _scalar(
            migration_database_url,
            "SELECT max(version) FROM schema_migrations",
        )
        == 8
    )
    assert _scalar(
        migration_database_url,
        "SELECT to_regclass('customer_addresses') IS NOT NULL",
    )
    assert not _scalar(
        migration_database_url,
        "SELECT to_regclass('auth_sessions') IS NOT NULL",
    )
    assert not _scalar(
        migration_database_url,
        "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
        "WHERE table_schema = current_schema() "
        "AND table_name = 'users' AND column_name = 'email')",
    )


def test_prediction_schema_rejects_non_finite_numbers(
    migration_database_url: str,
) -> None:
    execute_command(UpCommand(), database_url=migration_database_url)

    with psycopg.connect(migration_database_url) as connection:
        user = connection.execute(
            "INSERT INTO users (name, email, role) "
            "VALUES ('Prediction Tester', 'prediction@example.local', 'admin') "
            "RETURNING user_id"
        ).fetchone()
        assert user is not None
        organisation = connection.execute(
            "INSERT INTO organisations (organisation_key, name, created_by) "
            "VALUES ('prediction-org', 'Prediction Org', %s) "
            "RETURNING organisation_id",
            (user[0],),
        ).fetchone()
        assert organisation is not None
        version = connection.execute(
            "INSERT INTO prediction_versions ("
            "organisation_id, prediction_key, name, cutoff_mode, start_date, "
            "end_date, created_by"
            ") VALUES (%s, 'prediction-1', 'Prediction 1', 'asOfStart', "
            "DATE '2025-01-01', DATE '2025-02-01', %s) "
            "RETURNING prediction_version_id",
            (organisation[0], user[0]),
        ).fetchone()
        assert version is not None
        target = connection.execute(
            "INSERT INTO prediction_targets ("
            "prediction_version_id, target_scenario_id, target_scenario_key, "
            "metric_key, metric_name, time_unit, "
            "eligibility_status, created_by"
            ") VALUES (%s, 1, 'target', 'revenue', 'Revenue', 'month', "
            "'eligible', %s) RETURNING prediction_target_id",
            (version[0], user[0]),
        ).fetchone()
        assert target is not None
        result = connection.execute(
            "INSERT INTO prediction_model_results ("
            "prediction_target_id, result_kind, status, prediction_interval_status, "
            "cross_validation_status, "
            "created_by"
            ") VALUES (%s, 'naive', 'available', 'not_applicable', "
            "'not_applicable', %s) "
            "RETURNING prediction_model_result_id",
            (target[0], user[0]),
        ).fetchone()
        assert result is not None
        connection.commit()

    with psycopg.connect(migration_database_url) as connection:
        with pytest.raises(psycopg.errors.CheckViolation):
            connection.execute(
                "INSERT INTO prediction_model_results ("
                "prediction_target_id, result_kind, status, "
                "prediction_interval_status, "
                "cross_validation_status, "
                "cross_validation_mae, created_by"
                ") VALUES (%s, 'mlforecast', 'available', 'unavailable', 'available', "
                "'NaN'::float8, %s)",
                (target[0], user[0]),
            )

    with psycopg.connect(migration_database_url) as connection:
        with pytest.raises(psycopg.errors.CheckViolation):
            connection.execute(
                "INSERT INTO prediction_points ("
                "prediction_model_result_id, date, value, created_by"
                ") VALUES (%s, DATE '2025-01-01', 'NaN'::float8, %s)",
                (result[0], user[0]),
            )


def test_prediction_interval_migration_resets_development_rows_and_constraints(
    migration_database_url: str, tmp_path: Path
) -> None:
    migrations = discover_migrations()
    migration_copy = tmp_path / "migrations_through_013"
    migration_copy.mkdir()
    for migration in migrations[:13]:
        shutil.copy2(migration.up_path, migration_copy / migration.up_name)
        shutil.copy2(migration.down_path, migration_copy / migration.down_name)
    execute_command(
        UpCommand(),
        database_url=migration_database_url,
        migrations_directory=migration_copy,
    )

    with psycopg.connect(migration_database_url) as connection:
        connection.execute("CREATE TABLE migration_sentinel (value TEXT NOT NULL)")
        connection.execute("INSERT INTO migration_sentinel (value) VALUES ('kept')")
        user = connection.execute(
            "INSERT INTO users (name, email, role) "
            "VALUES ('Interval Tester', 'interval@example.local', 'admin') "
            "RETURNING user_id"
        ).fetchone()
        assert user is not None
        organisation = connection.execute(
            "INSERT INTO organisations (organisation_key, name, created_by) "
            "VALUES ('interval-org', 'Interval Org', %s) "
            "RETURNING organisation_id",
            (user[0],),
        ).fetchone()
        assert organisation is not None
        connection.execute(
            "INSERT INTO prediction_versions ("
            "organisation_id, prediction_key, name, cutoff_mode, start_date, "
            "end_date, created_by"
            ") VALUES (%s, 'discarded-version', 'Discarded version', 'asOfStart', "
            "DATE '2025-01-01', DATE '2025-02-01', %s)",
            (organisation[0], user[0]),
        )
        connection.commit()

    execute_command(UpCommand(), database_url=migration_database_url)
    assert (
        _scalar(migration_database_url, "SELECT count(*) FROM prediction_versions") == 0
    )
    assert (
        _scalar(migration_database_url, "SELECT value FROM migration_sentinel")
        == "kept"
    )

    with psycopg.connect(migration_database_url) as connection:
        with pytest.raises(psycopg.errors.CheckViolation):
            connection.execute(
                "INSERT INTO prediction_versions ("
                "organisation_id, prediction_key, name, cutoff_mode, "
                "confidence_level, start_date, end_date, created_by"
                ") VALUES (%s, 'invalid-level', 'Invalid level', 'asOfStart', "
                "49, DATE '2025-01-01', DATE '2025-02-01', %s)",
                (organisation[0], user[0]),
            )
        connection.rollback()
        version = connection.execute(
            "INSERT INTO prediction_versions ("
            "organisation_id, prediction_key, name, cutoff_mode, start_date, "
            "end_date, created_by"
            ") VALUES (%s, 'interval-version', 'Interval version', 'asOfStart', "
            "DATE '2025-01-01', DATE '2025-02-01', %s) "
            "RETURNING prediction_version_id",
            (organisation[0], user[0]),
        ).fetchone()
        assert version is not None
        confidence_level = connection.execute(
            "SELECT confidence_level FROM prediction_versions"
        ).fetchone()
        assert confidence_level == (80,)
        target = connection.execute(
            "INSERT INTO prediction_targets ("
            "prediction_version_id, target_scenario_id, target_scenario_key, "
            "metric_key, metric_name, time_unit, eligibility_status, created_by"
            ") VALUES (%s, 1, 'target', 'revenue', 'Revenue', 'month', "
            "'eligible', %s) RETURNING prediction_target_id",
            (version[0], user[0]),
        ).fetchone()
        assert target is not None
        result = connection.execute(
            "INSERT INTO prediction_model_results ("
            "prediction_target_id, result_kind, status, prediction_interval_status, "
            "cross_validation_status, created_by"
            ") VALUES (%s, 'mlforecast', 'available', 'available', "
            "'not_applicable', %s) RETURNING prediction_model_result_id",
            (target[0], user[0]),
        ).fetchone()
        assert result is not None
        connection.execute(
            "INSERT INTO prediction_points ("
            "prediction_model_result_id, date, value, lower_bound, upper_bound, "
            "created_by"
            ") VALUES (%s, DATE '2025-01-01', 10, 9, 11, %s)",
            (result[0], user[0]),
        )
        connection.commit()

    invalid_bounds: list[tuple[float | None, float | None]] = [
        (float("nan"), 11),
        (9, None),
        (11, 9),
        (11, 12),
    ]
    for index, (lower_bound, upper_bound) in enumerate(invalid_bounds):
        with psycopg.connect(migration_database_url) as connection:
            with pytest.raises(psycopg.errors.CheckViolation):
                connection.execute(
                    "INSERT INTO prediction_points ("
                    "prediction_model_result_id, date, value, lower_bound, "
                    "upper_bound, created_by"
                    ") VALUES (%s, %s, 10, %s, %s, %s)",
                    (
                        result[0],
                        f"2025-01-0{index + 2}",
                        lower_bound,
                        upper_bound,
                        user[0],
                    ),
                )

    execute_command(
        DownCommand("019_add_ai_change_set_review_channel.down.sql"),
        database_url=migration_database_url,
    )
    execute_command(
        DownCommand("018_create_ai_change_sets.down.sql"),
        database_url=migration_database_url,
    )
    execute_command(
        DownCommand("017_create_mcp_oauth_schema.down.sql"),
        database_url=migration_database_url,
    )
    execute_command(
        DownCommand("016_add_prophet_result_kind.down.sql"),
        database_url=migration_database_url,
    )
    execute_command(
        DownCommand("015_create_prediction_requests.down.sql"),
        database_url=migration_database_url,
    )
    execute_command(
        DownCommand("014_add_prediction_intervals.down.sql"),
        database_url=migration_database_url,
    )
    assert (
        _scalar(migration_database_url, "SELECT count(*) FROM prediction_versions") == 0
    )
    assert (
        _scalar(migration_database_url, "SELECT value FROM migration_sentinel")
        == "kept"
    )
    assert not _scalar(
        migration_database_url,
        "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
        "WHERE table_schema = current_schema() AND table_name = 'prediction_points' "
        "AND column_name = 'lower_bound')",
    )


def test_prophet_result_kind_migration_up_and_down(
    migration_database_url: str,
) -> None:
    execute_command(UpCommand(), database_url=migration_database_url)

    with psycopg.connect(migration_database_url) as connection:
        user = connection.execute(
            "INSERT INTO users (name, email, role) "
            "VALUES ('Prophet Tester', 'prophet@example.local', 'admin') "
            "RETURNING user_id"
        ).fetchone()
        assert user is not None
        organisation = connection.execute(
            "INSERT INTO organisations (organisation_key, name, created_by) "
            "VALUES ('prophet-org', 'Prophet Org', %s) RETURNING organisation_id",
            (user[0],),
        ).fetchone()
        assert organisation is not None
        version = connection.execute(
            "INSERT INTO prediction_versions ("
            "organisation_id, prediction_key, name, cutoff_mode, start_date, "
            "end_date, created_by"
            ") VALUES (%s, 'prophet-version', 'Prophet version', 'asOfStart', "
            "DATE '2025-01-01', DATE '2025-02-01', %s) "
            "RETURNING prediction_version_id",
            (organisation[0], user[0]),
        ).fetchone()
        assert version is not None
        target = connection.execute(
            "INSERT INTO prediction_targets ("
            "prediction_version_id, target_scenario_id, target_scenario_key, "
            "metric_key, metric_name, time_unit, eligibility_status, created_by"
            ") VALUES (%s, 1, 'target', 'revenue', 'Revenue', 'month', "
            "'eligible', %s) RETURNING prediction_target_id",
            (version[0], user[0]),
        ).fetchone()
        assert target is not None
        for kind in ("naive", "prophet"):
            result = connection.execute(
                "INSERT INTO prediction_model_results ("
                "prediction_target_id, result_kind, status, "
                "prediction_interval_status, cross_validation_status, created_by"
                ") VALUES (%s, %s, 'available', 'not_applicable', "
                "'not_applicable', %s) RETURNING prediction_model_result_id",
                (target[0], kind, user[0]),
            ).fetchone()
            assert result is not None
            connection.execute(
                "INSERT INTO prediction_points ("
                "prediction_model_result_id, date, value, created_by"
                ") VALUES (%s, DATE '2025-01-01', 10, %s)",
                (result[0], user[0]),
            )
        connection.commit()

    execute_command(
        DownCommand("019_add_ai_change_set_review_channel.down.sql"),
        database_url=migration_database_url,
    )
    execute_command(
        DownCommand("018_create_ai_change_sets.down.sql"),
        database_url=migration_database_url,
    )
    execute_command(
        DownCommand("017_create_mcp_oauth_schema.down.sql"),
        database_url=migration_database_url,
    )
    execute_command(
        DownCommand("016_add_prophet_result_kind.down.sql"),
        database_url=migration_database_url,
    )
    assert _scalar(
        migration_database_url,
        "SELECT string_agg(result_kind, ',') FROM prediction_model_results",
    ) == "naive"
    assert (
        _scalar(migration_database_url, "SELECT count(*) FROM prediction_points") == 1
    )
    assert (
        _scalar(migration_database_url, "SELECT count(*) FROM prediction_versions")
        == 1
    )
    with psycopg.connect(migration_database_url) as connection:
        with pytest.raises(psycopg.errors.CheckViolation):
            connection.execute(
                "INSERT INTO prediction_model_results ("
                "prediction_target_id, result_kind, status, "
                "prediction_interval_status, cross_validation_status"
                ") VALUES (%s, 'prophet', 'ineligible', 'unavailable', "
                "'unavailable')",
                (target[0],),
            )

    execute_command(UpCommand(), database_url=migration_database_url)
    with psycopg.connect(migration_database_url) as connection:
        connection.execute(
            "INSERT INTO prediction_model_results ("
            "prediction_target_id, result_kind, status, "
            "prediction_interval_status, cross_validation_status"
            ") VALUES (%s, 'prophet', 'ineligible', 'unavailable', 'unavailable')",
            (target[0],),
        )
        with pytest.raises(psycopg.errors.CheckViolation):
            connection.execute(
                "INSERT INTO prediction_model_results ("
                "prediction_target_id, result_kind, status, "
                "prediction_interval_status, cross_validation_status"
                ") VALUES (%s, 'arima', 'ineligible', 'unavailable', "
                "'unavailable')",
                (target[0],),
            )


def test_prediction_observation_source_migration_replaces_schema(
    migration_database_url: str,
) -> None:
    execute_command(UpCommand(), database_url=migration_database_url)

    assert not _scalar(
        migration_database_url,
        """
        SELECT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND table_name = 'prediction_targets'
              AND column_name = 'reality_scenario_key'
        )
        """,
    )

    with psycopg.connect(migration_database_url) as connection:
        with pytest.raises(psycopg.errors.CheckViolation):
            connection.execute(
                """
                INSERT INTO prediction_versions (
                    organisation_id, prediction_key, name, cutoff_mode,
                    start_date, end_date
                ) VALUES (1, 'legacy-cutoff', 'Legacy cutoff',
                    'allCurrentReality', DATE '2025-01-01', DATE '2025-02-01')
                """
            )

    execute_command(
        DownCommand("019_add_ai_change_set_review_channel.down.sql"),
        database_url=migration_database_url,
    )
    execute_command(
        DownCommand("018_create_ai_change_sets.down.sql"),
        database_url=migration_database_url,
    )
    execute_command(
        DownCommand("017_create_mcp_oauth_schema.down.sql"),
        database_url=migration_database_url,
    )
    execute_command(
        DownCommand("016_add_prophet_result_kind.down.sql"),
        database_url=migration_database_url,
    )
    execute_command(
        DownCommand("015_create_prediction_requests.down.sql"),
        database_url=migration_database_url,
    )
    execute_command(
        DownCommand("014_add_prediction_intervals.down.sql"),
        database_url=migration_database_url,
    )
    execute_command(
        DownCommand("013_create_derived_metrics.down.sql"),
        database_url=migration_database_url,
    )
    execute_command(
        DownCommand("012_add_timeserie_short_name.down.sql"),
        database_url=migration_database_url,
    )
    execute_command(
        DownCommand("011_alter_prediction_target_observation_source.down.sql"),
        database_url=migration_database_url,
    )
    assert _scalar(
        migration_database_url,
        """
        SELECT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND table_name = 'prediction_targets'
              AND column_name = 'reality_scenario_key'
        )
        """,
    )
    execute_command(UpCommand(), database_url=migration_database_url)


def test_prediction_request_migration_preserves_versions_and_enforces_lifecycle(
    migration_database_url: str,
) -> None:
    execute_command(UpCommand(), database_url=migration_database_url)
    with psycopg.connect(migration_database_url) as connection:
        user = connection.execute(
            "INSERT INTO users (name, email, role) "
            "VALUES ('Queue Tester', 'queue@example.local', 'admin') RETURNING user_id"
        ).fetchone()
        assert user is not None
        organisation = connection.execute(
            "INSERT INTO organisations (organisation_key, name, created_by) "
            "VALUES ('queue-org', 'Queue Org', %s) RETURNING organisation_id",
            (user[0],),
        ).fetchone()
        other = connection.execute(
            "INSERT INTO organisations (organisation_key, name, created_by) "
            "VALUES ('other-queue-org', 'Other Queue Org', %s) "
            "RETURNING organisation_id",
            (user[0],),
        ).fetchone()
        assert organisation is not None and other is not None
        version = connection.execute(
            "INSERT INTO prediction_versions ("
            "organisation_id, prediction_key, name, cutoff_mode, start_date, "
            "end_date, created_by) VALUES "
            "(%s, 'existing-version', 'Existing', 'asOfStart', "
            "DATE '2025-01-01', DATE '2025-02-01', %s) "
            "RETURNING prediction_version_id",
            (organisation[0], user[0]),
        ).fetchone()
        assert version is not None
        connection.commit()

    assert _scalar(
        migration_database_url, "SELECT count(*) FROM prediction_requests"
    ) == 0
    assert _scalar(
        migration_database_url,
        "SELECT to_regclass('idx_prediction_requests_organisation_active') "
        "IS NOT NULL",
    )
    with psycopg.connect(migration_database_url) as connection:
        connection.execute(
            "INSERT INTO prediction_requests ("
            "prediction_request_key, organisation_id, name, input_snapshot, "
            "submitted_by) VALUES ('active', %s, 'Reserved', '{}'::jsonb, %s)",
            (organisation[0], user[0]),
        )
        connection.execute(
            "INSERT INTO prediction_requests ("
            "prediction_request_key, organisation_id, name, input_snapshot, state, "
            "start_time, finish_time, failure_code, failure_reason, submitted_by) "
            "VALUES ('failed-history', %s, 'RESERVED', '{}'::jsonb, 'failed', "
            "now(), now(), 'FAILED', 'Safe reason.', %s)",
            (organisation[0], user[0]),
        )
        connection.commit()

    with psycopg.connect(migration_database_url) as connection:
        with pytest.raises(psycopg.errors.UniqueViolation):
            connection.execute(
                "INSERT INTO prediction_requests ("
                "prediction_request_key, organisation_id, name, input_snapshot, "
                "submitted_by) VALUES ('duplicate', %s, 'reserved', '{}'::jsonb, %s)",
                (organisation[0], user[0]),
            )

    with psycopg.connect(migration_database_url) as connection:
        with pytest.raises(psycopg.errors.CheckViolation):
            connection.execute(
                "INSERT INTO prediction_requests ("
                "prediction_request_key, organisation_id, name, input_snapshot, "
                "state, submitted_by) VALUES "
                "('invalid-state', %s, 'Invalid', '{}'::jsonb, 'running', %s)",
                (organisation[0], user[0]),
            )

    with psycopg.connect(migration_database_url) as connection:
        with pytest.raises(psycopg.errors.ForeignKeyViolation):
            connection.execute(
                "INSERT INTO prediction_requests ("
                "prediction_request_key, organisation_id, name, input_snapshot, "
                "state, start_time, finish_time, submitted_by, "
                "completed_prediction_version_id) VALUES "
                "('wrong-owner', %s, 'Wrong owner', '{}'::jsonb, 'completed', "
                "now(), now(), %s, %s)",
                (other[0], user[0], version[0]),
            )

    execute_command(
        DownCommand("019_add_ai_change_set_review_channel.down.sql"),
        database_url=migration_database_url,
    )
    execute_command(
        DownCommand("018_create_ai_change_sets.down.sql"),
        database_url=migration_database_url,
    )
    execute_command(
        DownCommand("017_create_mcp_oauth_schema.down.sql"),
        database_url=migration_database_url,
    )
    execute_command(
        DownCommand("016_add_prophet_result_kind.down.sql"),
        database_url=migration_database_url,
    )
    execute_command(
        DownCommand("015_create_prediction_requests.down.sql"),
        database_url=migration_database_url,
    )
    assert _scalar(
        migration_database_url, "SELECT count(*) FROM prediction_versions"
    ) == 1
    assert not _scalar(
        migration_database_url,
        "SELECT to_regclass('prediction_requests') IS NOT NULL",
    )
    execute_command(UpCommand(), database_url=migration_database_url)


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
    assert (
        _scalar(
            migration_database_url,
            """
        SELECT count(*)
        FROM graph_nodes gn
        JOIN graphs g ON g.graph_id = gn.graph_id
        JOIN org_states os ON os.org_state_id = g.org_state_id
        WHERE os.scenario_id = 101
        """,
        )
        == 1
    )


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
    assert (
        _scalar(
            migration_database_url,
            "SELECT max(version) FROM schema_migrations",
        )
        == 4
    )


def test_timeserie_name_and_short_name_indexes_enforce_active_scope(
    migration_database_url: str,
) -> None:
    execute_command(UpCommand(), database_url=migration_database_url)

    with psycopg.connect(migration_database_url) as connection:
        user = connection.execute(
            """
            INSERT INTO users (name, email, role)
            VALUES ('Migration Tester', 'migration@example.test', 'admin')
            RETURNING user_id
            """
        ).fetchone()
        assert user is not None
        organisation = connection.execute(
            """
            INSERT INTO organisations (organisation_key, name, created_by)
            VALUES ('migration-org', 'Migration Org', %s)
            RETURNING organisation_id
            """,
            (user[0],),
        ).fetchone()
        assert organisation is not None
        scenario = connection.execute(
            """
            INSERT INTO scenarios (organisation_id, scenario_key, name, created_by)
            VALUES (%s, 'migration-scenario', 'Migration Scenario', %s)
            RETURNING scenario_id
            """,
            (organisation[0], user[0]),
        ).fetchone()
        assert scenario is not None
        connection.execute(
            """
            INSERT INTO timeseries (
                scenario_id, timeserie_key, name, short_name, time_unit,
                value_unit, created_by
            ) VALUES (%s, 'revenue', 'Revenue', 'revenue_monthly', 'month',
                'number', %s)
            """,
            (scenario[0], user[0]),
        )
        connection.commit()

        with pytest.raises(psycopg.errors.UniqueViolation):
            connection.execute(
                """
                INSERT INTO timeseries (
                    scenario_id, timeserie_key, name, time_unit, value_unit,
                    created_by
                ) VALUES (%s, 'revenue-copy', 'revenue', 'month', 'number', %s)
                """,
                (scenario[0], user[0]),
            )
        connection.rollback()

        with pytest.raises(psycopg.errors.UniqueViolation):
            connection.execute(
                """
                INSERT INTO timeseries (
                    scenario_id, timeserie_key, name, time_unit, value_unit,
                    created_by
                ) VALUES (%s, 'revenue-whitespace-copy', ' Revenue ', 'month',
                    'number', %s)
                """,
                (scenario[0], user[0]),
            )
        connection.rollback()

        with pytest.raises(psycopg.errors.UniqueViolation):
            connection.execute(
                """
                INSERT INTO timeseries (
                    scenario_id, timeserie_key, name, short_name, time_unit,
                    value_unit, created_by
                ) VALUES (%s, 'revenue-short-name-copy', 'Revenue copy',
                    'revenue_monthly', 'month', 'number', %s)
                """,
                (scenario[0], user[0]),
            )
        connection.rollback()

        connection.execute(
            """
            UPDATE timeseries
            SET deleted_time = now()
            WHERE scenario_id = %s AND timeserie_key = 'revenue'
            """,
            (scenario[0],),
        )
        connection.execute(
            """
            INSERT INTO timeseries (
                scenario_id, timeserie_key, name, short_name, time_unit,
                value_unit, created_by
            ) VALUES (%s, 'revenue-replacement', 'REVENUE',
                'revenue_monthly', 'month', 'number', %s)
            """,
            (scenario[0], user[0]),
        )
        connection.commit()

    execute_command(
        DownCommand("019_add_ai_change_set_review_channel.down.sql"),
        database_url=migration_database_url,
    )
    execute_command(
        DownCommand("018_create_ai_change_sets.down.sql"),
        database_url=migration_database_url,
    )
    execute_command(
        DownCommand("017_create_mcp_oauth_schema.down.sql"),
        database_url=migration_database_url,
    )
    execute_command(
        DownCommand("016_add_prophet_result_kind.down.sql"),
        database_url=migration_database_url,
    )
    execute_command(
        DownCommand("015_create_prediction_requests.down.sql"),
        database_url=migration_database_url,
    )
    execute_command(
        DownCommand("014_add_prediction_intervals.down.sql"),
        database_url=migration_database_url,
    )
    execute_command(
        DownCommand("013_create_derived_metrics.down.sql"),
        database_url=migration_database_url,
    )
    execute_command(
        DownCommand("012_add_timeserie_short_name.down.sql"),
        database_url=migration_database_url,
    )
    assert not _scalar(
        migration_database_url,
        """
        SELECT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND table_name = 'timeseries'
              AND column_name = 'short_name'
        )
        """,
    )
    assert not _scalar(
        migration_database_url,
        "SELECT to_regclass('ux_timeseries_scenario_short_name_active') IS NOT NULL",
    )
    assert not _scalar(
        migration_database_url,
        "SELECT to_regclass('ux_timeseries_scenario_name_active') IS NOT NULL",
    )


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
        _scalar(migration_database_url, "SELECT count(*) FROM schema_migrations") == 1
    )


MCP_REDIRECT_URIS = '["https://claude.ai/api/mcp/auth_callback"]'
MCP_CODE_CHALLENGE = "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"


def _schema_catalog(database_url: str) -> list[tuple[object, ...]]:
    with psycopg.connect(database_url) as connection:
        relations = connection.execute(
            "SELECT 'relation', relname, relkind::text FROM pg_class "
            "WHERE relnamespace = current_schema()::regnamespace"
        ).fetchall()
        constraints = connection.execute(
            "SELECT 'constraint', conname, pg_get_constraintdef(oid) "
            "FROM pg_constraint "
            "WHERE connamespace = current_schema()::regnamespace"
        ).fetchall()
        columns = connection.execute(
            "SELECT 'column', table_name || '.' || column_name, data_type "
            "FROM information_schema.columns "
            "WHERE table_schema = current_schema()"
        ).fetchall()
    return sorted([*relations, *constraints, *columns], key=repr)


def test_mcp_oauth_migration_down_fully_reverses_up(
    migration_database_url: str, tmp_path: Path
) -> None:
    migrations = discover_migrations()
    migration_copy = tmp_path / "migrations_through_016"
    migration_copy.mkdir()
    for migration in migrations[:16]:
        shutil.copy2(migration.up_path, migration_copy / migration.up_name)
        shutil.copy2(migration.down_path, migration_copy / migration.down_name)
    execute_command(
        UpCommand(),
        database_url=migration_database_url,
        migrations_directory=migration_copy,
    )
    before = _schema_catalog(migration_database_url)

    execute_command(UpCommand(), database_url=migration_database_url)
    assert (
        _scalar(
            migration_database_url,
            "SELECT count(*) FROM pg_tables "
            "WHERE schemaname = current_schema() AND tablename LIKE 'mcp_oauth_%'",
        )
        == 4
    )

    execute_command(
        DownCommand("019_add_ai_change_set_review_channel.down.sql"),
        database_url=migration_database_url,
    )
    execute_command(
        DownCommand("018_create_ai_change_sets.down.sql"),
        database_url=migration_database_url,
    )
    execute_command(
        DownCommand("017_create_mcp_oauth_schema.down.sql"),
        database_url=migration_database_url,
    )

    assert (
        _scalar(migration_database_url, "SELECT max(version) FROM schema_migrations")
        == 16
    )
    assert _schema_catalog(migration_database_url) == before


def _insert_mcp_oauth_fixture(
    connection: psycopg.Connection[tuple[object, ...]],
) -> tuple[object, object, object]:
    user = connection.execute(
        "INSERT INTO users (name, email, role) "
        "VALUES ('MCP Tester', 'mcp@example.local', 'consultant') RETURNING user_id"
    ).fetchone()
    assert user is not None
    client = connection.execute(
        "INSERT INTO mcp_oauth_clients (client_id, client_name, redirect_uris) "
        "VALUES ('client-1', 'Claude', %s::jsonb) RETURNING mcp_oauth_client_id",
        (MCP_REDIRECT_URIS,),
    ).fetchone()
    assert client is not None
    grant = connection.execute(
        "INSERT INTO mcp_oauth_grants ("
        "grant_key, mcp_oauth_client_id, user_id, scopes, resource, expires_time"
        ") VALUES ('grant-1', %s, %s, 'schatten.write', "
        "'https://app.localhost/api/mcp/write', now() + interval '30 days') "
        "RETURNING grant_id",
        (client[0], user[0]),
    ).fetchone()
    assert grant is not None
    return user[0], client[0], grant[0]


def test_mcp_oauth_grant_deletion_cascades_and_clients_are_restricted(
    migration_database_url: str,
) -> None:
    execute_command(UpCommand(), database_url=migration_database_url)

    with psycopg.connect(migration_database_url) as connection:
        user_id, client_id, grant_id = _insert_mcp_oauth_fixture(connection)
        for token_hash, kind, replaced_by_hash in (
            (b"a" * 32, "access", None),
            (b"r" * 32, "refresh", b"n" * 32),
            (b"n" * 32, "refresh", None),
        ):
            connection.execute(
                "INSERT INTO mcp_oauth_tokens ("
                "token_hash, grant_id, kind, expires_time, replaced_by_hash"
                ") VALUES (%s, %s, %s, now() + interval '1 hour', %s)",
                (token_hash, grant_id, kind, replaced_by_hash),
            )
        connection.commit()

    with psycopg.connect(migration_database_url) as connection:
        with pytest.raises(psycopg.errors.RestrictViolation):
            connection.execute(
                "DELETE FROM mcp_oauth_clients WHERE mcp_oauth_client_id = %s",
                (client_id,),
            )

    with psycopg.connect(migration_database_url) as connection:
        connection.execute(
            "INSERT INTO mcp_oauth_authorization_requests ("
            "request_id_hash, mcp_oauth_client_id, redirect_uri, state, "
            "code_challenge, scopes, resource, expires_time, user_id, code_hash, "
            "code_expires_time, consumed_time, grant_id"
            ") VALUES (%s, %s, 'https://claude.ai/api/mcp/auth_callback', "
            "'state', %s, 'schatten.write', 'https://app.localhost/api/mcp/write', "
            "now() + interval '10 minutes', %s, %s, "
            "now() + interval '60 seconds', now(), %s)",
            (b"q" * 32, client_id, MCP_CODE_CHALLENGE, user_id, b"c" * 32, grant_id),
        )
        connection.commit()

    with psycopg.connect(migration_database_url) as connection:
        connection.execute(
            "DELETE FROM mcp_oauth_grants WHERE grant_id = %s", (grant_id,)
        )
        connection.commit()

    assert _scalar(migration_database_url, "SELECT count(*) FROM mcp_oauth_tokens") == 0
    assert _scalar(
        migration_database_url,
        "SELECT grant_id IS NULL AND consumed_time IS NOT NULL "
        "FROM mcp_oauth_authorization_requests",
    )

    with psycopg.connect(migration_database_url) as connection:
        with pytest.raises(psycopg.errors.RestrictViolation):
            connection.execute(
                "DELETE FROM mcp_oauth_clients WHERE mcp_oauth_client_id = %s",
                (client_id,),
            )

    with psycopg.connect(migration_database_url) as connection:
        connection.execute("DELETE FROM mcp_oauth_authorization_requests")
        connection.execute(
            "DELETE FROM mcp_oauth_clients WHERE mcp_oauth_client_id = %s",
            (client_id,),
        )
        connection.commit()

    assert (
        _scalar(migration_database_url, "SELECT count(*) FROM mcp_oauth_clients") == 0
    )


def test_mcp_oauth_schema_constraints(migration_database_url: str) -> None:
    execute_command(UpCommand(), database_url=migration_database_url)
    with psycopg.connect(migration_database_url) as connection:
        user_id, client_id, grant_id = _insert_mcp_oauth_fixture(connection)
        connection.commit()

    grant_insert = (
        "INSERT INTO mcp_oauth_grants ("
        "grant_key, mcp_oauth_client_id, user_id, scopes, resource, expires_time"
        ") VALUES (%s, %s, %s, %s, %s, %s)"
    )
    read_resource = "https://app.localhost/api/mcp/read"
    expires = datetime.now(UTC) + timedelta(days=30)
    client_insert = (
        "INSERT INTO mcp_oauth_clients (client_id, client_name, redirect_uris) "
        "VALUES (%s, %s, %s::jsonb)"
    )
    token_insert = (
        "INSERT INTO mcp_oauth_tokens (token_hash, grant_id, kind, expires_time) "
        "VALUES (%s, %s, %s, now() + interval '1 hour')"
    )
    rejected: list[tuple[type[psycopg.Error], LiteralString, tuple[object, ...]]] = [
        (psycopg.errors.CheckViolation, token_insert, (b"t" * 32, grant_id, "id")),
        (
            psycopg.errors.CheckViolation,
            token_insert,
            (b"short", grant_id, "access"),
        ),
        (
            psycopg.errors.CheckViolation,
            grant_insert,
            (
                "grant-2",
                client_id,
                user_id,
                "schatten.read schatten.write",
                read_resource,
                expires,
            ),
        ),
        (
            psycopg.errors.CheckViolation,
            grant_insert,
            ("grant-2", client_id, user_id, "schatten.admin", read_resource, expires),
        ),
        (
            psycopg.errors.CheckViolation,
            grant_insert,
            (
                "grant-2",
                client_id,
                user_id,
                "schatten.write",
                read_resource,
                expires,
            ),
        ),
        (
            psycopg.errors.NotNullViolation,
            grant_insert,
            ("grant-2", client_id, user_id, "schatten.read", read_resource, None),
        ),
        (
            psycopg.errors.UniqueViolation,
            grant_insert,
            ("grant-1", client_id, user_id, "schatten.read", read_resource, expires),
        ),
        (
            psycopg.errors.CheckViolation,
            client_insert,
            ("client-2", "x" * 101, MCP_REDIRECT_URIS),
        ),
        (psycopg.errors.CheckViolation, client_insert, ("client-2", "Claude", "[]")),
        (
            psycopg.errors.CheckViolation,
            client_insert,
            (" \t", "Claude", MCP_REDIRECT_URIS),
        ),
        (
            psycopg.errors.CheckViolation,
            grant_insert,
            (" ", client_id, user_id, "schatten.read", read_resource, expires),
        ),
        (
            psycopg.errors.CheckViolation,
            "INSERT INTO mcp_oauth_tokens ("
            "token_hash, grant_id, kind, created_time, expires_time"
            ") VALUES (%s, %s, 'access', now(), now())",
            (b"t" * 32, grant_id),
        ),
        (
            psycopg.errors.UniqueViolation,
            client_insert,
            ("client-1", "Claude", MCP_REDIRECT_URIS),
        ),
    ]
    for error, statement, parameters in rejected:
        with psycopg.connect(migration_database_url) as connection:
            with pytest.raises(error):
                connection.execute(statement, parameters)


def test_ai_change_sets_migration_down_fully_reverses_up(
    migration_database_url: str, tmp_path: Path
) -> None:
    migrations = discover_migrations()
    migration_copy = tmp_path / "migrations_through_017"
    migration_copy.mkdir()
    for migration in migrations[:17]:
        shutil.copy2(migration.up_path, migration_copy / migration.up_name)
        shutil.copy2(migration.down_path, migration_copy / migration.down_name)
    execute_command(
        UpCommand(),
        database_url=migration_database_url,
        migrations_directory=migration_copy,
    )
    before = _schema_catalog(migration_database_url)

    execute_command(UpCommand(), database_url=migration_database_url)
    assert (
        _scalar(
            migration_database_url,
            "SELECT count(*) FROM pg_tables "
            "WHERE schemaname = current_schema() AND tablename LIKE 'ai_change_set%'",
        )
        == 2
    )

    execute_command(
        DownCommand("019_add_ai_change_set_review_channel.down.sql"),
        database_url=migration_database_url,
    )
    execute_command(
        DownCommand("018_create_ai_change_sets.down.sql"),
        database_url=migration_database_url,
    )

    assert (
        _scalar(migration_database_url, "SELECT max(version) FROM schema_migrations")
        == 17
    )
    assert _schema_catalog(migration_database_url) == before


def test_ai_change_set_review_channel_migration_backfills_and_reverses(
    migration_database_url: str, tmp_path: Path
) -> None:
    migrations = discover_migrations()
    migration_copy = tmp_path / "migrations_through_018"
    migration_copy.mkdir()
    for migration in migrations[:18]:
        shutil.copy2(migration.up_path, migration_copy / migration.up_name)
        shutil.copy2(migration.down_path, migration_copy / migration.down_name)
    execute_command(
        UpCommand(),
        database_url=migration_database_url,
        migrations_directory=migration_copy,
    )
    with psycopg.connect(migration_database_url) as connection:
        user_id, _, draft_id = _insert_ai_change_set_fixture(connection)
        reviewed = connection.execute(
            "INSERT INTO ai_change_sets ("
            "change_set_key, organisation_id, title, client_id, client_name, "
            "created_by, status, reviewed_by, reviewed_time"
            ") SELECT 'change-set-2', organisation_id, 'Plan', 'client-1', 'Claude', "
            "%s, 'rejected', %s, now() FROM ai_change_sets WHERE change_set_id = %s "
            "RETURNING change_set_id",
            (user_id, user_id, draft_id),
        ).fetchone()
        assert reviewed is not None
        connection.commit()
    before = _schema_catalog(migration_database_url)

    execute_command(UpCommand(), database_url=migration_database_url)

    with psycopg.connect(migration_database_url) as connection:
        rows = connection.execute(
            "SELECT change_set_id, reviewed_via, review_client_id, review_client_name "
            "FROM ai_change_sets ORDER BY change_set_id"
        ).fetchall()
    assert rows == [(draft_id, None, None, None), (reviewed[0], "web", None, None)]

    execute_command(
        DownCommand("019_add_ai_change_set_review_channel.down.sql"),
        database_url=migration_database_url,
    )

    assert (
        _scalar(migration_database_url, "SELECT max(version) FROM schema_migrations")
        == 18
    )
    assert _schema_catalog(migration_database_url) == before
    assert _scalar(
        migration_database_url,
        "SELECT obj_description('ai_change_sets'::regclass, 'pg_class')",
    ) == (
        "AI change sets staged through MCP. Only a human applies or rejects them. "
        "Down migration destroys this history."
    )


def _insert_ai_change_set_fixture(
    connection: psycopg.Connection[tuple[object, ...]],
) -> tuple[object, object, object]:
    user_id, _, grant_id = _insert_mcp_oauth_fixture(connection)
    organisation = connection.execute(
        "INSERT INTO organisations (organisation_key, name, created_by) "
        "VALUES ('ai-org', 'AI Org', %s) RETURNING organisation_id",
        (user_id,),
    ).fetchone()
    assert organisation is not None
    change_set = connection.execute(
        "INSERT INTO ai_change_sets ("
        "change_set_key, organisation_id, title, grant_id, client_id, client_name, "
        "created_by"
        ") VALUES ('change-set-1', %s, 'Plan', %s, 'client-1', 'Claude', %s) "
        "RETURNING change_set_id",
        (organisation[0], grant_id, user_id),
    ).fetchone()
    assert change_set is not None
    connection.execute(
        "INSERT INTO ai_change_set_operations ("
        "change_set_id, position, ref, op_type, payload"
        ") VALUES (%s, 0, '$plan', 'create_scenario', '{\"payload\": {}}'::jsonb)",
        (change_set[0],),
    )
    return user_id, grant_id, change_set[0]


def test_ai_change_set_grant_deletion_keeps_the_audit_record(
    migration_database_url: str,
) -> None:
    execute_command(UpCommand(), database_url=migration_database_url)

    with psycopg.connect(migration_database_url) as connection:
        user_id, grant_id, change_set_id = _insert_ai_change_set_fixture(connection)
        connection.commit()

    with psycopg.connect(migration_database_url) as connection:
        connection.execute(
            "DELETE FROM mcp_oauth_grants WHERE grant_id = %s", (grant_id,)
        )
        connection.commit()

    with psycopg.connect(migration_database_url) as connection:
        row = connection.execute(
            "SELECT grant_id, created_by, client_id, client_name, status "
            "FROM ai_change_sets WHERE change_set_id = %s",
            (change_set_id,),
        ).fetchone()
    assert row == (None, user_id, "client-1", "Claude", "draft")
    assert (
        _scalar(
            migration_database_url, "SELECT count(*) FROM ai_change_set_operations"
        )
        == 1
    )


def test_ai_change_set_schema_constraints(migration_database_url: str) -> None:
    execute_command(UpCommand(), database_url=migration_database_url)
    with psycopg.connect(migration_database_url) as connection:
        user_id, _, change_set_id = _insert_ai_change_set_fixture(connection)
        organisation_id = connection.execute(
            "SELECT organisation_id FROM organisations"
        ).fetchone()
        assert organisation_id is not None
        connection.commit()

    change_set_insert: LiteralString = (
        "INSERT INTO ai_change_sets ("
        "change_set_key, organisation_id, title, client_id, client_name, "
        "created_by, status, applied_result, reviewed_by, reviewed_time, review_note, "
        "reviewed_via, review_client_id, review_client_name"
        ") VALUES (%s, %s, %s, 'client-1', 'Claude', %s, %s, %s::jsonb, %s, %s, %s, "
        "%s, %s, %s)"
    )
    operation_insert: LiteralString = (
        "INSERT INTO ai_change_set_operations ("
        "change_set_id, position, ref, op_type, payload, frozen_values"
        ") VALUES (%s, %s, %s, %s, %s::jsonb, %s::jsonb)"
    )
    now = datetime.now(UTC)
    organisation = organisation_id[0]

    def change_set(**overrides: object) -> tuple[object, ...]:
        values: dict[str, object] = {
            "key": "change-set-2",
            "title": "Plan",
            "status": "draft",
            "applied_result": None,
            "reviewed_by": None,
            "reviewed_time": None,
            "review_note": None,
            "reviewed_via": None,
            "review_client_id": None,
            "review_client_name": None,
        } | overrides
        return (
            values["key"],
            organisation,
            values["title"],
            user_id,
            values["status"],
            values["applied_result"],
            values["reviewed_by"],
            values["reviewed_time"],
            values["review_note"],
            values["reviewed_via"],
            values["review_client_id"],
            values["review_client_name"],
        )

    def operation(**overrides: object) -> tuple[object, ...]:
        values: dict[str, object] = {
            "position": 1,
            "ref": None,
            "op_type": "create_node",
            "payload": "{}",
            "frozen_values": None,
        } | overrides
        return (
            change_set_id,
            values["position"],
            values["ref"],
            values["op_type"],
            values["payload"],
            values["frozen_values"],
        )

    accepted: list[tuple[LiteralString, tuple[object, ...]]] = [
        (
            change_set_insert,
            change_set(
                status="applied",
                applied_result='{"status": "applied"}',
                reviewed_by=user_id,
                reviewed_time=now,
                reviewed_via="web",
            ),
        ),
        (
            change_set_insert,
            change_set(
                key="change-set-3",
                status="rejected",
                reviewed_by=user_id,
                reviewed_time=now,
                review_note="Not now",
                reviewed_via="mcp",
                review_client_id="client-2",
                review_client_name="Claude Code",
            ),
        ),
        (
            operation_insert,
            operation(
                op_type="generate_timeserie_values", frozen_values='{"values": []}'
            ),
        ),
    ]
    for statement, parameters in accepted:
        with psycopg.connect(migration_database_url) as connection:
            connection.execute(statement, parameters)
            connection.commit()

    rejected: list[tuple[type[psycopg.Error], LiteralString, tuple[object, ...]]] = [
        (psycopg.errors.CheckViolation, change_set_insert, change_set(status="done")),
        (psycopg.errors.CheckViolation, change_set_insert, change_set(title=" ")),
        (
            psycopg.errors.CheckViolation,
            change_set_insert,
            change_set(status="applied", reviewed_by=user_id, reviewed_time=now),
        ),
        (
            psycopg.errors.CheckViolation,
            change_set_insert,
            change_set(applied_result='{"status": "applied"}'),
        ),
        (
            psycopg.errors.CheckViolation,
            change_set_insert,
            change_set(status="rejected", reviewed_by=user_id),
        ),
        (
            psycopg.errors.CheckViolation,
            change_set_insert,
            change_set(review_note="Too early"),
        ),
        (
            psycopg.errors.CheckViolation,
            change_set_insert,
            change_set(status="rejected", reviewed_by=user_id, reviewed_time=now),
        ),
        (
            psycopg.errors.CheckViolation,
            change_set_insert,
            change_set(reviewed_via="web"),
        ),
        (
            psycopg.errors.CheckViolation,
            change_set_insert,
            change_set(
                status="rejected",
                reviewed_by=user_id,
                reviewed_time=now,
                reviewed_via="chat",
            ),
        ),
        (
            psycopg.errors.CheckViolation,
            change_set_insert,
            change_set(
                status="rejected",
                reviewed_by=user_id,
                reviewed_time=now,
                reviewed_via="mcp",
            ),
        ),
        (
            psycopg.errors.CheckViolation,
            change_set_insert,
            change_set(
                status="rejected",
                reviewed_by=user_id,
                reviewed_time=now,
                reviewed_via="web",
                review_client_id="client-2",
                review_client_name="Claude Code",
            ),
        ),
        (
            psycopg.errors.CheckViolation,
            change_set_insert,
            change_set(
                status="rejected",
                reviewed_by=user_id,
                reviewed_time=now,
                reviewed_via="mcp",
                review_client_id=" ",
                review_client_name="Claude Code",
            ),
        ),
        (
            psycopg.errors.CheckViolation,
            change_set_insert,
            change_set(
                status="rejected",
                reviewed_by=user_id,
                reviewed_time=now,
                reviewed_via="mcp",
                review_client_id="client-2",
                review_client_name="x" * 101,
            ),
        ),
        (
            psycopg.errors.UniqueViolation,
            change_set_insert,
            change_set(key="change-set-1"),
        ),
        (psycopg.errors.CheckViolation, operation_insert, operation(op_type="apply")),
        (psycopg.errors.CheckViolation, operation_insert, operation(position=-1)),
        (psycopg.errors.CheckViolation, operation_insert, operation(ref="$node")),
        (
            psycopg.errors.CheckViolation,
            operation_insert,
            operation(op_type="create_scenario", ref="plan"),
        ),
        (psycopg.errors.CheckViolation, operation_insert, operation(payload="[]")),
        (
            psycopg.errors.CheckViolation,
            operation_insert,
            operation(frozen_values='{"values": []}'),
        ),
        (psycopg.errors.UniqueViolation, operation_insert, operation(position=0)),
        (
            psycopg.errors.UniqueViolation,
            operation_insert,
            operation(op_type="create_scenario", ref="$plan"),
        ),
    ]
    for error, statement, parameters in rejected:
        with psycopg.connect(migration_database_url) as connection:
            with pytest.raises(error):
                connection.execute(statement, parameters)
