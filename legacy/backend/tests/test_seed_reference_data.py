from pathlib import Path

import psycopg
import pytest

from app.seed_reference_data import (
    REFERENCE_JSON_PATH,
    REFERENCE_SQL_PATH,
    ReferenceDataSeedResult,
    main,
)


def test_cli_requires_database_url(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)

    assert main([]) == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "Reference data seed failed: DATABASE_URL is required.\n"


def test_cli_rejects_arguments(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["unexpected"]) == 2

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "Usage: python -m app.seed_reference_data\n"


def test_cli_reports_insert_and_noop_without_sensitive_values(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    secret_url = "postgresql://private-user:private-password@database/private"
    monkeypatch.setenv("DATABASE_URL", secret_url)

    def inserted_result(_database_url: str) -> ReferenceDataSeedResult:
        return ReferenceDataSeedResult(inserted=True)

    monkeypatch.setattr(
        "app.seed_reference_data.seed_reference_data",
        inserted_result,
    )

    assert main([]) == 0
    inserted = capsys.readouterr()
    assert inserted.out == "Reference data seed completed.\n"
    assert secret_url not in inserted.out + inserted.err

    def skipped_result(_database_url: str) -> ReferenceDataSeedResult:
        return ReferenceDataSeedResult(inserted=False)

    monkeypatch.setattr("app.seed_reference_data.seed_reference_data", skipped_result)
    assert main([]) == 0
    skipped = capsys.readouterr()
    assert "active default already exists" in skipped.out
    assert secret_url not in skipped.out + skipped.err


def test_cli_redacts_database_and_source_errors(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    secret_url = "postgresql://private-user:private-password@database/private"
    sensitive_payload = '{"private": "source payload"}'
    monkeypatch.setenv("DATABASE_URL", secret_url)

    def fail(_database_url: str) -> ReferenceDataSeedResult:
        raise psycopg.OperationalError(f"{secret_url} {sensitive_payload}")

    monkeypatch.setattr("app.seed_reference_data.seed_reference_data", fail)

    assert main([]) == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "Reference data seed failed.\n"
    assert secret_url not in captured.err
    assert sensitive_payload not in captured.err


def test_resource_paths_are_independent_of_working_directory(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)

    assert REFERENCE_SQL_PATH.is_file()
    assert REFERENCE_JSON_PATH.is_file()
