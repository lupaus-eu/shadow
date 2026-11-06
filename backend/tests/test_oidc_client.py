import json
from urllib.parse import parse_qs, urlparse

import httpx
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

from app.oidc import AuthentikOIDCClient, OIDCClientSettings


def test_authentik_client_uses_pkce_and_validates_the_id_token() -> None:
    issuer = "http://localhost:8190/application/o/yearclock/"
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private_key.public_key()))
    public_jwk.update({"kid": "yearclock-key", "use": "sig", "alg": "RS256"})
    id_token = jwt.encode(
        {
            "iss": issuer,
            "sub": "authentik-user-123",
            "aud": "yearclock-client",
            "exp": 2_000_000_000,
            "iat": 1_700_000_000,
            "nonce": "expected-nonce",
            "email": "alex@example.com",
            "email_verified": True,
            "name": "Alex Example",
        },
        private_key,
        algorithm="RS256",
        headers={"kid": "yearclock-key"},
    )

    def oidc_provider(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "authentik-server"
        assert request.headers["host"] == "localhost:8190"
        assert request.headers["x-forwarded-proto"] == "http"
        if request.url.path.endswith(".well-known/openid-configuration"):
            return httpx.Response(
                200,
                json={
                    "issuer": issuer,
                    "authorization_endpoint": (
                        "http://localhost:8190/application/o/authorize/"
                    ),
                    "token_endpoint": "http://localhost:8190/application/o/token/",
                    "jwks_uri": (
                        "http://localhost:8190/application/o/yearclock/jwks/"
                    ),
                    "end_session_endpoint": (
                        "http://localhost:8190/application/o/yearclock/end-session/"
                    ),
                },
            )
        if request.url.path == "/application/o/token/":
            assert request.headers["authorization"].startswith("Basic ")
            assert "code_verifier=pkce-verifier" in request.content.decode()
            return httpx.Response(200, json={"id_token": id_token})
        if request.url.path.endswith("/jwks/"):
            return httpx.Response(200, json={"keys": [public_jwk]})
        raise AssertionError(f"unexpected OIDC request: {request.method} {request.url}")

    client = AuthentikOIDCClient(
        OIDCClientSettings(
            issuer=issuer,
            client_id="yearclock-client",
            client_secret="client-secret",
            internal_base_url="http://authentik-server:9000",
        ),
        http_client=httpx.Client(transport=httpx.MockTransport(oidc_provider)),
    )

    authorization_url = client.authorization_url(
        state="login-state",
        nonce="expected-nonce",
        code_challenge="pkce-challenge",
        redirect_uri="http://localhost:8100/api/v1/auth/callback",
    )
    authorization_query = parse_qs(urlparse(authorization_url).query)
    identity = client.exchange_code(
        code="authorization-code",
        code_verifier="pkce-verifier",
        nonce="expected-nonce",
        redirect_uri="http://localhost:8100/api/v1/auth/callback",
    )

    assert authorization_query["response_type"] == ["code"]
    assert authorization_query["scope"] == ["openid profile email"]
    assert authorization_query["code_challenge_method"] == ["S256"]
    assert identity.issuer == issuer
    assert identity.subject == "authentik-user-123"
    assert identity.email_verified is True
    assert identity.display_name == "Alex Example"
    assert identity.id_token
    logout_query = parse_qs(urlparse(client.end_session_url(post_logout_redirect_uri="http://localhost:8173", id_token_hint=identity.id_token)).query)
    assert logout_query == {"client_id": ["yearclock-client"], "id_token_hint": [identity.id_token], "post_logout_redirect_uri": ["http://localhost:8173"]}
    without_hint = parse_qs(urlparse(client.end_session_url(post_logout_redirect_uri="http://localhost:8173")).query)
    assert without_hint == {"client_id": ["yearclock-client"]}


def test_internal_discovery_tells_authentik_the_public_https_scheme() -> None:
    issuer = "https://identity.example.com/application/o/yearclock/"
    seen: dict[str, str] = {}

    def oidc_provider(request: httpx.Request) -> httpx.Response:
        seen.update(request.headers)
        return httpx.Response(
            200,
            json={
                "issuer": issuer,
                "authorization_endpoint": "https://identity.example.com/application/o/authorize/",
            },
        )

    client = AuthentikOIDCClient(
        OIDCClientSettings(
            issuer=issuer,
            client_id="yearclock-client",
            client_secret="client-secret",
            internal_base_url="http://authentik-server:9000",
        ),
        http_client=httpx.Client(transport=httpx.MockTransport(oidc_provider)),
    )

    url = client.authorization_url(
        state="s", nonce="n", code_challenge="c", redirect_uri="https://yearclock.example.com/api/v1/auth/callback"
    )

    assert seen["host"] == "identity.example.com"
    assert seen["x-forwarded-proto"] == "https"
    assert url.startswith("https://identity.example.com/application/o/authorize/?")
