from pathlib import Path

import pytest

from app.core.migrations import (
    AppliedMigration,
    BaselineCommand,
    DownCommand,
    MigrationError,
    UpCommand,
    discover_migrations,
    get_psycopg_database_url,
    main,
    parse_command,
    validate_history,
)


def _write_pair(directory: Path, version: int, name: str) -> None:
    stem = f"{version:03d}_{name}"
    (directory / f"{stem}.sql").write_text("SELECT 1;\n", encoding="utf-8")
    (directory / f"{stem}.down.sql").write_text("SELECT 1;\n", encoding="utf-8")


def test_discovers_ordered_paired_migrations(tmp_path: Path) -> None:
    _write_pair(tmp_path, 2, "second_change")
    _write_pair(tmp_path, 1, "first_change")

    migrations = discover_migrations(tmp_path)

    assert [migration.version for migration in migrations] == [1, 2]
    assert migrations[0].up_name == "001_first_change.sql"
    assert migrations[0].down_name == "001_first_change.down.sql"
    assert len(migrations[0].checksum) == 64


@pytest.mark.parametrize(
    ("files", "message"),
    [
        (["001_first.sql"], "missing down versions 001"),
        (
            [
                "001_first.sql",
                "001_first.down.sql",
                "003_third.sql",
                "003_third.down.sql",
            ],
            "contiguous",
        ),
        (
            [
                "001_first.sql",
                "001_first.down.sql",
                "001_duplicate.sql",
                "001_duplicate.down.sql",
            ],
            "Duplicate .* migration version 001",
        ),
        (["migration.sql"], "Invalid migration filename"),
    ],
)
def test_rejects_invalid_migration_sets(
    tmp_path: Path, files: list[str], message: str
) -> None:
    for filename in files:
        (tmp_path / filename).write_text("SELECT 1;\n", encoding="utf-8")

    with pytest.raises(MigrationError, match=message):
        discover_migrations(tmp_path)


def test_rejects_pair_with_different_stems(tmp_path: Path) -> None:
    (tmp_path / "001_first.sql").write_text("SELECT 1;\n", encoding="utf-8")
    (tmp_path / "001_other.down.sql").write_text("SELECT 1;\n", encoding="utf-8")

    with pytest.raises(MigrationError, match="pair stems do not match"):
        discover_migrations(tmp_path)


def test_parses_supported_commands() -> None:
    assert parse_command(["up"]) == UpCommand()
    assert parse_command(["001_first.down.sql"]) == DownCommand("001_first.down.sql")
    assert parse_command(["baseline", "008"]) == BaselineCommand(8)


def test_normalizes_sqlalchemy_psycopg_database_url() -> None:
    assert (
        get_psycopg_database_url("postgresql+psycopg://user:pass@database/app")
        == "postgresql://user:pass@database/app"
    )
    assert (
        get_psycopg_database_url("postgresql://user:pass@database/app")
        == "postgresql://user:pass@database/app"
    )


@pytest.mark.parametrize(
    "arguments",
    [
        [],
        ["down", "001_first.down.sql"],
        ["../001_first.down.sql"],
        ["001"],
        ["baseline", "8"],
        ["up", "extra"],
    ],
)
def test_rejects_unsupported_commands(arguments: list[str]) -> None:
    with pytest.raises(MigrationError):
        parse_command(arguments)


def test_cli_returns_nonzero_for_invalid_command(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["../001_first.down.sql"]) == 1

    captured = capsys.readouterr()
    assert "Migration failed: Usage:" in captured.err
    assert captured.out == ""


def test_validates_contiguous_matching_history(tmp_path: Path) -> None:
    _write_pair(tmp_path, 1, "first")
    _write_pair(tmp_path, 2, "second")
    migrations = discover_migrations(tmp_path)
    applied = [
        AppliedMigration(
            version=migration.version,
            filename=migration.up_name,
            checksum=migration.checksum,
        )
        for migration in migrations
    ]

    validate_history(migrations, applied)


@pytest.mark.parametrize(
    ("record", "message"),
    [
        (AppliedMigration(2, "002_second.sql", "checksum"), "contiguous prefix"),
        (AppliedMigration(1, "001_renamed.sql", "checksum"), "filename drift"),
        (AppliedMigration(1, "001_first.sql", "changed"), "checksum drift"),
    ],
)
def test_rejects_invalid_history(
    tmp_path: Path, record: AppliedMigration, message: str
) -> None:
    _write_pair(tmp_path, 1, "first")
    _write_pair(tmp_path, 2, "second")
    migrations = discover_migrations(tmp_path)

    with pytest.raises(MigrationError, match=message):
        validate_history(migrations, [record])


def test_rejects_history_longer_than_repository(tmp_path: Path) -> None:
    _write_pair(tmp_path, 1, "first")
    migrations = discover_migrations(tmp_path)
    applied = [
        AppliedMigration(1, migrations[0].up_name, migrations[0].checksum),
        AppliedMigration(2, "002_unknown.sql", "checksum"),
    ]

    with pytest.raises(MigrationError, match="unknown migration versions"):
        validate_history(migrations, applied)


def test_repository_migrations_are_complete_pairs() -> None:
    migrations = discover_migrations()

    assert [migration.version for migration in migrations] == list(
        range(1, len(discover_migrations()) + 1)
    )
