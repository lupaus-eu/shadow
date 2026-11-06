"""Operational ceilings fail clearly, and dense Yearclocks stay complete and fast (ticket 23)."""
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.main import create_app
from test_invitations import NOW, OIDC, Stripe, Verifier, active_org, login


@pytest.fixture
def owner(database_url):
    with ExitStack() as stack:
        verifier = Verifier()
        application = create_app(database_url=database_url, oidc_client=OIDC(f"limits-{uuid4()}", f"limits-{uuid4()}@example.com"), stripe_billing=Stripe(), stripe_webhook_verifier=verifier, clock=lambda: NOW)
        client = stack.enter_context(TestClient(application))
        login(client)
        organization_id = active_org(client, verifier)
        clock = client.get(f"/api/v1/organizations/{organization_id}").json()["yearclocks"][0]
        yield client, application, f"/api/v1/organizations/{organization_id}", organization_id, clock


def _limit(response, name):
    assert response.status_code == 409, response.text
    assert response.json()["detail"]["reason"] == "limit_reached" and response.json()["detail"]["limit"] == name
    return response.json()["detail"]["maximum"]


def test_structure_ceilings_refuse_with_a_named_reason(owner, monkeypatch) -> None:
    client, _, base, _, clock = owner
    monkeypatch.setenv("LIMIT_LANES_PER_YEARCLOCK", "2")
    monkeypatch.setenv("LIMIT_CATEGORIES_PER_YEARCLOCK", "1")
    monkeypatch.setenv("LIMIT_YEARCLOCKS_PER_ORGANIZATION", "2")
    assert client.post(f"{base}/yearclocks/{clock['id']}/lanes", json={"name": "Second"}).status_code == 201
    assert _limit(client.post(f"{base}/yearclocks/{clock['id']}/lanes", json={"name": "Third"}), "lanes_per_yearclock") == 2
    assert client.post(f"{base}/yearclocks/{clock['id']}/categories", json={"name": "One", "color": "#336699"}).status_code == 201
    _limit(client.post(f"{base}/yearclocks/{clock['id']}/categories", json={"name": "Two", "color": "#336699"}), "categories_per_yearclock")
    assert client.post(f"{base}/yearclocks", json={"name": "Second clock"}).status_code == 201
    _limit(client.post(f"{base}/yearclocks", json={"name": "Third clock"}), "yearclocks_per_organization")


def test_event_and_series_ceilings_hold_under_concurrent_writes(owner, monkeypatch) -> None:
    client, _, base, _, clock = owner
    monkeypatch.setenv("LIMIT_EVENTS_PER_YEARCLOCK", "5")
    body = lambda index: {"title": f"Parallel {index}", "lane_id": clock["lanes"][0]["id"], "starts_on": "2026-10-01"}
    with ThreadPoolExecutor(max_workers=8) as pool:
        statuses = list(pool.map(lambda index: client.post(f"{base}/yearclocks/{clock['id']}/events", json=body(index)).status_code, range(12)))
    assert statuses.count(201) == 5 and statuses.count(409) == 7
    series = client.post(f"{base}/yearclocks/{clock['id']}/series", json={**body("series"), "frequency": "weekly", "interval": 1})
    _limit(series, "events_per_yearclock")


def test_a_dense_yearclock_lists_every_event_quickly(owner) -> None:
    client, application, base, organization_id, clock = owner
    lanes = [clock["lanes"][0]["id"]] + [client.post(f"{base}/yearclocks/{clock['id']}/lanes", json={"name": f"Lane {index}"}).json()["id"] for index in range(11)]
    rows = [{"id": uuid4(), "org": organization_id, "clock": clock["id"], "lane": lanes[index % len(lanes)], "title": f"Dense {index}", "day": index % 365} for index in range(2999)]
    with application.state.database_engine.begin() as connection:
        connection.execute(text("INSERT INTO events (id, organization_id, yearclock_id, lane_id, title, starts_on, version) VALUES (:id, :org, :clock, :lane, :title, DATE '2026-01-01' + :day, 1)"), rows)
    started = time.perf_counter()
    listed = client.get(f"{base}/yearclocks/{clock['id']}/events", params={"window_start": "2026-01-01"})
    elapsed = time.perf_counter() - started
    assert listed.status_code == 200 and len(listed.json()) == 2999
    assert elapsed < 3.0, f"dense list took {elapsed:.2f}s"
    # One more fits the default ceiling of 3000; the next is refused, not dropped.
    assert client.post(f"{base}/yearclocks/{clock['id']}/events", json={"title": "Last", "lane_id": lanes[0], "starts_on": "2026-12-31"}).status_code == 201
    assert _limit(client.post(f"{base}/yearclocks/{clock['id']}/events", json={"title": "Too many", "lane_id": lanes[0], "starts_on": "2026-12-31"}), "events_per_yearclock") == 3000
