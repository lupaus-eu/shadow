import os
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings, get_sqlalchemy_database_url

APPLICATION_DATABASE_ROLE = "shadow_app"

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def get_engine() -> Engine:
    global _engine

    if _engine is None:
        _engine = create_engine(
            get_sqlalchemy_database_url(get_settings()),
            pool_pre_ping=True,
            pool_size=int(os.getenv("DATABASE_POOL_SIZE", "5")),
            max_overflow=int(os.getenv("DATABASE_MAX_OVERFLOW", "10")),
        )

    return _engine


def get_session_factory() -> sessionmaker[Session]:
    global _session_factory

    if _session_factory is None:
        _session_factory = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=get_engine(),
        )

    return _session_factory


def get_db_session() -> Generator[Session, None, None]:
    session = get_session_factory()()

    try:
        yield session
    finally:
        session.close()


@dataclass(frozen=True)
class RequestContext:
    """Who and which tenant a database transaction acts for (ADR-016).

    The values become transaction-local ``app.*`` settings that audit records
    and, later, row-level security policies read.
    """

    user_id: int | None = None
    tenant_id: UUID | None = None
    support_access_id: UUID | None = None
    invitation_token_hash: str | None = None
    worker_scope: str | None = None


def apply_request_context(session: Session, request_context: RequestContext) -> None:
    settings = {
        "app.current_user_id": request_context.user_id,
        "app.current_tenant_id": request_context.tenant_id,
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
) -> Generator[Session, None, None]:
    """One transaction under the application role with the request context set.

    Commits when the block ends and rolls back on an exception.
    """
    with session_factory() as session:
        with session.begin():
            session.execute(text(f"SET LOCAL ROLE {APPLICATION_DATABASE_ROLE}"))
            apply_request_context(session, request_context)
            yield session
