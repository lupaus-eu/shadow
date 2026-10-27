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
    settings = Settings.model_validate(
        {
            "APP_ENV": "development",
            "PUBLIC_ORIGIN": "https://app.localhost",
            "APP_ALLOWED_ORIGIN": "https://app.localhost",
            "SESSION_COOKIE_SECURE": True,
            "TRUSTED_CADDY_PEER_CIDRS": "172.28.59.2/32",
            "OIDC_ISSUER": "https://login.microsoftonline.com/tenant-id/v2.0",
            "OIDC_DISCOVERY_URL": "https://login.microsoftonline.com/tenant-id/v2.0/.well-known/openid-configuration",
            name: value,
        }
    )

    with pytest.raises(ValueError, match="tenant-specific"):
        settings.validate_auth_configuration()


def test_development_requires_local_https_caddy_boundary() -> None:
    settings = Settings.model_validate(
        {
            "APP_ENV": "development",
            "PUBLIC_ORIGIN": "https://app.example.test",
            "APP_ALLOWED_ORIGIN": "https://app.example.test",
            "SESSION_COOKIE_SECURE": True,
            "TRUSTED_CADDY_PEER_CIDRS": "172.28.59.2/32",
        }
    )

    with pytest.raises(ValueError, match="https://app.localhost"):
        settings.validate_auth_configuration()


def test_development_requires_exact_direct_entra_discovery() -> None:
    settings = Settings.model_validate(
        {
            "APP_ENV": "development",
            "PUBLIC_ORIGIN": "https://app.localhost",
            "APP_ALLOWED_ORIGIN": "https://app.localhost",
            "SESSION_COOKIE_SECURE": True,
            "TRUSTED_CADDY_PEER_CIDRS": "172.28.59.2/32",
            "OIDC_ISSUER": "https://login.microsoftonline.com/tenant-id/v2.0",
            "OIDC_DISCOVERY_URL": "https://login.microsoftonline.com/other/v2.0/.well-known/openid-configuration",
        }
    )

    with pytest.raises(ValueError, match="must match"):
        settings.validate_auth_configuration()


@pytest.mark.parametrize(
    "name,value",
    [
        (
            "OIDC_DISCOVERY_URL",
            "https://provider.example.test/tenant-id/v2.0/.well-known/openid-configuration",
        ),
        (
            "OIDC_ISSUER",
            "https://login.microsoftonline.com:444/tenant-id/v2.0",
        ),
    ],
)
def test_development_rejects_noncanonical_entra_origins(
    name: str, value: str
) -> None:
    settings = Settings.model_validate(
        {
            "APP_ENV": "development",
            "PUBLIC_ORIGIN": "https://app.localhost",
            "APP_ALLOWED_ORIGIN": "https://app.localhost",
            "SESSION_COOKIE_SECURE": True,
            "TRUSTED_CADDY_PEER_CIDRS": "172.28.59.2/32",
            "OIDC_ISSUER": "https://login.microsoftonline.com/tenant-id/v2.0",
            "OIDC_DISCOVERY_URL": "https://login.microsoftonline.com/tenant-id/v2.0/.well-known/openid-configuration",
            name: value,
        }
    )

    with pytest.raises(ValueError, match="exact direct Entra HTTPS origin"):
        settings.validate_auth_configuration()


def test_development_rejects_broad_caddy_peer_trust() -> None:
    settings = Settings.model_validate(
        {
            "APP_ENV": "development",
            "PUBLIC_ORIGIN": "https://app.localhost",
            "APP_ALLOWED_ORIGIN": "https://app.localhost",
            "SESSION_COOKIE_SECURE": True,
            "TRUSTED_CADDY_PEER_CIDRS": "172.28.59.0/24",
        }
    )

    with pytest.raises(ValueError, match="172.28.59.2/32"):
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


def test_mcp_is_disabled_by_default_with_the_adr_015_allowlist() -> None:
    settings = Settings()

    assert settings.mcp_enabled is False
    assert settings.mcp_oauth_redirect_uris == (
        "https://claude.ai/api/mcp/auth_callback",
        "https://claude.com/api/mcp/auth_callback",
        "http://127.0.0.1:{port}/callback",
        "http://[::1]:{port}/callback",
        "http://localhost:{port}/callback",
    )
    assert settings.mcp_oauth_authorization_request_lifetime_seconds == 600
    assert settings.mcp_oauth_authorization_code_lifetime_seconds == 60
    assert settings.mcp_oauth_access_token_lifetime_seconds == 3600
    assert settings.mcp_oauth_refresh_token_idle_lifetime_seconds == 7 * 86400
    assert settings.mcp_oauth_grant_lifetime_seconds == 30 * 86400
    assert settings.mcp_oauth_max_pending_requests_per_client == 20
    assert settings.mcp_oauth_max_pending_requests == 1000
    assert settings.mcp_oauth_max_clients == 10_000
    assert settings.mcp_tool_concurrency == 4
    assert settings.mcp_rate_limit_per_minute == 120


