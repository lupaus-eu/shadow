import io
import sys

import psycopg
import pytest

from app.bootstrap_admin import (
    AdminBootstrapRefused,
    AdminBootstrapResult,
    bootstrap_admin,
    main,
)


class InteractiveInput(io.StringIO):
    def isatty(self) -> bool:
        return True


def test_cli_rejects_arguments_and_non_interactive_input(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["personal@example.test"]) == 2
    arguments = capsys.readouterr()
    assert arguments.out == ""
    assert arguments.err == "Usage: python -m app.bootstrap_admin\n"
    assert "personal@example.test" not in arguments.err

    monkeypatch.setattr(sys, "stdin", io.StringIO("Name\nemail@example.test\n"))
    assert main([]) == 2
    non_interactive = capsys.readouterr()
    assert non_interactive.out == ""
    assert "private interactive terminal" in non_interactive.err


def test_cli_requires_database_url_before_prompting(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(sys, "stdin", InteractiveInput())
    monkeypatch.delenv("DATABASE_URL", raising=False)

    assert main([]) == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "Administrator bootstrap failed: DATABASE_URL is required.\n"


def test_cli_reports_success_without_echoing_personal_or_database_data(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    name = "Private Person"
    email = "private.person@example.test"
    database_url = "postgresql://private-user:private-password@database/private"
    received: list[tuple[str, str, str]] = []
    monkeypatch.setattr(sys, "stdin", InteractiveInput(f"{name}\n{email}\n"))
    monkeypatch.setenv("DATABASE_URL", database_url)

    def succeed(url: str, *, name: str, email: str) -> AdminBootstrapResult:
        received.append((url, name, email))
        return AdminBootstrapResult(user_id=101)

    monkeypatch.setattr("app.bootstrap_admin.bootstrap_admin", succeed)

    assert main([]) == 0

    captured = capsys.readouterr()
    assert received == [(database_url, name, email)]
    assert captured.out.endswith("Administrator bootstrap completed.\n")
    assert name not in captured.out + captured.err
    assert email not in captured.out + captured.err
    assert database_url not in captured.out + captured.err


@pytest.mark.parametrize(
    "error, expected",
    [
        (
            AdminBootstrapRefused("private.person@example.test"),
            "Administrator bootstrap refused: the users table is not empty.\n",
        ),
        (
            psycopg.OperationalError(
                "postgresql://private-user:private-password@database/private"
            ),
            "Administrator bootstrap failed.\n",
        ),
    ],
)
def test_cli_redacts_refusal_and_database_errors(
    error: Exception,
    expected: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    name = "Private Person"
    email = "private.person@example.test"
    database_url = "postgresql://private-user:private-password@database/private"
    monkeypatch.setattr(sys, "stdin", InteractiveInput(f"{name}\n{email}\n"))
    monkeypatch.setenv("DATABASE_URL", database_url)

    def fail(_url: str, *, name: str, email: str) -> AdminBootstrapResult:
        del name, email
        raise error

    monkeypatch.setattr("app.bootstrap_admin.bootstrap_admin", fail)

    assert main([]) == 1

    captured = capsys.readouterr()
    assert captured.err == expected
    assert name not in captured.out + captured.err
    assert email not in captured.out + captured.err
    assert database_url not in captured.out + captured.err


def test_cli_rejects_blank_input_before_connecting(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        sys,
        "stdin",
        InteractiveInput("\nvalid@example.test\n"),
    )
    monkeypatch.setenv("DATABASE_URL", "postgresql://database/test")

    def should_not_connect(_url: str) -> None:
        raise AssertionError("Invalid input must not open a database connection")

    monkeypatch.setattr("app.bootstrap_admin.psycopg.connect", should_not_connect)

    assert main([]) == 1
    captured = capsys.readouterr()
    assert captured.err == "Administrator bootstrap failed: invalid input.\n"


def test_cli_interrupted_input_makes_no_bootstrap_call(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(sys, "stdin", InteractiveInput("Name\n"))
    monkeypatch.setenv("DATABASE_URL", "postgresql://database/test")
    called = False

    def should_not_run(_url: str, *, name: str, email: str) -> AdminBootstrapResult:
        del _url, name, email
        nonlocal called
        called = True
        raise AssertionError("Interrupted input must not call bootstrap")

    monkeypatch.setattr("app.bootstrap_admin.bootstrap_admin", should_not_run)

    assert main([]) == 1
    assert called is False
    captured = capsys.readouterr()
    assert captured.err.endswith("Administrator bootstrap cancelled.\n")


@pytest.mark.parametrize(
    "email",
    ["not-an-email", "person @example.test", "person@-invalid.test"],
)
def test_bootstrap_rejects_invalid_email_before_database_access(email: str) -> None:
    with pytest.raises(ValueError, match="valid email"):
        bootstrap_admin(
            "postgresql://private-user:private-password@database/private",
            name="Administrator",
            email=email,
        )
