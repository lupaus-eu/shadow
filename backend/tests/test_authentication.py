from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.auth import AuthSettings, OIDCIdentity
from app.main import create_app
from app.models import AccountClass, UserAccount


class FakeOIDCClient:
    def __init__(self) -> None:
        self.authorization_request: dict[str, str] | None = None
        self.exchange_request: dict[str, str] | None = None
        self.email = "alex@example.com"
        self.email_verified = True
        self.display_name = "Alex Example"
        self.subject = "authentik-user-123"

    def authorization_url(
        self,
        *,
        state: str,
        nonce: str,
        code_challenge: str,
        redirect_uri: str,
    ) -> str:
        self.authorization_request = {
            "state": state,
            "nonce": nonce,
            "code_challenge": code_challenge,
            "redirect_uri": redirect_uri,
        }
        return (
            "https://identity.example/application/o/authorize/"
            f"?state={state}"
        )

    def exchange_code(
        self,
        *,
        code: str,
        code_verifier: str,
        nonce: str,
        redirect_uri: str,
    ) -> OIDCIdentity:
        self.exchange_request = {
            "code": code,
            "code_verifier": code_verifier,
            "nonce": nonce,
            "redirect_uri": redirect_uri,
        }
        return OIDCIdentity(
            issuer="https://identity.example/application/o/yearclock/",
            subject=self.subject,
            email=self.email,
            email_verified=self.email_verified,
            display_name=self.display_name,
            expires_at=2_000_000_000,
            id_token=f"id-token-for-{self.subject}",
        )

    def end_session_url(self, *, post_logout_redirect_uri: str, id_token_hint: str | None = None) -> str:
        return (
            "https://identity.example/application/o/yearclock/end-session/"
            f"?post_logout_redirect_uri={post_logout_redirect_uri}&id_token_hint={id_token_hint}"
        )


