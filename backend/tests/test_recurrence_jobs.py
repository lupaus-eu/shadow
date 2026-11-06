"""Background materialization of recurring Occurrences (ticket 13)."""
import threading
from datetime import UTC, date, datetime, timedelta
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.database import RequestContext, transaction_session
from app.jobs import MAX_JOB_ATTEMPTS, RECURRENCE_JOB, run_one_background_job, schedule_recurrence_jobs
from app.main import create_app
from app.models import EventSeries
from app.recurrence import materialization_horizon, materialize_series
from test_invitations import NOW, OIDC, Stripe, Verifier, active_org, login


def _organization_with_series(database_url: str, subject: str, series: dict) -> tuple:
    verifier = Verifier()
    application = create_app(database_url=database_url, oidc_client=OIDC(subject, f"{subject}@example.com"), stripe_billing=Stripe(), stripe_webhook_verifier=verifier, clock=lambda: NOW)
    with TestClient(application) as client:
        login(client)
        organization_id = active_org(client, verifier)
        yearclock = client.get(f"/api/v1/organizations/{organization_id}").json()["yearclocks"][0]
        created = client.post(f"/api/v1/organizations/{organization_id}/yearclocks/{yearclock['id']}/series", json={"lane_id": yearclock["lanes"][0]["id"], **series})
        assert created.status_code == 201, created.text
    return application, organization_id, created.json()["id"]


def _last_series_date(engine, series_id: str) -> date:
    with engine.connect() as connection:
        return connection.execute(text("SELECT max(series_date) FROM series_occurrences WHERE series_id = :id"), {"id": series_id}).scalar_one()


def _occurrence_count(engine, series_id: str) -> tuple[int, int]:
    with engine.connect() as connection:
        total = connection.execute(text("SELECT count(*) FROM series_occurrences WHERE series_id = :id"), {"id": series_id}).scalar_one()
        distinct = connection.execute(text("SELECT count(DISTINCT series_date) FROM series_occurrences WHERE series_id = :id"), {"id": series_id}).scalar_one()
    return total, distinct


def _jobs(engine, organization_id: str) -> list:
    with engine.connect() as connection:
        return connection.execute(text("SELECT status, attempts, last_error, available_at FROM background_jobs WHERE organization_id = :id AND job_type = :type"), {"id": organization_id, "type": RECURRENCE_JOB}).all()


def _drain(session_factory, now: datetime, organization_id: str, **kwargs) -> int:
    ran = 0
    while run_one_background_job(session_factory, now=lambda: now, organization_id=UUID(organization_id), **kwargs):
        ran += 1
    return ran


def test_the_worker_extends_the_forward_buffer_once_per_day(database_url: str) -> None:
    application, organization_id, series_id = _organization_with_series(database_url, "jobs-buffer", {"title": "Weekly review", "starts_on": "2026-07-06", "frequency": "WEEKLY"})
    engine, factory = application.state.database_engine, application.state.session_factory
    created_through = _last_series_date(engine, series_id)
    later = datetime(2028, 6, 1, 9, 0, tzinfo=UTC)

    assert schedule_recurrence_jobs(factory, today=later.date()) >= 1
    schedule_recurrence_jobs(factory, today=later.date())
    assert len(_jobs(engine, organization_id)) == 1
    _drain(factory, later, organization_id)
    extended = _last_series_date(engine, series_id)
    total, distinct = _occurrence_count(engine, series_id)

    assert [row.status for row in _jobs(engine, organization_id)] == ["completed"]
    assert extended > created_through
    assert extended > materialization_horizon("Europe/Helsinki", now=later) - timedelta(days=7)
    assert extended <= materialization_horizon("Europe/Helsinki", now=later)
    assert total == distinct


def test_failed_jobs_retry_with_backoff_and_then_fail(database_url: str) -> None:
    application, organization_id, _series_id = _organization_with_series(database_url, "jobs-retry", {"title": "Monthly close", "starts_on": "2026-01-31", "frequency": "MONTHLY"})
    engine, factory = application.state.database_engine, application.state.session_factory
    now = datetime(2027, 1, 1, 9, 0, tzinfo=UTC)
    schedule_recurrence_jobs(factory, today=now.date())

    def broken(session, job, when):
        raise RuntimeError("materializer unavailable")

    assert run_one_background_job(factory, now=lambda: now, handlers={RECURRENCE_JOB: broken}, organization_id=UUID(organization_id))
    [pending] = _jobs(engine, organization_id)
    assert (pending.status, pending.attempts) == ("pending", 1)
    assert pending.last_error == "RuntimeError: materializer unavailable"
    assert pending.available_at > now
    assert not run_one_background_job(factory, now=lambda: now, handlers={RECURRENCE_JOB: broken}, organization_id=UUID(organization_id)), "backoff hides the job until it is due"

    for _ in range(MAX_JOB_ATTEMPTS - 1):
        with engine.begin() as connection:
            connection.execute(text("UPDATE background_jobs SET available_at = now() WHERE organization_id = :id"), {"id": organization_id})
        assert run_one_background_job(factory, now=lambda: now, handlers={RECURRENCE_JOB: broken}, organization_id=UUID(organization_id))
    [failed] = _jobs(engine, organization_id)
    assert (failed.status, failed.attempts) == ("failed", MAX_JOB_ATTEMPTS)


