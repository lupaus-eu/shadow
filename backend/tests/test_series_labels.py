"""Labels on Series and Occurrences (Yearclock V2, P2 ticket 04)."""
from contextlib import ExitStack
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.database import RequestContext, create_session_factory, transaction_session
from app.label_routes import LABEL_COLORS
from app.main import create_app
from app.models import EventSeries
from app.recurrence import materialize_series
from test_invitations import NOW, OIDC, Stripe, Verifier, active_org, login


@pytest.fixture
def stack():
    with ExitStack() as clients:
        yield clients


class Planner:
    def __init__(self, stack, database_url, subject):
        verifier = Verifier()
        self.application = create_app(database_url=database_url, oidc_client=OIDC(subject, f"{subject}@example.com"), stripe_billing=Stripe(), stripe_webhook_verifier=verifier, clock=lambda: NOW)
        self.client = stack.enter_context(TestClient(self.application))
        login(self.client)
        self.organization_id = active_org(self.client, verifier)
        self.org = f"/api/v1/organizations/{self.organization_id}"
        clock = self.client.get(self.org).json()["yearclocks"][0]
        self.base = f"{self.org}/yearclocks/{clock['id']}"
        self.lane = clock["lanes"][0]["id"]

    def label(self, name):
        return self.client.post(f"{self.org}/labels", json={"name": name, "color": LABEL_COLORS[0]}).json()["id"]

    def events(self):
        return {item["series_date"]: item for item in self.client.get(f"{self.base}/events", params={"window_start": "2026-01-01", "include_skipped": True}).json() if item["series_id"]}

    def weekly(self, label_ids):
        response = self.client.post(f"{self.base}/series", json={"title": "Standup", "lane_id": self.lane, "starts_on": "2026-01-05", "frequency": "WEEKLY", "label_ids": label_ids})
        assert response.status_code == 201, response.text
        return response.json()


def test_occurrences_inherit_series_labels_and_can_override_them(database_url, stack) -> None:
    planner = Planner(stack, database_url, "series-labels-inherit")
    team, board = planner.label("Team"), planner.label("Board")
    series = planner.weekly([team])
    assert series["label_ids"] == [team]
    before = planner.events()
    assert all(item["label_ids"] == [team] for item in before.values())
    third = before["2026-01-19"]
    overridden = planner.client.patch(f"{planner.base}/occurrences/{third['occurrence_id']}", json={"label_ids": [board, team], "expected_version": third["version"]})
    emptied = planner.events()["2026-01-26"]
    cleared = planner.client.patch(f"{planner.base}/occurrences/{emptied['occurrence_id']}", json={"label_ids": [], "expected_version": emptied["version"]})
    assert overridden.status_code == 200 and sorted(overridden.json()["label_ids"]) == sorted([board, team]) and overridden.json()["exception"] is True
    assert cleared.json()["label_ids"] == []
    after = planner.events()
    assert after["2026-01-12"]["label_ids"] == [team]
    restored = planner.client.post(f"{planner.base}/occurrences/{third['occurrence_id']}/restore")
    assert restored.json()["label_ids"] == [team] and restored.json()["exception"] is False
    assert planner.client.get(f"{planner.base}/series/{series['id']}").json()["label_ids"] == [team]


def test_this_and_future_changes_labels_from_the_chosen_occurrence(database_url, stack) -> None:
    planner = Planner(stack, database_url, "series-labels-split")
    team, board, hr = planner.label("Team"), planner.label("Board"), planner.label("HR")
    series = planner.weekly([team])
    events = planner.events()
    later = events["2026-02-02"]
    planner.client.patch(f"{planner.base}/occurrences/{later['occurrence_id']}", json={"label_ids": [hr], "expected_version": later["version"]})
    split = planner.client.post(f"{planner.base}/series/{series['id']}/split", json={"from_occurrence_id": events["2026-01-19"]["occurrence_id"], "expected_version": series["version"], "label_ids": [board]})
    assert split.status_code == 200 and split.json()["label_ids"] == [board]
    after = planner.events()
    assert after["2026-01-12"]["label_ids"] == [team]
    assert after["2026-01-19"]["label_ids"] == [board] and after["2026-01-26"]["label_ids"] == [board]
    assert after["2026-02-02"]["label_ids"] == [hr]
    unchanged = planner.client.post(f"{planner.base}/series/{split.json()['id']}/split", json={"from_occurrence_id": after["2026-03-02"]["occurrence_id"], "expected_version": split.json()["version"], "title": "Standup (new)"})
    assert unchanged.json()["label_ids"] == [board]


def test_merge_and_delete_reach_series_overrides_and_new_occurrences(database_url, stack) -> None:
    planner = Planner(stack, database_url, "series-labels-merge")
    team, meeting, draft = planner.label("Team"), planner.label("Meeting"), planner.label("Draft")
    series = planner.weekly([team, draft])
    third = planner.events()["2026-01-19"]
    planner.client.patch(f"{planner.base}/occurrences/{third['occurrence_id']}", json={"label_ids": [team], "expected_version": third["version"]})
    merged = planner.client.post(f"{planner.org}/labels/{team}/merge", json={"into_label_id": meeting, "expected_version": 1, "confirm": True})
    assert merged.status_code == 200
    assert sorted(planner.client.get(f"{planner.base}/series/{series['id']}").json()["label_ids"]) == sorted([meeting, draft])
    after = planner.events()
    assert after["2026-01-19"]["label_ids"] == [meeting]
    assert sorted(after["2026-01-12"]["label_ids"]) == sorted([meeting, draft])
    restored = planner.client.post(f"{planner.base}/occurrences/{third['occurrence_id']}/restore")
    assert sorted(restored.json()["label_ids"]) == sorted([meeting, draft])

    assert planner.client.delete(f"{planner.org}/labels/{draft}?expected_version=1&confirm=true").status_code == 204
    assert planner.client.get(f"{planner.base}/series/{series['id']}").json()["label_ids"] == [meeting]
    session_factory = create_session_factory(planner.application.state.database_engine)
    with transaction_session(session_factory, RequestContext(organization_id=planner.organization_id)) as session:
        materialize_series(session, session.get(EventSeries, series["id"]), through=date(2028, 6, 30))
    latest = planner.client.get(f"{planner.base}/events", params={"window_start": "2028-01-01"}).json()
    assert latest and all(item["label_ids"] == [meeting] for item in latest)
