"""Interactive, database-only first production administrator bootstrap."""

import os
import sys
from collections.abc import Sequence
from dataclasses import dataclass

import psycopg
from pydantic import ValidationError

from app.api.v1.users.schemas import (
    UserCreateRequest,
    validate_user_email_address,
)
from app.core.migrations import get_psycopg_database_url


class AdminBootstrapRefused(RuntimeError):
    """Raised when any User row already exists."""


@dataclass(frozen=True)
class AdminBootstrapResult:
    user_id: int


def bootstrap_admin(
    database_url: str,
    *,
    name: str,
    email: str,
) -> AdminBootstrapResult:
    """Create the only initial admin in a transaction locked against writers."""
    payload = UserCreateRequest(name=name, email=email, role="admin")
    validate_user_email_address(payload.email)
    normalized_url = get_psycopg_database_url(database_url)

    with psycopg.connect(normalized_url) as connection:
        with connection.transaction():
            # INSERT/UPDATE/DELETE take ROW EXCLUSIVE, which conflicts with this
            # lock. The empty-table check and insert therefore cannot race any
            # other User writer, including another bootstrap process.
            connection.execute("LOCK TABLE users IN SHARE ROW EXCLUSIVE MODE")
            populated = connection.execute(
                "SELECT EXISTS (SELECT 1 FROM users)"
            ).fetchone()
            if populated is None:
                raise RuntimeError("User-table check returned no result")
            if bool(populated[0]):
                raise AdminBootstrapRefused("The users table is not empty")

            inserted = connection.execute(
                """
                INSERT INTO users (name, email, role)
                VALUES (%s, %s, 'admin')
                RETURNING user_id
                """,
                (payload.name, payload.email),
            ).fetchone()
            if inserted is None:
                raise RuntimeError("Administrator insert returned no result")
            return AdminBootstrapResult(user_id=int(inserted[0]))


def main(arguments: Sequence[str] | None = None) -> int:
    cli_arguments = sys.argv[1:] if arguments is None else arguments
    if cli_arguments:
        print("Usage: python -m app.bootstrap_admin", file=sys.stderr)
        return 2
    if not sys.stdin.isatty():
        print(
            "Administrator bootstrap requires a private interactive terminal.",
            file=sys.stderr,
        )
        return 2

    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        print(
            "Administrator bootstrap failed: DATABASE_URL is required.",
            file=sys.stderr,
        )
        return 1

    try:
        name = input("Designated administrator display name: ")
        email = input("Designated administrator email: ")
        bootstrap_admin(database_url, name=name, email=email)
    except (EOFError, KeyboardInterrupt):
        print("\nAdministrator bootstrap cancelled.", file=sys.stderr)
        return 1
    except (ValidationError, ValueError):
        print("Administrator bootstrap failed: invalid input.", file=sys.stderr)
        return 1
    except AdminBootstrapRefused:
        print(
            "Administrator bootstrap refused: the users table is not empty.",
            file=sys.stderr,
        )
        return 1
    except (psycopg.Error, RuntimeError):
        print("Administrator bootstrap failed.", file=sys.stderr)
        return 1

    print("Administrator bootstrap completed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
