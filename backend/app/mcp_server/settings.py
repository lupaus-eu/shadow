import os
from dataclasses import dataclass


def _flag(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class McpSettings:
    """Configuration of the MCP interface (docs/architecture/api.md, ADR-0038)."""

    enabled: bool = False
    # The public address of the MCP endpoint; also the resource identifier in the metadata.
    resource_url: str = "http://localhost:8100/api/mcp"
    # The dedicated Authentik provider: its issuer, and its client id, which is the audience.
    issuer: str = "http://localhost:8190/application/o/shadow-mcp/"
    client_id: str = "shadow-mcp-local"
    # Shown to Owners and Admins on the connection page; never used to verify tokens.
    client_secret: str = ""
    # The issuer under which accounts are stored (OIDC_ISSUER); the MCP issuer is an alias of it.
    canonical_issuer: str = "http://localhost:8190/application/o/shadow/"
    internal_base_url: str | None = None

    @classmethod
    def from_environment(cls) -> "McpSettings":
        public_api = (os.getenv("PUBLIC_API_BASE_URL") or "http://localhost:8100").rstrip("/")
        return cls(
            enabled=_flag("MCP_ENABLED"),
            resource_url=os.getenv("MCP_RESOURCE_URL") or f"{public_api}/api/mcp",
            issuer=os.getenv("MCP_OIDC_ISSUER") or cls.issuer,
            client_id=os.getenv("MCP_OIDC_CLIENT_ID") or cls.client_id,
            client_secret=os.getenv("MCP_OIDC_CLIENT_SECRET", ""),
            canonical_issuer=os.getenv("OIDC_ISSUER") or cls.canonical_issuer,
            internal_base_url=os.getenv("OIDC_INTERNAL_BASE_URL") or None,
        )