def test_concurrent_materialization_never_duplicates(database_url: str) -> None:
    application, organization_id, series_id = _organization_with_series(database_url, "jobs-concurrent", {"title": "Weekly sync", "starts_on": "2026-07-06", "frequency": "WEEKLY"})
    factory = application.state.session_factory
    barrier = threading.Barrier(2)
    errors: list[BaseException] = []
    created: list[int] = []

    def materialize() -> None:
        try:
            with transaction_session(factory, RequestContext(organization_id=UUID(organization_id))) as session:
                series = session.get(EventSeries, UUID(series_id))
                barrier.wait(timeout=10)
                created.append(materialize_series(session, series, through=date(2030, 12, 31)))
        except BaseException as error:  # noqa: BLE001
            errors.append(error)

    threads = [threading.Thread(target=materialize) for _ in range(2)]
    for thread in threads: thread.start()
    for thread in threads: thread.join(timeout=30)
    total, distinct = _occurrence_count(application.state.database_engine, series_id)
    assert errors == []
    assert sorted(created)[0] == 0 and sorted(created)[1] > 0
    assert total == distinct


def test_the_horizon_follows_the_organization_time_zone(database_url: str) -> None:
    application, organization_id, series_id = _organization_with_series(database_url, "jobs-zone", {"title": "Quarter start", "starts_on": "2026-01-01", "frequency": "MONTHLY"})
    factory = application.state.session_factory
    evening_utc = datetime(2027, 12, 31, 22, 30, tzinfo=UTC)
    assert materialization_horizon("Europe/Helsinki", now=evening_utc) == date(2029, 1, 1)
    assert materialization_horizon("UTC", now=evening_utc) == date(2028, 12, 31)
    schedule_recurrence_jobs(factory, today=evening_utc.date())
    _drain(factory, evening_utc, organization_id)
    assert _last_series_date(application.state.database_engine, series_id) == date(2029, 1, 1)


def test_the_series_api_returns_an_rrule_and_rejects_unsupported_rules(database_url: str) -> None:
    verifier = Verifier()
    application = create_app(database_url=database_url, oidc_client=OIDC("jobs-rules", "jobs-rules@example.com"), stripe_billing=Stripe(), stripe_webhook_verifier=verifier, clock=lambda: NOW)
    with TestClient(application) as client:
        login(client)
        organization_id = active_org(client, verifier)
        yearclock = client.get(f"/api/v1/organizations/{organization_id}").json()["yearclocks"][0]
        path = f"/api/v1/organizations/{organization_id}/yearclocks/{yearclock['id']}/series"
        base = {"title": "Close", "lane_id": yearclock["lanes"][0]["id"], "starts_on": "2026-01-12"}
        month_end = client.post(path, json={**base, "frequency": "MONTHLY", "last_day": True, "occurrence_count": 3})
        rejected = [
            client.post(path, json={**base, "frequency": "DAILY"}).status_code,
            client.post(path, json={**base, "frequency": "WEEKLY", "interval": 0}).status_code,
            client.post(path, json={**base, "frequency": "WEEKLY", "last_day": True}).status_code,
            client.post(path, json={**base, "frequency": "MONTHLY", "until": "2026-12-31", "occurrence_count": 3}).status_code,
            client.post(path, json={**base, "frequency": "MONTHLY", "until": "2025-12-31"}).status_code,
            client.post(path, json={**base, "frequency": "MONTHLY", "links": [{"title": "x", "url": "ftp://example.com"}]}).status_code,
        ]
        dates = [item["starts_on"] for item in client.get(f"/api/v1/organizations/{organization_id}/yearclocks/{yearclock['id']}/events?window_start=2026-01-01").json()]
    assert month_end.status_code == 201
    assert month_end.json()["rrule"] == "FREQ=MONTHLY;INTERVAL=1;BYMONTHDAY=-1;COUNT=3"
    assert dates == ["2026-01-31", "2026-02-28", "2026-03-31"]
    assert rejected == [422] * 6
