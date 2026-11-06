"""Search one Yearclock across all time (Yearclock V2, P2 ticket 07)."""
from contextlib import ExitStack
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

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
    return application, owner, organization_id, base, clock


def _event(client, base, clock, title, starts_on="2026-10-01", **extra):
    response = client.post(f"{base}/yearclocks/{clock['id']}/events", json={"title": title, "lane_id": clock["lanes"][0]["id"], "starts_on": starts_on, **extra})
    assert response.status_code == 201, response.text
    return response.json()


def _search(client, base, clock, q, **params):
    return client.get(f"{base}/yearclocks/{clock['id']}/search", params={"q": q, **params})


def test_search_ignores_case_and_accents_across_fields_and_years(database_url, stack) -> None:
    application, owner, _, base, clock = _world(stack, database_url, "search-owner")
    category = owner.post(f"{base}/categories", json={"name": "Hallitus", "color": "#1f5f99"}).json()
    label = owner.post(f"{base}/labels", json={"name": "Päätös", "color": LABEL_COLORS[0]}).json()
    budget_2025 = _event(owner, base, clock, "Budjetin käsittely", "2025-03-10")
    budget_2027 = _event(owner, base, clock, "Board meeting", "2027-11-02", description="Hyväksytään BUDJETTI")
    by_category = _event(owner, base, clock, "Kokous", "2026-05-05", category_id=category["id"])
    by_label = _event(owner, base, clock, "Katselmointi", "2026-06-06", label_ids=[label["id"]])
    deleted = _event(owner, base, clock, "Budjetti luonnos", "2026-07-07")
    owner.delete(f"{base}/yearclocks/{clock['id']}/events/{deleted['id']}?expected_version=1")
    with application.state.database_engine.connect() as connection:
        audit_before = connection.execute(text("SELECT count(*) FROM audit_events")).scalar_one()

    budget = _search(owner, base, clock, "budjetti").json()
    accent = _search(owner, base, clock, "KASITTELY").json()
    category_hit = _search(owner, base, clock, "hallitus").json()
    label_hit = _search(owner, base, clock, "paatos").json()
    assert [item["id"] for item in budget["items"]] == [budget_2027["id"]]
    assert [item["id"] for item in accent["items"]] == [budget_2025["id"]]
    assert [item["id"] for item in category_hit["items"]] == [by_category["id"]]
    assert [item["id"] for item in label_hit["items"]] == [by_label["id"]] and label_hit["items"][0]["label_ids"] == [label["id"]]
    assert _search(owner, base, clock, "budj").json()["total"] == 2
    assert _search(owner, base, clock, " a ").status_code == 422
    with application.state.database_engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM audit_events")).scalar_one() == audit_before


def test_results_page_by_date_and_include_recurring_occurrences(database_url, stack) -> None:
    application, owner, organization_id, base, clock = _world(stack, database_url, "search-paging")
    rows = [{"id": uuid4(), "org": organization_id, "clock": clock["id"], "lane": clock["lanes"][0]["id"], "title": f"Weekly review {index:02d}", "day": index} for index in range(55)]
    with application.state.database_engine.begin() as connection:
        connection.execute(text("INSERT INTO events (id, organization_id, yearclock_id, lane_id, title, starts_on, version) VALUES (:id, :org, :clock, :lane, :title, DATE '2026-01-01' + :day, 1)"), rows)
    first = _search(owner, base, clock, "review").json()
    second = _search(owner, base, clock, "review", offset=first["next_offset"]).json()
    assert len(first["items"]) == 50 and first["next_offset"] == 50 and first["total"] == 55
    assert [item["title"] for item in second["items"]] == [f"Weekly review {index:02d}" for index in range(50, 55)] and second["next_offset"] is None
    assert [item["starts_on"] for item in first["items"]] == sorted(item["starts_on"] for item in first["items"])
    assert first["includes_recurring"] is False

    series = owner.post(f"{base}/yearclocks/{clock['id']}/series", json={"title": "Standup sync", "lane_id": clock["lanes"][0]["id"], "starts_on": "2026-01-05", "frequency": "WEEKLY"})
    assert series.status_code == 201
    recurring = _search(owner, base, clock, "standup").json()
    assert recurring["includes_recurring"] is True and recurring["total"] > 20
    skipped = recurring["items"][1]
    owner.post(f"{base}/yearclocks/{clock['id']}/occurrences/{skipped['occurrence_id']}/skip")
    assert skipped["id"] not in [item["id"] for item in _search(owner, base, clock, "standup").json()["items"]]


def test_search_follows_yearclock_access(database_url, stack) -> None:
    application, owner, organization_id, base, clock = _world(stack, database_url, "search-access")
    _event(owner, base, clock, "Secret merger")
    viewer_app, viewer_id = join(application, owner, organization_id, subject="search-viewer", email="search-viewer@example.com")
    member_app, _ = join(application, owner, organization_id, subject="search-member", email="search-member@example.com")
    owner.put(f"{base}/yearclocks/{clock['id']}/access", json={"user_account_id": viewer_id, "role": "viewer"})
    with TestClient(viewer_app) as viewer:
        login(viewer)
        assert [item["title"] for item in _search(viewer, base, clock, "merger").json()["items"]] == ["Secret merger"]
    with TestClient(member_app) as member:
        login(member)
        assert _search(member, base, clock, "merger").status_code in {403, 404}