@pytest.mark.parametrize(
    "overrides",
    [
        {"MCP_TOOL_CONCURRENCY": 0},
        {"MCP_TOOL_CONCURRENCY": 65},
        {"MCP_RATE_LIMIT_PER_MINUTE": 0},
    ],
)
def test_mcp_resource_limits_are_bounded(overrides: dict[str, int]) -> None:
    with pytest.raises(ValidationError):
        Settings.model_validate(overrides)


def test_mcp_settings_are_read_from_the_environment(monkeypatch: MonkeyPatch) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("MCP_ENABLED", "true")
    monkeypatch.setenv(
        "MCP_OAUTH_REDIRECT_URIS",
        "https://claude.ai/api/mcp/auth_callback http://[::1]:{port}/callback",
    )
    monkeypatch.setenv("MCP_OAUTH_MAX_CLIENTS", "5")
    monkeypatch.setenv("MCP_OAUTH_ACCESS_TOKEN_LIFETIME_SECONDS", "600")
    monkeypatch.setenv("MCP_OAUTH_REFRESH_TOKEN_IDLE_LIFETIME_SECONDS", "3600")
    monkeypatch.setenv("MCP_OAUTH_GRANT_LIFETIME_SECONDS", "86400")
    monkeypatch.setenv("MCP_TOOL_CONCURRENCY", "2")
    monkeypatch.setenv("MCP_RATE_LIMIT_PER_MINUTE", "30")

    settings = get_settings()

    assert settings.mcp_enabled is True
    assert settings.mcp_oauth_redirect_uris == (
        "https://claude.ai/api/mcp/auth_callback",
        "http://[::1]:{port}/callback",
    )
    assert settings.mcp_oauth_max_clients == 5
    assert settings.mcp_oauth_access_token_lifetime_seconds == 600
    assert settings.mcp_oauth_refresh_token_idle_lifetime_seconds == 3600
    assert settings.mcp_oauth_grant_lifetime_seconds == 86400
    assert settings.mcp_tool_concurrency == 2
    assert settings.mcp_rate_limit_per_minute == 30
    get_settings.cache_clear()


@pytest.mark.parametrize(
    "entry",
    [
        "http://claude.ai/api/mcp/auth_callback",
        "https://claude.ai/api/mcp/auth_callback?x=1",
        "https://claude.ai/api/mcp/auth_callback#x",
        "https://user@claude.ai/api/mcp/auth_callback",
        "https://claude.ai",
        "https://claude.ai:99999/callback",
        "https://claude.ai/*",
        "http://evil.example:{port}/callback",
        "https://127.0.0.1:{port}/callback",
        "http://127.0.0.1:{port}",
        "http://127.0.0.1:{port}/callback?x=1",
        "http://127.0.0.1:{port}/call%62ack",
        "http://localhost.:{port}/callback",
        "http://127.0.0.1:8080{port}/callback",
    ],
)
def test_mcp_redirect_allowlist_rejects_unsafe_entries(entry: str) -> None:
    with pytest.raises(ValidationError, match="MCP_OAUTH_REDIRECT_URIS"):
        Settings.model_validate({"MCP_OAUTH_REDIRECT_URIS": entry})


def test_mcp_pending_request_caps_must_be_consistent() -> None:
    with pytest.raises(ValidationError, match="PER_CLIENT cannot exceed"):
        Settings.model_validate(
            {
                "MCP_OAUTH_MAX_PENDING_REQUESTS_PER_CLIENT": 30,
                "MCP_OAUTH_MAX_PENDING_REQUESTS": 20,
            }
        )
    with pytest.raises(ValidationError):
        Settings.model_validate({"MCP_OAUTH_AUTHORIZATION_CODE_LIFETIME_SECONDS": 0})


@pytest.mark.parametrize(
    "overrides",
    [
        {
            "MCP_OAUTH_ACCESS_TOKEN_LIFETIME_SECONDS": 7200,
            "MCP_OAUTH_GRANT_LIFETIME_SECONDS": 3600,
        },
        {"MCP_OAUTH_REFRESH_TOKEN_IDLE_LIFETIME_SECONDS": 31 * 86400},
        {"MCP_OAUTH_ACCESS_TOKEN_LIFETIME_SECONDS": 86401},
        {"MCP_OAUTH_GRANT_LIFETIME_SECONDS": 0},
        # Values beyond a year would overflow the datetime range at issuance.
        {"MCP_OAUTH_GRANT_LIFETIME_SECONDS": 10**12},
        {
            "MCP_OAUTH_REFRESH_TOKEN_IDLE_LIFETIME_SECONDS": 10**12,
            "MCP_OAUTH_GRANT_LIFETIME_SECONDS": 10**12,
        },
        {"MCP_OAUTH_GRANT_LIFETIME_SECONDS": 365 * 86400 + 1},
    ],
)
def test_mcp_token_lifetimes_cannot_outlive_the_grant(
    overrides: dict[str, int],
) -> None:
    with pytest.raises(ValidationError):
        Settings.model_validate(overrides)
