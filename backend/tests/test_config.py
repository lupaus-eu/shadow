import pytest
from pydantic import ValidationError
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


def test_non_test_runtime_fails_closed_when_oidc_configuration_is_missing(
    monkeypatch: MonkeyPatch,
) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("APP_ENV", "development")
    for name in (
        "OIDC_DISCOVERY_URL",
        "OIDC_ISSUER",
        "OIDC_CLIENT_ID",
        "OIDC_CLIENT_SECRET",
        "PUBLIC_ORIGIN",
        "APP_ALLOWED_ORIGIN",
    ):
        monkeypatch.delenv(name, raising=False)

    with pytest.raises(ValueError, match="Missing required authentication"):
        get_settings().validate_auth_configuration()
    get_settings.cache_clear()


def test_production_requires_https_and_secure_cookie() -> None:
    with pytest.raises(ValidationError, match="Production origins must use HTTPS"):
        Settings(APP_ENV="production")


def test_symmetric_id_token_algorithms_are_configuration_errors() -> None:
    with pytest.raises(ValidationError, match="asymmetric algorithms"):
        Settings.model_validate({"OIDC_ALLOWED_SIGNING_ALGORITHMS": "HS256"})


@pytest.mark.parametrize(
    "scopes",
    [
        "openid profile",
        "openid profile email offline_access",
        "openid profile email https://graph.microsoft.com/User.Read",
    ],
)
def test_oidc_scopes_are_limited_to_identity_claims(scopes: str) -> None:
    with pytest.raises(ValidationError, match="must contain exactly"):
        Settings.model_validate({"OIDC_SCOPES": scopes})


def test_generic_entra_authority_is_rejected() -> None:
    settings = Settings.model_validate(
        {
            "APP_ENV": "development",
            "OIDC_ISSUER": "https://login.microsoftonline.com/common/v2.0",
        }
    )

    with pytest.raises(ValueError, match="tenant-specific"):
        settings.validate_auth_configuration()


def test_secure_cookie_uses_host_prefix() -> None:
    settings = Settings.model_validate(
        {
            "PUBLIC_ORIGIN": "https://app.example.test",
            "APP_ALLOWED_ORIGIN": "https://app.example.test",
            "SESSION_COOKIE_SECURE": True,
        }
    )

    assert settings.session_cookie_name == "__Host-schatten-session"
