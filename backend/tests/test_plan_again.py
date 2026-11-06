"""Plan a season again (Yearclock V2, P3 ticket 03)."""
from contextlib import ExitStack
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.event_routes import next_year, same_weekday_next_year
from app.label_routes import LABEL_COLORS
from app.main import create_app
from test_invitations import NOW, OIDC, Stripe, Verifier, active_org, join, login


@pytest.fixture
def stack():
    with ExitStack() as clients:
        yield clients


def _world(stack, database_url, subject):
    verifier = Verifier()
    application = create_app(database_url=database_url, oidc_client=OIDC(subject, f"{subject}@example.com"), stripe_billing=Stripe(), stripe_webhook_verifier=verifier, clock=lambda: NOW)
    owner = stack.enter_context(TestClient(application))
    login(owner)
    organization_id = active_org(owner, verifier, seats=4)
    base = f"/api/v1/organizations/{organization_id}"
    clock = owner.get(base).json()["yearclocks"][0]
    return application, owner, organization_id, base, f"{base}/yearclocks/{clock['id']}", clock


def _event(client, url, lane_id, title, starts_on, **extra):
    response = client.post(f"{url}/events", json={"title": title, "lane_id": lane_id, "starts_on": starts_on, **extra})
    assert response.status_code == 201, response.text
    return response.json()


def _events(client, url, start):
    return client.get(f"{url}/events", params={"window_start": start}).json()


def test_date_rules() -> None:
    assert next_year(date(2026, 3, 10)) == date(2027, 3, 10)
    assert next_year(date(2028, 2, 29)) == date(2029, 2, 28)
    for day in (date(2026, 1, 1), date(2027, 6, 15), date(2028, 2, 29), date(2027, 3, 1)):
        moved = same_weekday_next_year(day)
        assert moved.weekday() == day.weekday() and abs((moved - next_year(day)).days) <= 3


def test_a_season_is_copied_a_year_ahead_with_a_preview_and_duplicates_skipped(database_url, stack) -> None:
    application, owner, _, base, url, clock = _world(stack, database_url, "plan-again-owner")
    board, hr = clock["lanes"][0]["id"], owner.post(f"{url}/lanes", json={"name": "HR"}).json()["id"]
    other = owner.post(f"{url}/lanes", json={"name": "Other"}).json()["id"]
    finance = owner.post(f"{base}/categories", json={"name": "Finance", "color": "#1f5f99"}).json()
    skipped_category = owner.post(f"{url}/categories", json={"name": "Skip", "color": "#336699"}).json()
    label = owner.post(f"{base}/labels", json={"name": "Budget", "color": LABEL_COLORS[0]}).json()
    meeting = _event(owner, url, board, "Board meeting", "2026-03-10", category_id=finance["id"], label_ids=[label["id"]], description="Agenda", links=[{"title": "Agenda", "url": "https://example.com/a"}])
    _event(owner, url, hr, "Review week", "2026-06-01", ends_on="2026-06-05")
    _event(owner, url, other, "Not chosen", "2026-04-01")
    _event(owner, url, board, "Wrong category", "2026-04-02", category_id=skipped_category["id"])
    _event(owner, url, board, "Next season", "2027-01-15")
    owner.post(f"{url}/series", json={"title": "Weekly", "lane_id": board, "starts_on": "2026-01-05", "frequency": "WEEKLY"})
    body = {"season_start": "2026-01-01", "lane_ids": [board, hr], "category_ids": [finance["id"]], "include_uncategorized": True, "date_rule": "same_weekday"}

    preview = owner.post(f"{url}/plan-again", json=body)
    assert preview.status_code == 200, preview.text
    assert preview.json() == {"to_create": 2, "skipped_existing": 0, "limit_exceeded": False, "maximum": 3000, "created_ids": []}
    assert not [item for item in _events(owner, url, "2027-01-01") if item["title"] == "Board meeting"]

    done = owner.post(f"{url}/plan-again", json={**body, "dry_run": False}).json()
    assert done["to_create"] == 2 and len(done["created_ids"]) == 2
    copies = {item["title"]: item for item in _events(owner, url, "2027-01-01") if item["id"] in done["created_ids"]}
    assert copies["Board meeting"]["starts_on"] == "2027-03-09" and copies["Board meeting"]["category_id"] == finance["id"]
    assert copies["Board meeting"]["label_ids"] == [label["id"]] and copies["Board meeting"]["description"] == "Agenda" and copies["Board meeting"]["links"] == [{"title": "Agenda", "url": "https://example.com/a"}]
    assert (copies["Review week"]["starts_on"], copies["Review week"]["ends_on"]) == ("2027-05-31", "2027-06-04")
    assert next(item for item in _events(owner, url, "2026-01-01") if item["id"] == meeting["id"])["version"] == 1

    again = owner.post(f"{url}/plan-again", json={**body, "dry_run": False}).json()
    assert again == {"to_create": 0, "skipped_existing": 2, "limit_exceeded": False, "maximum": 3000, "created_ids": []}
    same_date = owner.post(f"{url}/plan-again", json={**body, "date_rule": "same_date"}).json()
    assert same_date["to_create"] == 2

    audits = owner.get(f"{base}/audit-events", params={"prefix": "yearclock"}).json()["items"]
    planned = [item for item in audits if item["action"] == "yearclock.planned_again"]
    assert len(planned) == 1 and planned[0]["change_summary"]["created"] == 2
    created = [item for item in owner.get(f"{base}/audit-events", params={"prefix": "event"}).json()["items"] if (item["change_summary"] or {}).get("plan_id") == planned[0]["change_summary"]["plan_id"]]
    assert sorted(item["action"] for item in created) == ["event.created", "event.created"]


