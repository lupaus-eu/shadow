"""Machine-readable health for uptime monitors (docs/operations/monitoring.md).

``GET /api/v1/monitoring/health`` requires ``Authorization: Bearer
$MONITORING_TOKEN`` and is disabled (404) when no token is configured. It
returns 200 when every check passes and 503 otherwise, so a plain HTTP monitor
can alert on it. It reports counts and ages only, never customer content.
"""

import hmac
import os
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import httpx
from fastapi import APIRouter, Header, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy import func, select, text
from sqlalchemy.orm import sessionmaker

from app.database import RequestContext, transaction_session
from app.models import BackgroundJob, OutboxMessage, QueueStatus, StripeWebhookEvent

AuthentikProbe = Callable[[], bool]


class Check(BaseModel):
    ok: bool
    detail: str


class MonitoringHealth(BaseModel):
    status: str
    checked_at: datetime
    checks: dict[str, Check]


def authentik_probe_from_environment() -> AuthentikProbe:
    base_url = os.getenv("OIDC_INTERNAL_BASE_URL", "http://authentik-server:9000").rstrip("/")

    def probe() -> bool:
        try:
            return httpx.get(f"{base_url}/-/health/live/", timeout=3.0).status_code < 300
        except httpx.HTTPError:
            return False

    return probe


def create_monitoring_router(*, session_factory: sessionmaker, authentik_probe: AuthentikProbe | None = None, token: str | None = None) -> APIRouter:
    router = APIRouter(prefix="/api/v1/monitoring", tags=["Monitoring"])
    configured_token = token if token is not None else os.getenv("MONITORING_TOKEN", "")
    probe = authentik_probe or authentik_probe_from_environment()
    stale_email = timedelta(minutes=int(os.getenv("MONITORING_EMAIL_MAX_AGE_MINUTES", "15")))
    max_database_bytes = int(os.getenv("MONITORING_DATABASE_MAX_BYTES", "0"))

    @router.get("/health", response_model=MonitoringHealth)
    def health(response: Response, authorization: str | None = Header(default=None)) -> MonitoringHealth:
        if not configured_token:
            raise HTTPException(status_code=404, detail="Not Found")
        if not authorization or not hmac.compare_digest(authorization, f"Bearer {configured_token}"):
            raise HTTPException(status_code=401, detail="monitoring token required")
        now = datetime.now(UTC)
        checks: dict[str, Check] = {}
        try:
            with transaction_session(session_factory, RequestContext()) as session:
                revision = session.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
                checks["database"] = Check(ok=True, detail=f"schema {revision}")
                size = session.execute(text("SELECT pg_database_size(current_database())")).scalar_one()
                checks["database_capacity"] = Check(ok=not max_database_bytes or size < max_database_bytes, detail=f"{size} bytes" + (f" of {max_database_bytes}" if max_database_bytes else ""))
                failed_jobs = session.scalar(select(func.count()).select_from(BackgroundJob).where(BackgroundJob.status == QueueStatus.FAILED.value))
                checks["background_jobs"] = Check(ok=failed_jobs == 0, detail=f"{failed_jobs} failed")
                failed_email = session.scalar(select(func.count()).select_from(OutboxMessage).where(OutboxMessage.status == QueueStatus.FAILED.value))
                oldest_pending = session.scalar(select(func.min(OutboxMessage.created_at)).where(OutboxMessage.status == QueueStatus.PENDING.value))
                stuck = oldest_pending is not None and now - oldest_pending > stale_email
                checks["email_delivery"] = Check(ok=failed_email == 0 and not stuck, detail=f"{failed_email} failed" + (f", pending since {oldest_pending.isoformat()}" if stuck else ""))
                last_webhook = session.scalar(select(func.max(StripeWebhookEvent.processed_at)))
                checks["stripe_webhooks"] = Check(ok=True, detail=f"last processed {last_webhook.isoformat()}" if last_webhook else "none processed yet")
        except Exception as error:  # noqa: BLE001 - any database failure is a failed check
            checks["database"] = Check(ok=False, detail=type(error).__name__)
        checks["authentik"] = Check(ok=probe(), detail="live endpoint")
        healthy = all(check.ok for check in checks.values())
        response.status_code = 200 if healthy else 503
        return MonitoringHealth(status="ok" if healthy else "degraded", checked_at=now, checks=checks)

    return router
