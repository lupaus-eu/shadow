import os
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

APPLICATION_DATABASE_ROLE = "shadow_app"


@dataclass(frozen=True)
class RequestContext:
    user_account_id: UUID | None = None
    organization_id: UUID | None = None
    support_access_id: UUID | None = None
    invitation_token_hash: str | None = None
    worker_scope: str | None = None


def create_database_engine(database_url: str) -> Engine:
    """One pool per process; size it with DATABASE_POOL_SIZE and DATABASE_MAX_OVERFLOW."""
    return create_engine(
        database_url,
        pool_pre_ping=True,
        pool_size=int(os.getenv("DATABASE_POOL_SIZE", "5")),
        max_overflow=int(os.getenv("DATABASE_MAX_OVERFLOW", "5")),
    )


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)


def apply_request_context(session: Session, request_context: RequestContext) -> None:
    settings = {
        "app.current_user_account_id": request_context.user_account_id,
        "app.current_organization_id": request_context.organization_id,
        "app.current_support_access_id": request_context.support_access_id,
        "app.current_invitation_token_hash": request_context.invitation_token_hash,
        "app.worker_scope": request_context.worker_scope,
    }
    for name, value in settings.items():
        session.execute(
            text("SELECT set_config(:name, :value, true)"),
            {"name": name, "value": "" if value is None else str(value)},
        )


@contextmanager
def transaction_session(
    session_factory: sessionmaker[Session],
    request_context: RequestContext,
) -> Iterator[Session]:
    with session_factory() as session:
        with session.begin():
            session.execute(text(f"SET LOCAL ROLE {APPLICATION_DATABASE_ROLE}"))
            apply_request_context(session, request_context)
            yield session
