"""Interactive, development-only admission of one designated Entra administrator."""

import re
import sys
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.v1.users.models import User
from app.api.v1.users.schemas import UserCreateRequest
from app.core.config import Settings, get_settings
from app.core.database import get_session_factory

_LOCAL_ENTRA_EMAIL_PATTERN = re.compile(
    r"^[^\s@]+@(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)"
    r"(?:\.(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?))*$"
)


class LocalAdminProvisioningError(Exception):
    """Safe operator-facing error that never includes personal input."""


@dataclass(frozen=True)
class LocalAdminProvisioningResult:
    user_id: int
    created: bool


def provision_local_admin(
    session: Session,
    settings: Settings,
    *,
    name: str,
    email: str,
) -> LocalAdminProvisioningResult:
    """Create or verify one admin without identities, sessions, or role changes."""
    if settings.app_environment != "development":
        raise LocalAdminProvisioningError(
            "Local administrator provisioning is allowed only in development."
        )

    payload = UserCreateRequest(name=name, email=email, role="admin")
    if not _LOCAL_ENTRA_EMAIL_PATTERN.fullmatch(payload.email):
        raise ValueError("Value must be a valid email address.")
    matching_users = session.scalars(
        select(User)
        .where(func.lower(User.email) == payload.email.lower())
        .with_for_update()
    ).all()
    active_users = [user for user in matching_users if user.deleted_time is None]
    deleted_users = [user for user in matching_users if user.deleted_time is not None]
    if deleted_users:
        session.rollback()
        raise LocalAdminProvisioningError(
            "A deleted account has this email. Resolve it before provisioning."
        )
    if len(active_users) > 1:
        session.rollback()
        raise LocalAdminProvisioningError(
            "More than one active account matches this email. Resolve it explicitly."
        )
    if active_users:
        existing = active_users[0]
        if existing.role != "admin":
            session.rollback()
            raise LocalAdminProvisioningError(
                "An active account has a different role; no role was changed."
            )
        session.rollback()
        return LocalAdminProvisioningResult(user_id=existing.user_id, created=False)

    user = User(name=payload.name, email=payload.email, role="admin")
    session.add(user)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise LocalAdminProvisioningError(
            "An account was added concurrently; inspect the local database and retry."
        ) from exc
    return LocalAdminProvisioningResult(user_id=user.user_id, created=True)


def main() -> int:
    if len(sys.argv) != 1:
        print(
            "This command accepts no arguments; identity input is prompted privately.",
            file=sys.stderr,
        )
        return 2
    if not sys.stdin.isatty():
        print(
            "Run this local-only provisioning command from an interactive terminal.",
            file=sys.stderr,
        )
        return 2

    settings = get_settings()
    if settings.app_environment != "development":
        print(
            "Local administrator provisioning is allowed only in development.",
            file=sys.stderr,
        )
        return 2
    confirmation = input("Type PROVISION LOCAL ADMIN to continue: ")
    if confirmation != "PROVISION LOCAL ADMIN":
        print("No changes made.", file=sys.stderr)
        return 2
    name = input("Designated administrator display name: ")
    email = input("Designated Entra email: ")
    repeated_email = input("Repeat designated Entra email: ")
    if email != repeated_email:
        print("Email confirmation did not match; no changes made.", file=sys.stderr)
        return 2

    session = get_session_factory()()
    try:
        result = provision_local_admin(session, settings, name=name, email=email)
    except (LocalAdminProvisioningError, ValueError):
        print(
            "Local administrator provisioning was not completed; inspect the local "
            "data or input and retry.",
            file=sys.stderr,
        )
        return 1
    finally:
        session.close()

    action = "Provisioned" if result.created else "Verified existing"
    print(f"{action} local administrator user id {result.user_id} with role admin.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
