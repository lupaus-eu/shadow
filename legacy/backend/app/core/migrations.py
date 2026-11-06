from __future__ import annotations

import hashlib
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, LiteralString, cast

import psycopg
from psycopg import sql

from app.core.config import get_settings

MIGRATIONS_DIRECTORY = Path(__file__).resolve().parents[3] / "db" / "migrations"
UP_NAME_PATTERN = re.compile(r"^(?P<version>\d{3})_[a-z0-9]+(?:_[a-z0-9]+)*\.sql$")
DOWN_NAME_PATTERN = re.compile(
    r"^(?P<version>\d{3})_[a-z0-9]+(?:_[a-z0-9]+)*\.down\.sql$"
)
BASELINE_VERSION_PATTERN = re.compile(r"^\d{3}$")
LOCK_SQL = """
SELECT pg_advisory_lock(
    hashtextextended(
        'shadow-schema-migrations:' || current_database() || ':' || current_schema(),
        0
    )
)
"""
UNLOCK_SQL = """
SELECT pg_advisory_unlock(
    hashtextextended(
        'shadow-schema-migrations:' || current_database() || ':' || current_schema(),
        0
    )
)
"""
CREATE_HISTORY_SQL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    filename TEXT NOT NULL UNIQUE,
    checksum TEXT NOT NULL,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""

type DbConnection = psycopg.Connection[tuple[Any, ...]]


class MigrationError(RuntimeError):
    """Raised when migration inputs or database history are unsafe."""


@dataclass(frozen=True)
class Migration:
    version: int
    up_path: Path
    down_path: Path
    checksum: str

    @property
    def up_name(self) -> str:
        return self.up_path.name

    @property
    def down_name(self) -> str:
        return self.down_path.name


@dataclass(frozen=True)
class AppliedMigration:
    version: int
    filename: str
    checksum: str


@dataclass(frozen=True)
class UpCommand:
    pass


@dataclass(frozen=True)
class DownCommand:
    filename: str


@dataclass(frozen=True)
class BaselineCommand:
    version: int


type MigrationCommand = UpCommand | DownCommand | BaselineCommand


