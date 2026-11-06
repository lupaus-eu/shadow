from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient

from alembic.config import Config
from alembic.script import ScriptDirectory

from app.auth import OIDCIdentity
from app.main import create_app


def _head_revision() -> str:
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    return ScriptDirectory.from_config(config).get_current_head()


class SystemStatusOIDCClient:
    def authorization_url(
        self,
        *,
        state: str,
        nonce: str,
        code_challenge: str,
        redirect_uri: str,
    ) -> str:
        return f"https://identity.example/authorize?state={state}"

    def exchange_code(
        self,
        *,
        code: str,
        code_verifier: str,
        nonce: str,
        redirect_uri: str,
    ) -> OIDCIdentity:
        return OIDCIdentity(
            issuer="https://identity.example/application/o/yearclock/",
            subject="system-status-user",
            email="status@example.com",
            email_verified=True,
            display_name="Status User",
            expires_at=int(datetime(2030, 1, 1, tzinfo=UTC).timestamp()),
        )

    def end_session_url(self, *, post_logout_redirect_uri: str, id_token_hint: str | None = None) -> str:
        return post_logout_redirect_uri


def log_in(client: TestClient) -> None:
    login_response = client.get("/api/v1/auth/login", follow_redirects=False)
    state = parse_qs(urlparse(login_response.headers["location"]).query)["state"][0]
    response = client.get(
        "/api/v1/auth/callback",
        params={"code": "code", "state": state},
        follow_redirects=False,
    )
    assert response.status_code == 303


def test_system_status_reports_migrated_postgresql(database_url: str) -> None:
    app = create_app(
        database_url=database_url,
        oidc_client=SystemStatusOIDCClient(),
    )

    with TestClient(app) as client:
        log_in(client)
        response = client.get("/api/v1/system/status")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "database": "ready",
        "schema_revision": _head_revision(),
    }


def test_local_frontend_origin_can_read_system_status(database_url: str) -> None:
    app = create_app(
        database_url=database_url,
        oidc_client=SystemStatusOIDCClient(),
    )

    with TestClient(app) as client:
        log_in(client)
        response = client.get(
            "/api/v1/system/status",
            headers={"Origin": "http://127.0.0.1:8173"},
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:8173"


def test_system_status_rejects_anonymous_access(database_url: str) -> None:
    app = create_app(database_url=database_url)

    with TestClient(app) as client:
        response = client.get("/api/v1/system/status")

    assert response.status_code == 401