def test_limits_roles_and_read_only(database_url, stack, monkeypatch) -> None:
    application, owner, organization_id, base, url, clock = _world(stack, database_url, "plan-again-roles")
    lane = clock["lanes"][0]["id"]
    _event(owner, url, lane, "One", "2026-02-01")
    _event(owner, url, lane, "Two", "2026-02-02")
    body = {"season_start": "2026-01-01", "lane_ids": [lane]}
    monkeypatch.setenv("LIMIT_EVENTS_PER_YEARCLOCK", "3")
    preview = owner.post(f"{url}/plan-again", json=body).json()
    assert preview["limit_exceeded"] is True and preview["to_create"] == 2 and preview["maximum"] == 3
    refused = owner.post(f"{url}/plan-again", json={**body, "dry_run": False})
    assert refused.status_code == 409 and refused.json()["detail"]["limit"] == "events_per_yearclock"
    assert len(_events(owner, url, "2027-01-01")) == 0
    monkeypatch.delenv("LIMIT_EVENTS_PER_YEARCLOCK")
    assert owner.post(f"{url}/plan-again", json={**body, "season_start": "2026-01-15"}).status_code == 422
    foreign = owner.post(f"{base}/yearclocks", json={"name": "Other"}).json()["lanes"][0]["id"]
    assert owner.post(f"{url}/plan-again", json={**body, "lane_ids": [foreign]}).status_code == 422

    viewer_app, viewer_id = join(application, owner, organization_id, subject="plan-again-viewer", email="plan-again-viewer@example.com")
    owner.put(f"{url}/access", json={"user_account_id": viewer_id, "role": "viewer"})
    with TestClient(viewer_app) as viewer:
        login(viewer)
        assert viewer.post(f"{url}/plan-again", json=body).status_code == 403
    with application.state.database_engine.begin() as connection:
        connection.execute(text("UPDATE organizations SET subscription_access_state = 'canceled' WHERE id = :id"), {"id": organization_id})
    assert owner.post(f"{url}/plan-again", json=body).status_code == 403
