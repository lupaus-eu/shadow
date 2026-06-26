from pytest import MonkeyPatch

from app.core.config import Settings, get_settings, get_sqlalchemy_database_url


def test_settings_reads_database_url_from_environment(monkeypatch: MonkeyPatch) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@database:5432/app")

    settings = get_settings()

    assert settings.database_url == "postgresql://user:pass@database:5432/app"

    get_settings.cache_clear()


def test_sqlalchemy_url_uses_psycopg_driver_for_postgresql_url() -> None:
    settings = Settings(DATABASE_URL="postgresql://user:pass@database:5432/app")

    assert (
        get_sqlalchemy_database_url(settings)
        == "postgresql+psycopg://user:pass@database:5432/app"
    )
