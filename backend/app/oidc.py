import hmac
import os
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode, urljoin, urlsplit, urlunsplit

import httpx
import jwt

from app.auth import OIDCIdentity


@dataclass(frozen=True)
class OIDCClientSettings:
    issuer: str
    client_id: str
    client_secret: str
    internal_base_url: str | None = None

    @classmethod
    def from_environment(cls) -> "OIDCClientSettings":
        return cls(
            issuer=os.getenv(
                "OIDC_ISSUER",
                "http://localhost:8190/application/o/yearclock/",
            ),
            client_id=os.getenv("OIDC_CLIENT_ID", "yearclock-local"),
            client_secret=os.getenv(
                "OIDC_CLIENT_SECRET",
                "replace-with-a-random-local-secret",
            ),
            internal_base_url=os.getenv("OIDC_INTERNAL_BASE_URL") or None,
        )


class AuthentikOIDCClient:
    def __init__(
        self,
        settings: OIDCClientSettings,
        *,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.settings = settings
        self.http_client = http_client or httpx.Client(timeout=10)
        self._metadata: dict[str, Any] | None = None

    @classmethod
    def from_environment(cls) -> "AuthentikOIDCClient":
        return cls(OIDCClientSettings.from_environment())

    def _internal_url(self, external_url: str) -> str:
        if self.settings.internal_base_url is None:
            return external_url

        issuer = urlsplit(self.settings.issuer)
        target = urlsplit(external_url)
        if (target.scheme, target.netloc) != (issuer.scheme, issuer.netloc):
            raise ValueError("OIDC metadata referenced an unexpected origin")

        internal = urlsplit(self.settings.internal_base_url)
        return urlunsplit(
            (
                internal.scheme,
                internal.netloc,
                target.path,
                target.query,
                target.fragment,
            )
        )

    def _discovery(self) -> dict[str, Any]:
        if self._metadata is None:
            discovery_url = urljoin(
                self.settings.issuer,
                ".well-known/openid-configuration",
            )
            response = self.http_client.get(
                self._internal_url(discovery_url),
                headers=self._internal_request_headers(),
            )
            response.raise_for_status()
            metadata = response.json()
            if metadata.get("issuer") != self.settings.issuer:
                raise ValueError("OIDC discovery issuer did not match configuration")
            self._metadata = metadata
        return self._metadata

    def _internal_request_headers(self) -> dict[str, str]:
        if self.settings.internal_base_url is None:
            return {}
        # Authentik builds the issuer and endpoint URLs from the request's Host and
        # scheme; the internal call is plain HTTP, so say the public scheme (it
        # trusts the forwarded scheme from the Docker network).
        issuer = urlsplit(self.settings.issuer)
        return {"Host": issuer.netloc, "X-Forwarded-Proto": issuer.scheme}

    def authorization_url(
        self,
        *,
        state: str,
        nonce: str,
        code_challenge: str,
        redirect_uri: str,
    ) -> str:
        metadata = self._discovery()
        query = urlencode(
            {
                "client_id": self.settings.client_id,
                "response_type": "code",
                "scope": "openid profile email",
                "redirect_uri": redirect_uri,
                "state": state,
                "nonce": nonce,
                "code_challenge": code_challenge,
                "code_challenge_method": "S256",
            }
        )
        return f"{metadata['authorization_endpoint']}?{query}"

    def exchange_code(
        self,
        *,
        code: str,
        code_verifier: str,
        nonce: str,
        redirect_uri: str,
    ) -> OIDCIdentity:
        metadata = self._discovery()
        token_response = self.http_client.post(
            self._internal_url(metadata["token_endpoint"]),
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "code_verifier": code_verifier,
            },
            auth=(self.settings.client_id, self.settings.client_secret),
            headers=self._internal_request_headers(),
        )
        token_response.raise_for_status()
        id_token = token_response.json()["id_token"]

        jwks_response = self.http_client.get(
            self._internal_url(metadata["jwks_uri"]),
            headers=self._internal_request_headers(),
        )
        jwks_response.raise_for_status()
        header = jwt.get_unverified_header(id_token)
        signing_jwk = next(
            (
                key
                for key in jwks_response.json()["keys"]
                if key.get("kid") == header.get("kid")
            ),
            None,
        )
        if signing_jwk is None:
            raise ValueError("OIDC signing key was not found")

        claims = jwt.decode(
            id_token,
            key=jwt.PyJWK.from_dict(signing_jwk),
            algorithms=["RS256"],
            audience=self.settings.client_id,
            issuer=self.settings.issuer,
            leeway=30,
            options={
                "require": [
                    "iss",
                    "sub",
                    "aud",
                    "exp",
                    "nonce",
                    "email",
                    "email_verified",
                ]
            },
        )
        if not hmac.compare_digest(
            str(claims["nonce"]),
            nonce,
        ):
            raise ValueError("OIDC nonce did not match the login transaction")

        return OIDCIdentity(
            issuer=str(claims["iss"]),
            subject=str(claims["sub"]),
            email=str(claims["email"]),
            email_verified=claims["email_verified"] is True,
            display_name=str(
                claims.get("name") or claims.get("preferred_username") or claims["email"]
            ),
            expires_at=int(claims["exp"]),
            id_token=id_token,
        )

    def end_session_url(self, *, post_logout_redirect_uri: str, id_token_hint: str | None = None) -> str:
        metadata = self._discovery()
        endpoint = metadata.get("end_session_endpoint") or urljoin(
            self.settings.issuer,
            "end-session/",
        )
        # Authentik accepts post_logout_redirect_uri only with the session's ID
        # token as id_token_hint (OIDC RP-initiated logout); without one, send the
        # user to Authentik's own logout page instead of a 400.
        query = {"client_id": self.settings.client_id}
        if id_token_hint:
            query.update({"id_token_hint": id_token_hint, "post_logout_redirect_uri": post_logout_redirect_uri})
        return f"{endpoint}?{urlencode(query)}"
