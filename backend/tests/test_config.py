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


@pytest.mark.parametrize(
    "origin",
    [
        "https://*.example.test",
        "https://app.example.test evil.example.test",
        "https://app.example.test,evil.example.test",
        "https://app_example.test",
        "https://app..example.test",
        "https://127.1",
        "https://0177.0.0.1",
        "https://0x7f000001",
        "https://0x7f.1",
        "https://2130706433",
        "https://app.example.test:0",
        "https://app.example.test:080",
        "https://app.example.test:65536",
    ],
)
def test_origin_requires_one_literal_host(origin: str) -> None:
    with pytest.raises(ValidationError, match="one literal hostname or IP"):
        Settings.model_validate({"PUBLIC_ORIGIN": origin})


@pytest.mark.parametrize(
    "origin",
    [
        "https://APP.Example.Test",
        "https://app.example.test:443",
        "https://[2001:0db8:0:0:0:0:0:1]",
    ],
)
def test_origin_requires_browser_canonical_serialization(origin: str) -> None:
    with pytest.raises(ValidationError, match="browser-canonical lowercase"):
        Settings.model_validate({"PUBLIC_ORIGIN": origin})


@pytest.mark.parametrize(
    "origin",
    [
        "http://localhost:5173",
        "https://app.example.test",
        "https://127.0.0.1:8443",
        "https://[2001:db8::1]:8443",
    ],
)
def test_origin_accepts_literal_dns_and_ip_hosts(origin: str) -> None:
    settings = Settings.model_validate(
        {"PUBLIC_ORIGIN": origin, "APP_ALLOWED_ORIGIN": origin}
    )

    assert settings.public_origin == origin


def test_production_origin_rejects_explicit_non_default_port() -> None:
    origin = "https://app.example.test:8443"
    with pytest.raises(ValidationError, match="must not include an explicit port"):
        Settings.model_validate(
            {
                "APP_ENV": "production",
                "PUBLIC_ORIGIN": origin,
                "APP_ALLOWED_ORIGIN": origin,
                "SESSION_COOKIE_SECURE": True,
                "TRUSTED_CADDY_PEER_CIDRS": "172.30.0.0/24",
            }
        )


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


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("OIDC_ISSUER", "https://login.microsoftonline.com/common/v2.0"),
        (
            "OIDC_DISCOVERY_URL",
            "https://login.microsoftonline.com/organizations/v2.0/"
            ".well-known/openid-configuration",
        ),
    ],
)
def test_generic_entra_authority_is_rejected(name: str, value: str) -> None:
    settings = Settings.model_validate({"APP_ENV": "development", name: value})

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
