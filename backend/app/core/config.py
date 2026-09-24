import os
import re
from functools import lru_cache
from ipaddress import IPv4Network, IPv6Network, ip_address, ip_network
from typing import Literal
from urllib.parse import SplitResult, urlsplit

from pydantic import Field, SecretStr, field_validator, model_validator

from app.core.schemas import StrictBaseModel

DEFAULT_DATABASE_URL = (
    "postgresql://schatten:schatten_dev_password@localhost:5432/schatten"
)
AppEnvironment = Literal["test", "development", "production"]
ORIGIN_HOST_LABEL = re.compile(
    r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$"
)
LEGACY_IPV4_LABEL = re.compile(r"^(?:0[xX][0-9A-Fa-f]+|[0-9]+)$")
LOCAL_CADDY_PEER_CIDRS = (ip_network("172.28.59.2/32"),)


class Settings(StrictBaseModel):
    database_url: str = Field(
        default=DEFAULT_DATABASE_URL,
        alias="DATABASE_URL",
        description="SQLAlchemy-compatible database URL.",
    )
    app_environment: AppEnvironment = Field(default="test", alias="APP_ENV")
    auth_configuration_present: bool = Field(
        default=True,
        alias="AUTH_CONFIGURATION_PRESENT",
        exclude=True,
    )
    oidc_discovery_url: str = Field(
        default="https://issuer.test/.well-known/openid-configuration",
        alias="OIDC_DISCOVERY_URL",
    )
    oidc_issuer: str = Field(default="https://issuer.test", alias="OIDC_ISSUER")
    oidc_client_id: str = Field(default="test-client", alias="OIDC_CLIENT_ID")
    oidc_client_secret: SecretStr = Field(
        default=SecretStr("test-secret"), alias="OIDC_CLIENT_SECRET"
    )
    oidc_scopes: tuple[str, ...] = Field(
        default=("openid", "profile", "email"), alias="OIDC_SCOPES"
    )
    oidc_callback_path: str = Field(
        default="/api/v1/auth/callback", alias="OIDC_CALLBACK_PATH"
    )
    oidc_allowed_signing_algorithms: tuple[str, ...] = Field(
        default=("RS256",), alias="OIDC_ALLOWED_SIGNING_ALGORITHMS"
    )
    oidc_require_verified_email: bool = Field(
        default=False, alias="OIDC_REQUIRE_VERIFIED_EMAIL"
    )
    public_origin: str = Field(default="http://testserver", alias="PUBLIC_ORIGIN")
    allowed_origin: str = Field(default="http://testserver", alias="APP_ALLOWED_ORIGIN")
    trusted_caddy_peer_cidrs: tuple[IPv4Network | IPv6Network, ...] = Field(
        default=(), alias="TRUSTED_CADDY_PEER_CIDRS"
    )
    session_cookie_secure: bool = Field(default=False, alias="SESSION_COOKIE_SECURE")
    auth_session_idle_timeout_seconds: int = Field(
        default=1800, alias="AUTH_SESSION_IDLE_TIMEOUT_SECONDS", ge=1
    )
    auth_session_absolute_lifetime_seconds: int = Field(
        default=28800, alias="AUTH_SESSION_ABSOLUTE_LIFETIME_SECONDS", ge=1
    )
    auth_session_activity_write_seconds: int = Field(
        default=300, alias="AUTH_SESSION_ACTIVITY_WRITE_SECONDS", ge=1
    )
    oidc_transaction_lifetime_seconds: int = Field(
        default=600, alias="OIDC_TRANSACTION_LIFETIME_SECONDS", ge=1
    )

    @field_validator("oidc_scopes", "oidc_allowed_signing_algorithms", mode="before")
    @classmethod
    def parse_space_or_comma_separated_tuple(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        separator = "," if "," in value else " "
        return tuple(item.strip() for item in value.split(separator) if item.strip())

    @field_validator("trusted_caddy_peer_cidrs", mode="before")
    @classmethod
    def parse_cidrs(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        return tuple(
            ip_network(item.strip(), strict=False)
            for item in value.split(",")
            if item.strip()
        )

    @model_validator(mode="after")
    def validate_security_values(self) -> "Settings":
        public = _validated_origin(self.public_origin, "PUBLIC_ORIGIN")
        allowed = _validated_origin(self.allowed_origin, "APP_ALLOWED_ORIGIN")
        if self.oidc_callback_path != "/api/v1/auth/callback":
            raise ValueError("OIDC_CALLBACK_PATH must be /api/v1/auth/callback")
        if len(self.oidc_scopes) != 3 or set(self.oidc_scopes) != {
            "openid",
            "profile",
            "email",
        }:
            raise ValueError(
                "OIDC_SCOPES must contain exactly openid, profile and email"
            )
        if not self.oidc_allowed_signing_algorithms or any(
            algorithm == "none" or algorithm.startswith("HS")
            for algorithm in self.oidc_allowed_signing_algorithms
        ):
            raise ValueError(
                "OIDC_ALLOWED_SIGNING_ALGORITHMS must contain only asymmetric "
                "algorithms"
            )
        if set(self.oidc_allowed_signing_algorithms) != {"RS256"}:
            raise ValueError(
                "Only RS256 is supported by the current authentication baseline"
            )
        if self.auth_session_activity_write_seconds > 300:
            raise ValueError("AUTH_SESSION_ACTIVITY_WRITE_SECONDS cannot exceed 300")
        if (
            self.auth_session_idle_timeout_seconds
            > self.auth_session_absolute_lifetime_seconds
        ):
            raise ValueError(
                "The session idle timeout cannot exceed its absolute lifetime"
            )
        if self.app_environment == "production":
            if public.scheme != "https" or allowed.scheme != "https":
                raise ValueError("Production origins must use HTTPS")
            if public.port is not None or allowed.port is not None:
                raise ValueError(
                    "Production origins must not include an explicit port"
                )
            if self.allowed_origin != self.public_origin:
                raise ValueError(
                    "Production APP_ALLOWED_ORIGIN must equal PUBLIC_ORIGIN"
                )
            if not self.session_cookie_secure:
                raise ValueError("Production session cookies must be Secure")
            if not self.trusted_caddy_peer_cidrs:
                raise ValueError("Production requires trusted Caddy peer CIDRs")
        return self

    def validate_auth_configuration(self) -> None:
        if self.app_environment == "test":
            return
        if not self.auth_configuration_present:
            raise ValueError(
                "Missing required authentication configuration; set "
                "OIDC_DISCOVERY_URL, "
                "OIDC_ISSUER, OIDC_CLIENT_ID, OIDC_CLIENT_SECRET, PUBLIC_ORIGIN and "
                "APP_ALLOWED_ORIGIN"
            )
        required = {
            "OIDC_DISCOVERY_URL": self.oidc_discovery_url,
            "OIDC_ISSUER": self.oidc_issuer,
            "OIDC_CLIENT_ID": self.oidc_client_id,
            "OIDC_CLIENT_SECRET": self.oidc_client_secret.get_secret_value(),
            "PUBLIC_ORIGIN": self.public_origin,
            "APP_ALLOWED_ORIGIN": self.allowed_origin,
        }
        missing = [name for name, value in required.items() if not value.strip()]
        if missing:
            raise ValueError(
                f"Missing required authentication configuration: {', '.join(missing)}"
            )
        if self.app_environment == "development":
            if self.public_origin != "https://app.localhost":
                raise ValueError(
                    "Development PUBLIC_ORIGIN must be https://app.localhost"
                )
            if self.allowed_origin != self.public_origin:
                raise ValueError(
                    "Development APP_ALLOWED_ORIGIN must equal PUBLIC_ORIGIN"
                )
            if not self.session_cookie_secure:
                raise ValueError("Development session cookies must be Secure")
            if self.trusted_caddy_peer_cidrs != LOCAL_CADDY_PEER_CIDRS:
                raise ValueError(
                    "Development TRUSTED_CADDY_PEER_CIDRS must be 172.28.59.2/32"
                )
        for name, value in (
            ("OIDC_DISCOVERY_URL", self.oidc_discovery_url),
            ("OIDC_ISSUER", self.oidc_issuer),
        ):
            parsed = urlsplit(value)
            if (
                parsed.scheme != "https"
                or parsed.hostname != "login.microsoftonline.com"
                or parsed.port is not None
                or parsed.username is not None
                or parsed.password is not None
                or parsed.query
                or parsed.fragment
            ):
                raise ValueError(
                    f"{name} must use the exact direct Entra HTTPS origin"
                )
            path_parts = [part for part in parsed.path.split("/") if part]
            if not path_parts or path_parts[0].lower() in {
                "common",
                "organizations",
                "consumers",
            }:
                raise ValueError(f"{name} must use a tenant-specific Entra authority")
        issuer = urlsplit(self.oidc_issuer)
        discovery = urlsplit(self.oidc_discovery_url)
        issuer_parts = [part for part in issuer.path.split("/") if part]
        if (
            len(issuer_parts) != 2
            or issuer_parts[1] != "v2.0"
            or issuer.path != f"/{issuer_parts[0]}/v2.0"
        ):
            raise ValueError("OIDC_ISSUER must contain an exact tenant and /v2.0")
        expected_discovery_path = (
            f"/{issuer_parts[0]}/v2.0/.well-known/openid-configuration"
        )
        if discovery.path != expected_discovery_path:
            raise ValueError(
                "OIDC_DISCOVERY_URL must match the exact tenant-specific issuer"
            )

    @property
    def public_host(self) -> str:
        return urlsplit(self.public_origin).netloc

    @property
    def callback_url(self) -> str:
        return f"{self.public_origin}{self.oidc_callback_path}"

    @property
    def post_logout_url(self) -> str:
        return f"{self.public_origin}/login"

    @property
    def session_cookie_name(self) -> str:
        return (
            "__Host-schatten-session"
            if self.session_cookie_secure
            else "schatten-session"
        )


@lru_cache
def get_settings() -> Settings:
    names = (
        "APP_ENV",
        "DATABASE_URL",
        "OIDC_DISCOVERY_URL",
        "OIDC_ISSUER",
        "OIDC_CLIENT_ID",
        "OIDC_CLIENT_SECRET",
        "OIDC_SCOPES",
        "OIDC_CALLBACK_PATH",
        "OIDC_ALLOWED_SIGNING_ALGORITHMS",
        "OIDC_REQUIRE_VERIFIED_EMAIL",
        "PUBLIC_ORIGIN",
        "APP_ALLOWED_ORIGIN",
        "TRUSTED_CADDY_PEER_CIDRS",
        "SESSION_COOKIE_SECURE",
        "AUTH_SESSION_IDLE_TIMEOUT_SECONDS",
        "AUTH_SESSION_ABSOLUTE_LIFETIME_SECONDS",
        "AUTH_SESSION_ACTIVITY_WRITE_SECONDS",
        "OIDC_TRANSACTION_LIFETIME_SECONDS",
    )
    environment = os.getenv("APP_ENV", "development")
    required_auth_names = (
        "OIDC_DISCOVERY_URL",
        "OIDC_ISSUER",
        "OIDC_CLIENT_ID",
        "OIDC_CLIENT_SECRET",
        "PUBLIC_ORIGIN",
        "APP_ALLOWED_ORIGIN",
    )
    values: dict[str, str | bool] = {
        "APP_ENV": environment,
        "DATABASE_URL": os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL),
        "AUTH_CONFIGURATION_PRESENT": environment == "test"
        or all(os.getenv(name, "").strip() for name in required_auth_names),
    }
    values.update(
        {name: value for name in names if (value := os.getenv(name)) is not None}
    )
    return Settings.model_validate(values)


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


def _validated_origin(value: str, name: str) -> SplitResult:
    error_message = (
        f"{name} must be an HTTP(S) origin with one literal hostname or IP "
        "and an optional valid port"
    )
    if "%" in value or any(
        character.isspace() or ord(character) < 32 or ord(character) == 127
        for character in value
    ):
        raise ValueError(error_message)

    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname
        port = parsed.port
    except ValueError as error:
        raise ValueError(error_message) from error

    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.path
        or parsed.query
        or parsed.fragment
        or parsed.username is not None
        or parsed.password is not None
        or hostname is None
        or not _is_literal_origin_host(hostname)
        or port == 0
    ):
        raise ValueError(error_message)

    try:
        address = ip_address(hostname)
    except ValueError:
        serialized_host = hostname
        canonical_host = hostname.casefold()
    else:
        serialized_host = f"[{hostname}]" if address.version == 6 else hostname
        canonical_address = address.compressed
        canonical_host = (
            f"[{canonical_address}]" if address.version == 6 else canonical_address
        )
    if port is not None:
        serialized_host = f"{serialized_host}:{port}"
        canonical_host = f"{canonical_host}:{port}"
    if parsed.netloc.casefold() != serialized_host.casefold():
        raise ValueError(error_message)

    default_port = 80 if parsed.scheme == "http" else 443
    if port == default_port:
        canonical_host = canonical_host.rsplit(":", 1)[0]
    canonical_origin = f"{parsed.scheme}://{canonical_host}"
    if value != canonical_origin:
        raise ValueError(
            f"{name} must use its browser-canonical lowercase serialization"
        )

    return parsed


def _is_literal_origin_host(hostname: str) -> bool:
    try:
        ip_address(hostname)
    except ValueError:
        labels = hostname.split(".")
        if all(LEGACY_IPV4_LABEL.fullmatch(label) is not None for label in labels):
            return False
        return len(hostname) <= 253 and all(
            ORIGIN_HOST_LABEL.fullmatch(label) is not None
            for label in labels
        )
    return True
