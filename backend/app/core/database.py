from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings, get_sqlalchemy_database_url

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def get_engine() -> Engine:
    global _engine

    if _engine is None:
        _engine = create_engine(
            get_sqlalchemy_database_url(get_settings()),
            pool_pre_ping=True,
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
