import hmac
import warnings
from dataclasses import dataclass
from threading import Lock
from typing import Any, Protocol, cast
from urllib.parse import urlencode, urlsplit, urlunsplit

import httpx
from authlib.common.errors import AuthlibBaseError
from authlib.deprecate import AuthlibDeprecationWarning
from authlib.integrations.httpx_client import OAuth2Client
from joserfc.errors import JoseError as JoseRfcError

with warnings.catch_warnings():
    warnings.simplefilter("ignore", AuthlibDeprecationWarning)
    from authlib.jose.errors import JoseError
    from authlib.jose.rfc7519 import JsonWebToken
    from authlib.oidc.core import CodeIDToken

from app.core.config import Settings


class OidcProviderError(Exception):
    """A generic, safe-to-handle provider or token validation failure."""


@dataclass(frozen=True)
class OidcMetadata:
    issuer: str
    authorization_endpoint: str
    token_endpoint: str
    jwks_uri: str
    end_session_endpoint: str | None


@dataclass(frozen=True)
class NormalizedClaims:
    issuer: str
    subject: str
    email: str | None
    name: str | None
    # The validated ID token, kept with the session only to send id_token_hint when the
    # person signs out (OIDC RP-initiated logout); never logged or returned.
    id_token: str | None = None


class OidcProvider(Protocol):
    def initialize(self) -> None: ...

    def authorization_url(
        self,
        *,
        state: str,
        nonce: str,
        pkce_verifier: str,
    ) -> str: ...

    def exchange_code(
        self,
        *,
        code: str,
        nonce: str,
        pkce_verifier: str,
    ) -> NormalizedClaims: ...

    def logout_url(self, *, id_token_hint: str | None = None) -> str | None: ...


