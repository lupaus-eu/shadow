import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text


@pytest.fixture(scope="session")
def database_url() -> str:
    return os.environ.get(
        "TEST_DATABASE_URL",
        "postgresql+psycopg://shadow:shadow@localhost:8132/shadow_test",
    )


@pytest.fixture(scope="session", autouse=True)
def migrated_database(database_url: str) -> Iterator[None]:
    backend_dir = Path(__file__).resolve().parents[1]
    config = Config(backend_dir / "alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url)

    engine = create_engine(database_url)
    with engine.begin() as connection:
        # Start from an empty schema: the DROP migration of the product tables has no downgrade.
        connection.execute(text("DROP SCHEMA public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
    command.upgrade(config, "head")
    yield
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
    engine.dispose()
