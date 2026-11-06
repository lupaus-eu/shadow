import os

os.environ["APP_ENV"] = "test"


import uuid
from collections.abc import Generator
from urllib.parse import quote

import psycopg
import pytest
from psycopg import sql
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker


@pytest.fixture
def schema_database_url() -> Generator[str, None, None]:
    """A disposable migrated PostgreSQL schema (needs MIGRATION_TEST_DATABASE_URL)."""
    from app.core.migrations import UpCommand, execute_command

    base_url = os.getenv("MIGRATION_TEST_DATABASE_URL")
    if base_url is None:
        pytest.skip("MIGRATION_TEST_DATABASE_URL is not configured")

    schema_name = f"platform_test_{uuid.uuid4().hex}"
    with psycopg.connect(base_url, autocommit=True) as connection:
        connection.execute(
            sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema_name))
        )
    separator = "&" if "?" in base_url else "?"
    schema_url = f"{base_url}{separator}options={quote(f'-csearch_path={schema_name}')}"
    try:
        execute_command(UpCommand(), database_url=schema_url)
        yield schema_url
    finally:
        with psycopg.connect(base_url, autocommit=True) as connection:
            connection.execute(
                sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema_name))
            )


@pytest.fixture
def schema_session_factory(
    schema_database_url: str,
) -> Generator[sessionmaker[Session], None, None]:
    from app.core.config import Settings, get_sqlalchemy_database_url

    settings = Settings(DATABASE_URL=schema_database_url)
    engine = create_engine(get_sqlalchemy_database_url(settings))
    try:
        yield sessionmaker(bind=engine, autocommit=False, autoflush=False)
    finally:
        engine.dispose()
