import os
from functools import lru_cache

from pydantic import Field

from app.core.schemas import StrictBaseModel

DEFAULT_DATABASE_URL = "postgresql://schatten:schatten_dev_password@localhost:5432/schatten"


class Settings(StrictBaseModel):
    database_url: str = Field(
        default=DEFAULT_DATABASE_URL,
        alias="DATABASE_URL",
        description="SQLAlchemy-compatible database URL.",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings(DATABASE_URL=os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL))


def get_sqlalchemy_database_url(settings: Settings) -> str:
    if settings.database_url.startswith("postgresql://"):
        return settings.database_url.replace(
            "postgresql://",
            "postgresql+psycopg://",
            1,
        )

    if settings.database_url.startswith("postgres://"):
        return settings.database_url.replace("postgres://", "postgresql+psycopg://", 1)

    return settings.database_url