def _checksum(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def get_psycopg_database_url(database_url: str) -> str:
    if database_url.startswith("postgresql+psycopg://"):
        return database_url.replace("postgresql+psycopg://", "postgresql://", 1)
    return database_url


def _trusted_sql(path: Path) -> sql.SQL:
    return sql.SQL(cast(LiteralString, path.read_text(encoding="utf-8")))


def discover_migrations(directory: Path = MIGRATIONS_DIRECTORY) -> list[Migration]:
    if not directory.is_dir():
        raise MigrationError(f"Migration directory does not exist: {directory}")

    up_paths: dict[int, Path] = {}
    down_paths: dict[int, Path] = {}

    for path in sorted(directory.glob("*.sql")):
        down_match = DOWN_NAME_PATTERN.fullmatch(path.name)
        up_match = UP_NAME_PATTERN.fullmatch(path.name)
        if down_match is not None:
            version = int(down_match.group("version"))
            if version in down_paths:
                raise MigrationError(f"Duplicate down migration version {version:03d}")
            down_paths[version] = path
        elif up_match is not None:
            version = int(up_match.group("version"))
            if version in up_paths:
                raise MigrationError(f"Duplicate up migration version {version:03d}")
            up_paths[version] = path
        else:
            raise MigrationError(f"Invalid migration filename: {path.name}")

    if not up_paths:
        raise MigrationError("No up migrations found")

    versions = sorted(up_paths)
    expected_versions = list(range(1, versions[-1] + 1))
    if versions != expected_versions:
        raise MigrationError(
            "Up migration versions must be contiguous and start at 001"
        )

    if set(down_paths) != set(up_paths):
        missing_down = sorted(set(up_paths) - set(down_paths))
        missing_up = sorted(set(down_paths) - set(up_paths))
        details: list[str] = []
        if missing_down:
            details.append(
                "missing down versions "
                + ", ".join(f"{version:03d}" for version in missing_down)
            )
        if missing_up:
            details.append(
                "down migrations without up versions "
                + ", ".join(f"{version:03d}" for version in missing_up)
            )
        raise MigrationError("Invalid migration pairs: " + "; ".join(details))

    migrations: list[Migration] = []
    for version in versions:
        up_path = up_paths[version]
        down_path = down_paths[version]
        expected_down_name = f"{up_path.stem}.down.sql"
        if down_path.name != expected_down_name:
            raise MigrationError(
                f"Migration {version:03d} pair stems do not match: "
                f"{up_path.name}, {down_path.name}"
            )
        migrations.append(
            Migration(
                version=version,
                up_path=up_path,
                down_path=down_path,
                checksum=_checksum(up_path),
            )
        )

    return migrations


def parse_command(arguments: Sequence[str]) -> MigrationCommand:
    if list(arguments) == ["up"]:
        return UpCommand()

    if len(arguments) == 2 and arguments[0] == "baseline":
        version_text = arguments[1]
        if BASELINE_VERSION_PATTERN.fullmatch(version_text) is None:
            raise MigrationError(
                "Baseline version must use three digits, for example 008"
            )
        return BaselineCommand(version=int(version_text))

    if len(arguments) == 1 and DOWN_NAME_PATTERN.fullmatch(arguments[0]) is not None:
        return DownCommand(filename=arguments[0])

    raise MigrationError(
        "Usage: migrate.py up | migrate.py NNN_name.down.sql | "
        "migrate.py baseline NNN"
    )


def validate_history(
    migrations: Sequence[Migration], applied: Sequence[AppliedMigration]
) -> None:
    if len(applied) > len(migrations):
        raise MigrationError("Database history contains unknown migration versions")

    for index, record in enumerate(applied):
        expected = migrations[index]
        if record.version != expected.version:
            raise MigrationError(
                "Database migration history must be a contiguous prefix of "
                "repository migrations"
            )
        if record.filename != expected.up_name:
            raise MigrationError(
                f"Migration {record.version:03d} filename drift detected"
            )
        if record.checksum != expected.checksum:
            raise MigrationError(
                f"Migration {record.version:03d} checksum drift detected"
            )


def _history_table_exists(connection: DbConnection) -> bool:
    row = connection.execute(
        "SELECT to_regclass('schema_migrations') IS NOT NULL"
    ).fetchone()
    return bool(row and row[0])


def _has_non_history_objects(connection: DbConnection) -> bool:
    row = connection.execute(
        """
        SELECT EXISTS (
            SELECT 1
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = current_schema()
              AND c.relkind IN ('r', 'p', 'v', 'm', 'S', 'f')
              AND c.relname <> 'schema_migrations'
              AND NOT EXISTS (
                  SELECT 1
                  FROM pg_depend d
                  WHERE d.objid = c.oid
                    AND d.deptype IN ('a', 'i')
              )
        )
        """
    ).fetchone()
    return bool(row and row[0])


def _create_history_table(connection: DbConnection) -> None:
    with connection.transaction():
        connection.execute(CREATE_HISTORY_SQL)


def _load_history(connection: DbConnection) -> list[AppliedMigration]:
    rows = connection.execute(
        """
        SELECT version, filename, checksum
        FROM schema_migrations
        ORDER BY version
        """
    ).fetchall()
    return [
        AppliedMigration(
            version=int(row[0]),
            filename=str(row[1]),
            checksum=str(row[2]),
        )
        for row in rows
    ]


def _find_down_migration(
    migrations: Sequence[Migration], filename: str
) -> Migration:
    for migration in migrations:
        if migration.down_name == filename:
            return migration
    raise MigrationError(f"Unknown down migration: {filename}")


def _run_up(
    connection: DbConnection,
    migrations: Sequence[Migration],
    history_exists: bool,
) -> None:
    if not history_exists:
        if _has_non_history_objects(connection):
            raise MigrationError(
                "Database has schema objects but no migration history; "
                "use 'baseline NNN' after verifying its migration level"
            )
        _create_history_table(connection)

    applied = _load_history(connection)
    if history_exists and not applied and _has_non_history_objects(connection):
        raise MigrationError(
            "Database has schema objects but no migration history; "
            "use 'baseline NNN' after verifying its migration level"
        )
    validate_history(migrations, applied)

    pending = migrations[len(applied) :]
    if not pending:
        print("No pending migrations.")
        return

    for migration in pending:
        with connection.transaction():
            connection.execute(_trusted_sql(migration.up_path))
            connection.execute(
                """
                INSERT INTO schema_migrations (version, filename, checksum)
                VALUES (%s, %s, %s)
                """,
                (migration.version, migration.up_name, migration.checksum),
            )
        print(f"Applied {migration.up_name}")


def _run_down(
    connection: DbConnection,
    migrations: Sequence[Migration],
    command: DownCommand,
    history_exists: bool,
) -> None:
    migration = _find_down_migration(migrations, command.filename)
    if not history_exists:
        raise MigrationError("Database has no migration history")

    applied = _load_history(connection)
    validate_history(migrations, applied)
    if not applied or applied[-1].version != migration.version:
        raise MigrationError(
            f"{migration.down_name} is not the latest applied migration"
        )

    with connection.transaction():
        connection.execute(_trusted_sql(migration.down_path))
        connection.execute(
            "DELETE FROM schema_migrations WHERE version = %s",
            (migration.version,),
        )
    print(f"Reverted {migration.down_name}")


def _run_baseline(
    connection: DbConnection,
    migrations: Sequence[Migration],
    command: BaselineCommand,
    history_exists: bool,
) -> None:
    target = next(
        (migration for migration in migrations if migration.version == command.version),
        None,
    )
    if target is None:
        raise MigrationError(f"Unknown baseline version: {command.version:03d}")
    if not _has_non_history_objects(connection):
        raise MigrationError("Baseline requires an existing non-empty schema")

    if history_exists:
        applied = _load_history(connection)
        if applied:
            raise MigrationError("Baseline requires empty migration history")
    else:
        _create_history_table(connection)

    selected = [
        migration for migration in migrations if migration.version <= target.version
    ]
    with connection.transaction():
        with connection.cursor() as cursor:
            cursor.executemany(
                """
                INSERT INTO schema_migrations (version, filename, checksum)
                VALUES (%s, %s, %s)
                """,
                [
                    (migration.version, migration.up_name, migration.checksum)
                    for migration in selected
                ],
            )
    print(
        f"Baselined migrations 001-{target.version:03d} without executing SQL; "
        "the operator is asserting the schema matches this level."
    )


def execute_command(
    command: MigrationCommand,
    *,
    database_url: str,
    migrations_directory: Path = MIGRATIONS_DIRECTORY,
) -> None:
    migrations = discover_migrations(migrations_directory)

    with psycopg.connect(database_url, autocommit=True) as connection:
        connection.execute(LOCK_SQL)
        try:
            history_exists = _history_table_exists(connection)
            if isinstance(command, UpCommand):
                _run_up(connection, migrations, history_exists)
            elif isinstance(command, DownCommand):
                _run_down(connection, migrations, command, history_exists)
            else:
                _run_baseline(connection, migrations, command, history_exists)
        finally:
            connection.execute(UNLOCK_SQL)


def main(arguments: Sequence[str] | None = None) -> int:
    cli_arguments = sys.argv[1:] if arguments is None else arguments
    try:
        command = parse_command(cli_arguments)
        database_url = get_psycopg_database_url(get_settings().database_url)
        execute_command(command, database_url=database_url)
    except (MigrationError, OSError, psycopg.Error) as error:
        print(f"Migration failed: {error}", file=sys.stderr)
        return 1
    return 0
