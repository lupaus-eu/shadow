# pyright: reportPrivateUsage=false

import hmac
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from authlib.jose import JsonWebKey
from authlib.jose.errors import JoseError
from authlib.jose.rfc7519 import JsonWebToken
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from joserfc.errors import JoseError as JoseRfcError

import app.api.v1.auth.provider as provider_module
from app.api.v1.auth.provider import (
    AuthlibOidcProvider,
    OidcMetadata,
    OidcProviderError,
)
from app.core.config import Settings


@pytest.fixture(scope="module")
def signing_material() -> tuple[bytes, dict[str, object]]:
    return _generate_signing_material()


def _generate_signing_material(
    key_id: str = "generated-test-key",
) -> tuple[bytes, dict[str, object]]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    public_pem = private_key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    key_importer = cast(Any, JsonWebKey)
    public_jwk = key_importer.import_key(
        public_pem,
        {"kid": key_id, "use": "sig"},
    ).as_dict()
    return private_pem, {"keys": [cast(object, public_jwk)]}


def _token(
    private_key: Any,
    *,
    algorithm: str = "RS256",
    key_id: str = "generated-test-key",
    overrides: dict[str, object] | None = None,
) -> str:
    now = datetime.now(UTC)
    payload: dict[str, object] = {
        "iss": "https://issuer.test",
        "sub": "subject-1",
        "aud": "test-client",
        "exp": int((now + timedelta(minutes=5)).timestamp()),
        "iat": int(now.timestamp()),
        "nonce": "expected-nonce",
        "email": " User@Example.COM ",
        "name": " Example User ",
        "email_verified": True,
    }
    payload.update(overrides or {})
    encoder = cast(Any, JsonWebToken([algorithm]))
    encoded = encoder.encode(
        {"alg": algorithm, "kid": key_id},
        payload,
        private_key,
    )
    return encoded.decode()


def _provider(
    jwks: dict[str, object], **settings_values: object
) -> AuthlibOidcProvider:
    settings = Settings.model_validate(settings_values)
    provider = AuthlibOidcProvider(settings)
    provider._jwks = jwks
    return provider


def test_generated_rs256_token_is_validated_and_normalized(
    signing_material: tuple[bytes, dict[str, object]],
) -> None:
    private_key, jwks = signing_material
    provider = _provider(jwks, OIDC_REQUIRE_VERIFIED_EMAIL=True)

    claims = provider._validate_id_token(_token(private_key), "expected-nonce")
    normalized = provider._normalize_claims(claims)

    assert normalized.issuer == "https://issuer.test"
    assert normalized.subject == "subject-1"
    assert normalized.email == "user@example.com"
    assert normalized.name == "Example User"


@pytest.mark.parametrize(
    ("overrides", "nonce"),
    [
        ({"iss": "https://other-issuer.test"}, "expected-nonce"),
        ({"aud": "other-client"}, "expected-nonce"),
        ({"sub": " "}, "expected-nonce"),
        ({"nonce": "swapped-nonce"}, "expected-nonce"),
        (
            {"exp": int((datetime.now(UTC) - timedelta(minutes=5)).timestamp())},
            "expected-nonce",
        ),
        (
            {"aud": ["test-client", "other"], "azp": "other-client"},
            "expected-nonce",
        ),
    ],
)
def test_invalid_id_token_claims_fail_closed(
    signing_material: tuple[bytes, dict[str, object]],
    overrides: dict[str, object],
    nonce: str,
) -> None:
    private_key, jwks = signing_material
    provider = _provider(jwks)

    with pytest.raises((JoseError, JoseRfcError, OidcProviderError)):
        provider._validate_id_token(_token(private_key, overrides=overrides), nonce)