class AuthlibOidcProvider:
    """OIDC network boundary; no provider token leaves this class."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._metadata: OidcMetadata | None = None
        self._jwks: dict[str, Any] | None = None
        self._lock = Lock()

    def initialize(self) -> None:
        self._get_metadata()

    def authorization_url(
        self,
        *,
        state: str,
        nonce: str,
        pkce_verifier: str,
    ) -> str:
        metadata = self._get_metadata()
        client = self._client()
        try:
            url, _ = client.create_authorization_url(
                metadata.authorization_endpoint,
                state=state,
                code_verifier=pkce_verifier,
                nonce=nonce,
                response_mode="query",
            )
        except (AuthlibBaseError, ValueError) as exc:
            raise OidcProviderError("Unable to create authorization request") from exc
        finally:
            client.close()
        return url

    def exchange_code(
        self,
        *,
        code: str,
        nonce: str,
        pkce_verifier: str,
    ) -> NormalizedClaims:
        metadata = self._get_metadata()
        client = self._client()
        try:
            token = client.fetch_token(
                self._internal_url(metadata.token_endpoint),
                code=code,
                redirect_uri=self._settings.callback_url,
                code_verifier=pkce_verifier,
                headers=self._internal_request_headers(),
            )
            client.close()
            id_token = token.get("id_token")
            if not isinstance(id_token, str) or not id_token:
                raise OidcProviderError("Provider omitted ID token")
            claims = self._validate_id_token(id_token, nonce)
            normalized = self._normalize_claims(claims)
            return NormalizedClaims(
                issuer=normalized.issuer,
                subject=normalized.subject,
                email=normalized.email,
                name=normalized.name,
                id_token=id_token,
            )
        except OidcProviderError:
            raise
        except (
            AuthlibBaseError,
            JoseError,
            JoseRfcError,
            KeyError,
            TypeError,
            ValueError,
        ) as exc:
            raise OidcProviderError("OIDC token validation failed") from exc
        finally:
            if not client.is_closed:
                client.close()

    def logout_url(self, *, id_token_hint: str | None = None) -> str | None:
        metadata = self._metadata
        if metadata is None or metadata.end_session_endpoint is None:
            return None
        # Authentik accepts post_logout_redirect_uri only together with the session's ID
        # token as id_token_hint; without one, the person lands on Authentik's own
        # sign-out page instead of a 400.
        parameters = {"client_id": self._settings.oidc_client_id}
        if id_token_hint:
            parameters["id_token_hint"] = id_token_hint
            parameters["post_logout_redirect_uri"] = self._settings.post_logout_url
        query = urlencode(parameters)
        separator = "&" if "?" in metadata.end_session_endpoint else "?"
        return f"{metadata.end_session_endpoint}{separator}{query}"

    def _client(self) -> Any:
        return OAuth2Client(
            self._settings.oidc_client_id,
            self._settings.oidc_client_secret.get_secret_value(),
            scope=" ".join(self._settings.oidc_scopes),
            redirect_uri=self._settings.callback_url,
            code_challenge_method="S256",
            token_endpoint_auth_method="client_secret_post",
            timeout=10.0,
            follow_redirects=False,
        )

    def _get_metadata(self) -> OidcMetadata:
        if self._metadata is not None:
            return self._metadata
        with self._lock:
            if self._metadata is not None:
                return self._metadata
            document = self._get_json(self._settings.oidc_discovery_url)
            if document.get("issuer") != self._settings.oidc_issuer:
                raise OidcProviderError(
                    "Discovery issuer does not match configured issuer"
                )
            metadata = OidcMetadata(
                issuer=self._required_url(document, "issuer"),
                authorization_endpoint=self._required_url(
                    document, "authorization_endpoint"
                ),
                token_endpoint=self._required_url(document, "token_endpoint"),
                jwks_uri=self._required_url(document, "jwks_uri"),
                end_session_endpoint=self._optional_url(
                    document.get("end_session_endpoint")
                ),
            )
            # Authentik serves every endpoint from the issuer's origin; the client
            # secret and the authorization code go to the token endpoint, and the ID
            # token to the end-session endpoint, so none may point elsewhere.
            issuer_origin = urlsplit(self._settings.oidc_issuer)
            elsewhere = [
                name
                for name, value in (
                    ("authorization_endpoint", metadata.authorization_endpoint),
                    ("token_endpoint", metadata.token_endpoint),
                    ("jwks_uri", metadata.jwks_uri),
                    ("end_session_endpoint", metadata.end_session_endpoint),
                )
                if value is not None
                and (urlsplit(value).scheme, urlsplit(value).netloc)
                != (issuer_origin.scheme, issuer_origin.netloc)
            ]
            if self._settings.app_environment == "production":
                endpoints = {
                    "authorization_endpoint": metadata.authorization_endpoint,
                    "token_endpoint": metadata.token_endpoint,
                    "jwks_uri": metadata.jwks_uri,
                    "end_session_endpoint": metadata.end_session_endpoint,
                }
                insecure = [
                    name
                    for name, value in endpoints.items()
                    if value is not None and urlsplit(value).scheme != "https"
                ]
                if insecure:
                    raise OidcProviderError(
                        "Production provider endpoints must use HTTPS: "
                        + ", ".join(insecure)
                    )
            if elsewhere:
                raise OidcProviderError(
                    "Provider endpoints must be on the issuer's origin: "
                    + ", ".join(elsewhere)
                )
            advertised = document.get("id_token_signing_alg_values_supported")
            if isinstance(advertised, list) and not set(
                self._settings.oidc_allowed_signing_algorithms
            ).intersection(str(value) for value in cast(list[object], advertised)):
                raise OidcProviderError(
                    "Provider does not advertise an allowed algorithm"
                )
            self._metadata = metadata
            return metadata

    def _get_jwks(self) -> dict[str, Any]:
        if self._jwks is None:
            document = self._get_json(self._get_metadata().jwks_uri)
            keys = document.get("keys")
            if not isinstance(keys, list) or not keys:
                raise OidcProviderError("Provider JWKS is invalid")
            self._jwks = document
        return self._jwks

    def _internal_url(self, url: str) -> str:
        """The address the backend itself uses for a provider URL.

        Without OIDC_INTERNAL_BASE_URL the public URL is used as it is. With it, only a
        URL on the issuer's own origin is rewritten, to the internal origin; a metadata
        URL on any other origin is refused.
        """
        base = self._settings.oidc_internal_base_url
        if not base:
            return url
        issuer = urlsplit(self._settings.oidc_issuer)
        target = urlsplit(url)
        if (target.scheme, target.netloc) != (issuer.scheme, issuer.netloc):
            raise OidcProviderError("Provider metadata referenced an unexpected origin")
        internal = urlsplit(base)
        return urlunsplit(
            (
                internal.scheme,
                internal.netloc,
                target.path,
                target.query,
                target.fragment,
            )
        )

    def _internal_request_headers(self) -> dict[str, str]:
        if not self._settings.oidc_internal_base_url:
            return {}
        # Authentik builds the issuer and the endpoint URLs from the request's Host and
        # scheme, and the internal call is plain HTTP: say the public ones (Authentik
        # trusts these headers only from the backend's address).
        issuer = urlsplit(self._settings.oidc_issuer)
        return {"Host": issuer.netloc, "X-Forwarded-Proto": issuer.scheme}

    def _get_json(self, url: str) -> dict[str, Any]:
        try:
            with httpx.Client(timeout=10.0, follow_redirects=False) as client:
                response = client.get(
                    self._internal_url(url),
                    headers={
                        "Accept": "application/json",
                        **self._internal_request_headers(),
                    },
                )
                response.raise_for_status()
                value = response.json()
        except Exception as exc:
            raise OidcProviderError("Provider metadata request failed") from exc
        if not isinstance(value, dict):
            raise OidcProviderError("Provider metadata is invalid")
        return cast(dict[str, Any], value)

    def _validate_id_token(self, token: str, nonce: str) -> dict[str, Any]:
        claims_options = {
            "iss": {"essential": True, "value": self._settings.oidc_issuer},
            "sub": {"essential": True},
            "aud": {"essential": True, "value": self._settings.oidc_client_id},
            "exp": {"essential": True},
            "iat": {"essential": True},
            "nonce": {"essential": True},
        }
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            decoder = cast(
                Any,
                JsonWebToken(list(self._settings.oidc_allowed_signing_algorithms)),
            )
            claims_params = {
                "client_id": self._settings.oidc_client_id,
            }
            try:
                claims = decoder.decode(
                    token,
                    self._get_jwks(),
                    claims_cls=CodeIDToken,
                    claims_options=claims_options,
                    claims_params=claims_params,
                )
            except (JoseError, JoseRfcError, ValueError):
                # A cached key set may be stale during normal provider rotation.
                # Refresh only after Authlib rejects signature/key selection.
                self._jwks = None
                claims = decoder.decode(
                    token,
                    self._get_jwks(),
                    claims_cls=CodeIDToken,
                    claims_options=claims_options,
                    claims_params=claims_params,
                )
            claims.validate(leeway=60)
        if claims.get("iss") != self._settings.oidc_issuer:
            raise OidcProviderError("ID token issuer mismatch")
        subject = claims.get("sub")
        returned_nonce = claims.get("nonce")
        if not isinstance(subject, str) or not subject.strip():
            raise OidcProviderError("ID token subject is invalid")
        if not isinstance(returned_nonce, str) or not hmac.compare_digest(
            returned_nonce.encode(), nonce.encode()
        ):
            raise OidcProviderError("ID token nonce mismatch")
        audience = claims.get("aud")
        if isinstance(audience, list) and len(cast(list[object], audience)) > 1:
            if claims.get("azp") != self._settings.oidc_client_id:
                raise OidcProviderError("ID token authorized party mismatch")
        if "azp" in claims and claims.get("azp") != self._settings.oidc_client_id:
            raise OidcProviderError("ID token authorized party mismatch")
        return cast(dict[str, Any], dict(claims))

    def _normalize_claims(self, claims: dict[str, Any]) -> NormalizedClaims:
        raw_email = claims.get("email")
        email = raw_email.strip().lower() if isinstance(raw_email, str) else None
        if not email:
            email = None
        if (
            self._settings.oidc_require_verified_email
            and claims.get("email_verified") is not True
        ):
            email = None
        raw_name = claims.get("name")
        name = (
            raw_name.strip() if isinstance(raw_name, str) and raw_name.strip() else None
        )
        return NormalizedClaims(
            issuer=cast(str, claims["iss"]),
            subject=cast(str, claims["sub"]),
            email=email,
            name=name,
        )

    @staticmethod
    def _required_url(document: dict[str, Any], key: str) -> str:
        value = document.get(key)
        parsed = urlsplit(value) if isinstance(value, str) else None
        if (
            parsed is None
            or parsed.scheme not in {"http", "https"}
            or not parsed.netloc
        ):
            raise OidcProviderError(f"Discovery field {key} is invalid")
        return cast(str, value)

    @staticmethod
    def _optional_url(value: object) -> str | None:
        if value is None:
            return None
        parsed = urlsplit(value) if isinstance(value, str) else None
        if (
            parsed is None
            or parsed.scheme not in {"http", "https"}
            or not parsed.netloc
        ):
            return None
        return cast(str, value)