class MutableClock:
    def __init__(self) -> None:
        self.now = datetime(2026, 7, 29, 9, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now


def log_in(client: TestClient) -> None:
    login_response = client.get("/api/v1/auth/login", follow_redirects=False)
    state = parse_qs(urlparse(login_response.headers["location"]).query)["state"][0]
    callback_response = client.get(
        "/api/v1/auth/callback",
        params={"code": "authorization-code", "state": state},
        follow_redirects=False,
    )
    assert callback_response.status_code == 303


def test_customer_session_rejects_anonymous_access(database_url: str) -> None:
    with TestClient(create_app(database_url=database_url)) as client:
        response = client.get("/api/v1/auth/session")

    assert response.status_code == 401
    assert response.json() == {"detail": "authentication required"}


def test_oidc_callback_creates_a_customer_profile_and_session(
    database_url: str,
) -> None:
    oidc_client = FakeOIDCClient()
    application = create_app(database_url=database_url, oidc_client=oidc_client)

    with TestClient(application, base_url="http://yearclock.test") as client:
        login_response = client.get(
            "/api/v1/auth/login",
            params={"return_to": "/app"},
            follow_redirects=False,
        )
        state = parse_qs(urlparse(login_response.headers["location"]).query)["state"][0]

        callback_response = client.get(
            "/api/v1/auth/callback",
            params={"code": "authorization-code", "state": state},
            follow_redirects=False,
        )
        session_response = client.get("/api/v1/auth/session")

    assert login_response.status_code == 307
    assert oidc_client.authorization_request is not None
    assert oidc_client.authorization_request["redirect_uri"] == (
        "http://yearclock.test/api/v1/auth/callback"
    )
    assert oidc_client.authorization_request["code_challenge"]
    assert callback_response.status_code == 303
    assert callback_response.headers["location"] == "http://localhost:8173/app"
    assert session_response.status_code == 200
    assert session_response.json() == {
        "user_account": {
            "id": session_response.json()["user_account"]["id"],
            "account_class": "customer",
            "email": "alex@example.com",
            "display_name": "Alex Example",
            "locale": "en",
        }
    }
    assert oidc_client.exchange_request is not None
    assert oidc_client.exchange_request["code"] == "authorization-code"
    assert oidc_client.exchange_request["code_verifier"]
    assert oidc_client.exchange_request["nonce"]


def test_customer_can_change_the_shell_locale(database_url: str) -> None:
    application = create_app(
        database_url=database_url,
        oidc_client=FakeOIDCClient(),
    )

    with TestClient(application) as client:
        log_in(client)
        locale_response = client.patch(
            "/api/v1/auth/profile/locale",
            json={"locale": "fi"},
        )
        session_response = client.get("/api/v1/auth/session")

    assert locale_response.status_code == 200
    assert locale_response.json()["user_account"]["locale"] == "fi"
    assert session_response.json()["user_account"]["locale"] == "fi"


def test_expired_and_logged_out_sessions_are_rejected(database_url: str) -> None:
    clock = MutableClock()
    application = create_app(
        database_url=database_url,
        oidc_client=FakeOIDCClient(),
        clock=clock,
        auth_settings=AuthSettings(session_max_age=timedelta(minutes=5)),
    )

    with TestClient(application) as client:
        log_in(client)
        logout_response = client.post(
            "/api/v1/auth/logout",
            follow_redirects=False,
        )
        after_logout = client.get("/api/v1/auth/session")

        log_in(client)
        clock.now += timedelta(minutes=6)
        after_expiry = client.get("/api/v1/auth/session")

    assert logout_response.status_code == 303
    assert logout_response.headers["location"].startswith(
        "https://identity.example/application/o/yearclock/end-session/"
    )
    assert "id_token_hint=id-token-for-" in logout_response.headers["location"]
    with application.state.database_engine.connect() as connection:
        stored_hints = connection.execute(text("SELECT id_token_hint FROM user_sessions WHERE revoked_at IS NOT NULL")).scalars().all()
    assert stored_hints and all(hint is None for hint in stored_hints)
    assert after_logout.status_code == 401
    assert after_expiry.status_code == 401


def test_profile_linkage_uses_issuer_and_subject_and_requires_verified_email(
    database_url: str,
) -> None:
    oidc_client = FakeOIDCClient()
    application = create_app(database_url=database_url, oidc_client=oidc_client)

    with TestClient(application) as client:
        log_in(client)
        original_profile = client.get("/api/v1/auth/session").json()["user_account"]

        oidc_client.email = "alex.new@example.com"
        oidc_client.display_name = "Alex New"
        log_in(client)
        updated_profile = client.get("/api/v1/auth/session").json()["user_account"]

        oidc_client.email_verified = False
        login_response = client.get("/api/v1/auth/login", follow_redirects=False)
        state = parse_qs(urlparse(login_response.headers["location"]).query)["state"][0]
        unverified_callback = client.get(
            "/api/v1/auth/callback",
            params={"code": "authorization-code", "state": state},
            follow_redirects=False,
        )

    assert updated_profile["id"] == original_profile["id"]
    assert updated_profile["email"] == "alex.new@example.com"
    assert updated_profile["display_name"] == "Alex New"
    assert unverified_callback.status_code == 403
    assert unverified_callback.json() == {"detail": "verified email required"}


def test_platform_identity_cannot_enter_the_customer_account_class(
    database_url: str,
) -> None:
    oidc_client = FakeOIDCClient()
    oidc_client.subject = "platform-identity"
    application = create_app(
        database_url=database_url,
        oidc_client=oidc_client,
    )
    with application.state.session_factory.begin() as session:
        session.add(
            UserAccount(
                id=uuid4(),
                oidc_issuer="https://identity.example/application/o/yearclock/",
                oidc_subject=oidc_client.subject,
                account_class=AccountClass.PLATFORM.value,
                email="operator@example.com",
                display_name="Platform Operator",
                locale="en",
            )
        )

    with TestClient(application) as client:
        login_response = client.get("/api/v1/auth/login", follow_redirects=False)
        state = parse_qs(urlparse(login_response.headers["location"]).query)["state"][0]
        callback_response = client.get(
            "/api/v1/auth/callback",
            params={"code": "authorization-code", "state": state},
            follow_redirects=False,
        )

    assert callback_response.status_code == 403
    assert callback_response.json() == {"detail": "customer account required"}