def test_nonce_mismatch_uses_constant_time_comparison(
    signing_material: tuple[bytes, dict[str, object]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    private_key, jwks = signing_material
    provider = _provider(jwks)
    comparisons: list[tuple[bytes, bytes]] = []
    original_compare_digest = hmac.compare_digest

    def tracked_compare_digest(left: bytes, right: bytes) -> bool:
        comparisons.append((left, right))
        return original_compare_digest(left, right)

    monkeypatch.setattr(
        provider_module.hmac,
        "compare_digest",
        tracked_compare_digest,
    )

    with pytest.raises(OidcProviderError, match="nonce mismatch"):
        provider._validate_id_token(
            _token(private_key, overrides={"nonce": "wrong-nonce"}),
            "expected-nonce",
        )

    assert (b"wrong-nonce", b"expected-nonce") in comparisons


def test_unconfigured_symmetric_algorithm_is_rejected() -> None:
    secret = b"a-secret-long-enough-for-the-test"
    now = datetime.now(UTC)
    encoder = cast(Any, JsonWebToken(["HS256"]))
    token = encoder.encode(
        {"alg": "HS256", "kid": "symmetric"},
        {
            "iss": "https://issuer.test",
            "sub": "subject",
            "aud": "test-client",
            "exp": int((now + timedelta(minutes=5)).timestamp()),
            "iat": int(now.timestamp()),
            "nonce": "expected-nonce",
        },
        secret,
    ).decode()
    provider = _provider(
        {"keys": [{"kty": "oct", "kid": "symmetric", "k": "YS1zZWNyZXQ"}]}
    )

    with pytest.raises((JoseError, JoseRfcError, OidcProviderError)):
        provider._validate_id_token(token, "expected-nonce")


def test_verified_email_policy_is_configuration_only() -> None:
    claims = {
        "iss": "https://issuer.test",
        "sub": "subject",
        "email": "user@example.com",
        "email_verified": False,
    }

    assert (
        _provider({"keys": [{}]})._normalize_claims(claims).email == "user@example.com"
    )
    assert (
        _provider({"keys": [{}]}, OIDC_REQUIRE_VERIFIED_EMAIL=True)
        ._normalize_claims(claims)
        .email
        is None
    )


def test_discovery_issuer_must_equal_independently_configured_issuer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = AuthlibOidcProvider(Settings())

    def discovery(_: str) -> dict[str, object]:
        return {
            "issuer": "https://attacker.test",
            "authorization_endpoint": "https://issuer.test/authorize",
            "token_endpoint": "https://issuer.test/token",
            "jwks_uri": "https://issuer.test/jwks",
        }

    monkeypatch.setattr(
        provider,
        "_get_json",
        discovery,
    )

    with pytest.raises(OidcProviderError):
        provider.initialize()


def test_discovery_uses_an_unauthenticated_http_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[httpx.Request] = []
    http_client = httpx.Client

    def discovery(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "issuer": "https://issuer.test",
                "authorization_endpoint": "https://issuer.test/authorize",
                "token_endpoint": "https://issuer.test/token",
                "jwks_uri": "https://issuer.test/jwks",
            },
        )

    def client(**_: object) -> httpx.Client:
        return http_client(transport=httpx.MockTransport(discovery))

    monkeypatch.setattr(provider_module.httpx, "Client", client)
    provider = AuthlibOidcProvider(Settings())

    provider.initialize()

    assert len(requests) == 1
    assert str(requests[0].url) == Settings().oidc_discovery_url
    assert "authorization" not in requests[0].headers
    assert requests[0].headers["accept"] == "application/json"


@pytest.mark.parametrize(
    "endpoint_name",
    [
        "authorization_endpoint",
        "token_endpoint",
        "jwks_uri",
        "end_session_endpoint",
    ],
)
def test_production_discovery_rejects_insecure_provider_endpoints(
    endpoint_name: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings.model_validate(
        {
            "APP_ENV": "production",
            "PUBLIC_ORIGIN": "https://app.example.test",
            "APP_ALLOWED_ORIGIN": "https://app.example.test",
            "SESSION_COOKIE_SECURE": True,
            "TRUSTED_CADDY_PEER_CIDRS": "10.0.0.0/8",
        }
    )
    provider = AuthlibOidcProvider(settings)
    document: dict[str, object] = {
        "issuer": "https://issuer.test",
        "authorization_endpoint": "https://issuer.test/authorize",
        "token_endpoint": "https://issuer.test/token",
        "jwks_uri": "https://issuer.test/jwks",
        "end_session_endpoint": "https://issuer.test/logout",
    }
    document[endpoint_name] = f"http://issuer.test/{endpoint_name}"

    def discovery(_: str) -> dict[str, object]:
        return document

    monkeypatch.setattr(provider, "_get_json", discovery)

    with pytest.raises(OidcProviderError, match="must use HTTPS"):
        provider.initialize()


def test_authorization_request_uses_fixed_callback_nonce_and_s256_pkce() -> None:
    provider = AuthlibOidcProvider(Settings())
    provider._metadata = OidcMetadata(
        issuer="https://issuer.test",
        authorization_endpoint="https://issuer.test/authorize",
        token_endpoint="https://issuer.test/token",
        jwks_uri="https://issuer.test/jwks",
        end_session_endpoint="https://issuer.test/logout",
    )

    url = provider.authorization_url(
        state="fixed-state",
        nonce="fixed-nonce",
        pkce_verifier="v" * 64,
    )
    query = parse_qs(urlsplit(url).query)

    assert query["response_type"] == ["code"]
    assert query["response_mode"] == ["query"]
    assert query["redirect_uri"] == ["http://testserver/api/v1/auth/callback"]
    assert query["state"] == ["fixed-state"]
    assert query["nonce"] == ["fixed-nonce"]
    assert query["code_challenge_method"] == ["S256"]
    assert query["code_challenge"] != ["v" * 64]

    logout_url = provider.logout_url()
    assert logout_url is not None
    logout_query = parse_qs(urlsplit(logout_url).query)
    assert logout_query == {
        "client_id": ["test-client"],
        "post_logout_redirect_uri": ["http://testserver/login"],
    }


def test_jwks_is_refreshed_once_for_normal_signing_key_rotation(
    signing_material: tuple[bytes, dict[str, object]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, old_jwks = signing_material
    new_private_key, new_jwks = _generate_signing_material("rotated-key")
    provider = _provider(old_jwks)
    provider._metadata = OidcMetadata(
        issuer="https://issuer.test",
        authorization_endpoint="https://issuer.test/authorize",
        token_endpoint="https://issuer.test/token",
        jwks_uri="https://issuer.test/jwks",
        end_session_endpoint=None,
    )
    fetches = 0

    def refreshed_jwks(_: str) -> dict[str, Any]:
        nonlocal fetches
        fetches += 1
        return cast(dict[str, Any], new_jwks)

    monkeypatch.setattr(provider, "_get_json", refreshed_jwks)

    claims = provider._validate_id_token(
        _token(new_private_key, key_id="rotated-key"),
        "expected-nonce",
    )

    assert claims["sub"] == "subject-1"
    assert fetches == 1
