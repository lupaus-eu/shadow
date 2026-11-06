"""Database-only production reference-data seed.

Run with ``python -m app.seed_reference_data`` after migrations. The command
loads the repository-owned default metamodel and shared SQL without importing
or starting FastAPI.
"""

import os
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import LiteralString, cast

import psycopg
from psycopg import sql

from app.core.migrations import get_psycopg_database_url

REFERENCE_DATA_DIRECTORY = Path(__file__).resolve().parents[2] / "db" / "init"
REFERENCE_SQL_PATH = REFERENCE_DATA_DIRECTORY / "001_seed_reference_data.sql"
REFERENCE_JSON_PATH = (
    REFERENCE_DATA_DIRECTORY / "metamodel_state_##default##.json"
)
REFERENCE_JSON_SETTING = "shadow.seed_reference_data.metamodel_json"

class ReferenceDataSeedError(RuntimeError):
    """Raised when the command cannot safely start a reference-data seed."""


@dataclass(frozen=True)
class ReferenceDataSeedResult:
    inserted: bool


def _trusted_sql(path: Path) -> sql.SQL:
    return sql.SQL(cast(LiteralString, path.read_text(encoding="utf-8")))


def seed_reference_data(
    database_url: str,
    *,
    sql_path: Path = REFERENCE_SQL_PATH,
    json_path: Path = REFERENCE_JSON_PATH,
) -> ReferenceDataSeedResult:
    """Insert the default metamodel once in one serialized transaction."""
    source_json = json_path.read_text(encoding="utf-8")
    seed_sql = _trusted_sql(sql_path)
    normalized_url = get_psycopg_database_url(database_url)

    with psycopg.connect(normalized_url) as connection:
        with connection.transaction():
            connection.execute(
                "SELECT set_config(%s, %s, true)",
                (REFERENCE_JSON_SETTING, source_json),
            )
            connection.execute(seed_sql)
            row = connection.execute(
                "SELECT EXISTS (SELECT 1 FROM _seed_default_metamodel)"
            ).fetchone()
            if row is None:
                raise ReferenceDataSeedError(
                    "Reference-data seed did not return an insertion result."
                )
            return ReferenceDataSeedResult(inserted=bool(row[0]))


def main(arguments: Sequence[str] | None = None) -> int:
    cli_arguments = sys.argv[1:] if arguments is None else arguments
    if cli_arguments:
        print("Usage: python -m app.seed_reference_data", file=sys.stderr)
        return 2

    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        print("Reference data seed failed: DATABASE_URL is required.", file=sys.stderr)
        return 1

    try:
        result = seed_reference_data(database_url)
    except (ReferenceDataSeedError, OSError, UnicodeError, psycopg.Error):
        print("Reference data seed failed.", file=sys.stderr)
        return 1

    if result.inserted:
        print("Reference data seed completed.")
    else:
        print("Reference data seed skipped: an active default already exists.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
