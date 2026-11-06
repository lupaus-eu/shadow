"""Verification of the access tokens Authentik issues to MCP clients (ADR-0038).

Authentik does not implement RFC 8707 resource indicators, so the audience is the client
id of the dedicated MCP provider: a token for the web provider, or for any other client,
carries a different audience and is refused.
"""

import time
from typing import Any
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx
import jwt
from mcp.server.auth.provider import AccessToken

from app.mcp_server.settings import McpSettings

JWKS_TTL_SECONDS = 300
JWKS_RETRY_SECONDS = 30


class AuthentikTokenVerifier:
    def __init__(self, settings: McpSettings, *, http_client: httpx.AsyncClient | None = None) -> None:
        self.settings = settings
        self.http_client = http_client or httpx.AsyncClient(timeout=10)
        self._keys: dict[str, Any] = {}
        self._fetched_at = 0.0

    def _url(self, path: str) -> str:
        external = urljoin(self.settings.issuer, path)
        if self.settings.internal_base_url is None:
            return external
        internal = urlsplit(self.settings.internal_base_url)
        target = urlsplit(external)
        return urlunsplit((internal.scheme, internal.netloc, target.path, target.query, ""))

    def _headers(self) -> dict[str, str]:
        if self.settings.internal_base_url is None:
            return {}
        # Authentik builds URLs from the request's Host and scheme; say the public ones.
        issuer = urlsplit(self.settings.issuer)
        return {"Host": issuer.netloc, "X-Forwarded-Proto": issuer.scheme}

    async def _signing_key(self, kid: str | None) -> Any | None:
        now = time.monotonic()
        stale = now - self._fetched_at > JWKS_TTL_SECONDS
        unknown = kid not in self._keys and now - self._fetched_at > JWKS_RETRY_SECONDS
        if stale or unknown:
            response = await self.http_client.get(self._url("jwks/"), headers=self._headers())
            response.raise_for_status()
            self._keys = {key.get("kid"): jwt.PyJWK.from_dict(key) for key in response.json()["keys"]}
            self._fetched_at = now
        return self._keys.get(kid)

    async def verify_token(self, token: str) -> AccessToken | None:
        try:
            header = jwt.get_unverified_header(token)
            key = await self._signing_key(header.get("kid"))
            if key is None:
                return None
            claims = jwt.decode(
                token,
                key=key,
                algorithms=["RS256"],
                audience=self.settings.client_id,
                issuer=self.settings.issuer,
                leeway=30,
                options={"require": ["iss", "sub", "aud", "exp"]},
            )
        except (jwt.PyJWTError, httpx.HTTPError, KeyError, ValueError):
            return None
        return AccessToken(
            token=token,
            client_id=str(claims.get("azp") or self.settings.client_id),
            scopes=str(claims.get("scope", "")).split(),
            expires_at=int(claims["exp"]),
            subject=str(claims["sub"]),
            claims={"iss": claims["iss"], "azp": claims.get("azp")},
        )
