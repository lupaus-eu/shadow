"""Operator command line: enroll Platform Users (ADR-0021).

    python -m app.platform_admin enroll --email ops@example.com --role platform_admin --role support_agent

The first platform sign-in (``/platform``) with that verified email creates the
Platform User. Enrollment never converts an existing customer account.
"""

import argparse
import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.models import PlatformEnrollment, PlatformRole, UserAccount

ROLES = ("platform_admin", "support_agent")


def enroll(session: Session, *, email: str, roles: list[str], days: int = 7, now: datetime | None = None) -> PlatformEnrollment:
    email = email.strip().lower()
    if not roles or any(role not in ROLES for role in roles):
        raise ValueError(f"roles must be chosen from {', '.join(ROLES)}")
    enrollment = PlatformEnrollment(id=uuid4(), email=email, roles=sorted(set(roles)), expires_at=(now or datetime.now(UTC)) + timedelta(days=days))
    session.add(enrollment)
    return enrollment


def grant(session: Session, *, email: str, role: str) -> None:
    """Add a role to an existing Platform User."""
    account = session.scalar(select(UserAccount).where(UserAccount.email == email, UserAccount.account_class == "platform"))
    if account is None:
        raise LookupError("no Platform User with that email")
    if role not in ROLES:
        raise ValueError(f"role must be one of {', '.join(ROLES)}")
    if session.scalar(select(PlatformRole).where(PlatformRole.user_account_id == account.id, PlatformRole.role == role)) is None:
        session.add(PlatformRole(id=uuid4(), user_account_id=account.id, role=role))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    enroll_parser = commands.add_parser("enroll", help="pre-authorize a verified email for platform roles")
    enroll_parser.add_argument("--email", required=True)
    enroll_parser.add_argument("--role", action="append", choices=ROLES, required=True)
    enroll_parser.add_argument("--days", type=int, default=7)
    grant_parser = commands.add_parser("grant", help="add a role to an existing Platform User")
    grant_parser.add_argument("--email", required=True)
    grant_parser.add_argument("--role", choices=ROLES, required=True)
    arguments = parser.parse_args()
    engine = create_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session, session.begin():
        if arguments.command == "enroll":
            item = enroll(session, email=arguments.email, roles=arguments.role, days=arguments.days)
            print(f"Enrolled {item.email} as {', '.join(item.roles)} until {item.expires_at:%Y-%m-%d}.")
        else:
            grant(session, email=arguments.email, role=arguments.role)
            print(f"Granted {arguments.role} to {arguments.email}.")


if __name__ == "__main__":
    main()
