"""Token-protected monitoring health for uptime checks (ticket 22)."""
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.main import create_app


def _client(database_url: str, *, token: str = "monitor-secret", authentik: bool = True) -> TestClient:
    return TestClient(create_app(database_url=database_url, authentik_probe=lambda: authentik, monitoring_token=token))


def test_monitoring_is_disabled_without_a_token_and_refuses_wrong_tokens(database_url: str) -> None:
    with _client(database_url, token="") as client:
        assert client.get("/api/v1/monitoring/health", headers={"Authorization": "Bearer "}).status_code == 404
    with _client(database_url) as client:
        assert client.get("/api/v1/monitoring/health").status_code == 401
        assert client.get("/api/v1/monitoring/health", headers={"Authorization": "Bearer wrong"}).status_code == 401


def test_monitoring_reports_failures_and_unavailable_identity(database_url: str) -> None:
    with _client(database_url) as client:
        healthy = client.get("/api/v1/monitoring/health", headers={"Authorization": "Bearer monitor-secret"})
    checks = healthy.json()["checks"]
    assert set(checks) == {"database", "database_capacity", "background_jobs", "email_delivery", "stripe_webhooks", "authentik"}
    assert checks["database"]["ok"] and checks["authentik"]["ok"]
    # The shared test database may hold failed rows from other tests; the status must follow the checks.
    assert healthy.status_code == (200 if all(check["ok"] for check in checks.values()) else 503)

    job_id = uuid4()
    with _client(database_url, authentik=False) as client:
        with client.app.state.database_engine.begin() as connection:
            connection.execute(text("INSERT INTO background_jobs (id, job_type, payload, idempotency_key, status, attempts, last_error) VALUES (:id, 'content.purge', '{}', :key, 'failed', 5, 'boom')"), {"id": job_id, "key": f"monitor:{job_id}"})
        try:
            degraded = client.get("/api/v1/monitoring/health", headers={"Authorization": "Bearer monitor-secret"})
        finally:
            with client.app.state.database_engine.begin() as connection:
                connection.execute(text("DELETE FROM background_jobs WHERE id = :id"), {"id": job_id})
    body = degraded.json()
    assert degraded.status_code == 503 and body["status"] == "degraded"
    assert body["checks"]["background_jobs"] == {"ok": False, "detail": "1 failed"}
    assert body["checks"]["authentik"]["ok"] is False
