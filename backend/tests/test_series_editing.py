"""Editing recurring Occurrences and Series (ticket 14, ADR-0025)."""
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.main import create_app
from test_invitations import NOW, OIDC, Stripe, Verifier, active_org, login


class Planner:
    def __init__(self, client: TestClient, organization_id: str, yearclock: dict) -> None:
        self.client = client
        self.base = f"/api/v1/organizations/{organization_id}/yearclocks/{yearclock['id']}"
        self.lanes = [lane["id"] for lane in yearclock["lanes"]]

    def events(self, window_start: str = "2026-01-01", *, include_skipped: bool = False) -> list[dict]:
        suffix = "&include_skipped=true" if include_skipped else ""
        return self.client.get(f"{self.base}/events?window_start={window_start}{suffix}").json()

    def occurrence(self, series_date: str, window_start: str = "2026-01-01") -> dict:
        return next(item for item in self.events(window_start, include_skipped=True) if item["series_date"] == series_date)

    def series(self, series_id: str) -> dict:
        return self.client.get(f"{self.base}/series/{series_id}").json()


def _planner(database_url: str, subject: str) -> tuple:
    verifier = Verifier()
    application = create_app(database_url=database_url, oidc_client=OIDC(subject, f"{subject}@example.com"), stripe_billing=Stripe(), stripe_webhook_verifier=verifier, clock=lambda: NOW)
    client = TestClient(application)
    client.__enter__()
    login(client)
    organization_id = active_org(client, verifier)
    base = f"/api/v1/organizations/{organization_id}/yearclocks"
    yearclock = client.get(f"/api/v1/organizations/{organization_id}").json()["yearclocks"][0]
    client.post(f"{base}/{yearclock['id']}/lanes", json={"name": "Board"})
    yearclock = client.get(f"/api/v1/organizations/{organization_id}").json()["yearclocks"][0]
    return application, client, organization_id, Planner(client, organization_id, yearclock)


def test_this_and_future_keeps_overrides_and_inherits_the_rest(database_url: str) -> None:
    application, client, organization_id, planner = _planner(database_url, "series-split")
    try:
        series = client.post(f"{planner.base}/series", json={"title": "Standup", "lane_id": planner.lanes[0], "starts_on": "2026-01-05", "frequency": "WEEKLY"}).json()
        third = planner.occurrence("2026-01-19")
        renamed = client.patch(f"{planner.base}/occurrences/{third['occurrence_id']}", json={"title": "Standup (board)", "expected_version": third["version"]})
        fourth = planner.occurrence("2026-01-26")
        moved = client.patch(f"{planner.base}/occurrences/{fourth['occurrence_id']}", json={"starts_on": "2026-01-09", "expected_version": fourth["version"]})
        first = planner.occurrence("2026-01-05")
        client.patch(f"{planner.base}/occurrences/{first['occurrence_id']}", json={"starts_on": "2026-01-20", "expected_version": first["version"]})
        stale_occurrence = client.patch(f"{planner.base}/occurrences/{third['occurrence_id']}", json={"title": "Lost", "expected_version": third["version"]})

        second = planner.occurrence("2026-01-12")
        stale_split = client.post(f"{planner.base}/series/{series['id']}/split", json={"from_occurrence_id": second["occurrence_id"], "expected_version": 99, "description": "x"})
        split = client.post(f"{planner.base}/series/{series['id']}/split", json={"from_occurrence_id": second["occurrence_id"], "expected_version": series["version"], "description": "New agenda", "lane_id": planner.lanes[1]})
        original = planner.series(series["id"])

        after = {item["series_date"]: item for item in planner.events(include_skipped=True)}
    finally:
        client.__exit__(None, None, None)
    assert renamed.status_code == 200 and renamed.json()["exception"] is True
    assert moved.json()["starts_on"] == "2026-01-09"
    assert stale_occurrence.status_code == 409
    assert stale_split.status_code == 409
    assert split.status_code == 200
    successor = split.json()
    assert successor["id"] != series["id"]
    assert (successor["effective_from"], successor["starts_on"]) == ("2026-01-12", "2026-01-05")
    assert original["until"] == "2026-01-11"

    assert after["2026-01-05"]["series_id"] == series["id"]
    assert after["2026-01-05"]["starts_on"] == "2026-01-20", "a moved Occurrence stays with the segment of its Series Date"
    assert after["2026-01-05"]["description"] is None and after["2026-01-05"]["lane_id"] == planner.lanes[0]
    assert after["2026-01-12"]["series_id"] == successor["id"]
    assert after["2026-01-12"]["description"] == "New agenda" and after["2026-01-12"]["lane_id"] == planner.lanes[1]
    assert after["2026-01-19"]["title"] == "Standup (board)", "explicit overrides survive the split"
    assert after["2026-01-19"]["description"] == "New agenda", "non-overridden fields inherit from the successor"
    assert after["2026-01-26"]["series_id"] == successor["id"] and after["2026-01-26"]["starts_on"] == "2026-01-09"
    assert all(item["series_id"] == successor["id"] for date, item in after.items() if date >= "2026-01-12")


def test_restore_skip_and_end_keep_history(database_url: str) -> None:
    application, client, organization_id, planner = _planner(database_url, "series-end")
    try:
        series = client.post(f"{planner.base}/series", json={"title": "Review", "lane_id": planner.lanes[0], "starts_on": "2026-02-02", "frequency": "WEEKLY"}).json()
        target = planner.occurrence("2026-02-16")
        edited = client.patch(f"{planner.base}/occurrences/{target['occurrence_id']}", json={"title": "Special review", "starts_on": "2026-02-18", "description": "Bring numbers", "expected_version": target["version"]}).json()
        restored = client.post(f"{planner.base}/occurrences/{target['occurrence_id']}/restore?expected_version={edited['version']}").json()
        skipped = client.post(f"{planner.base}/occurrences/{target['occurrence_id']}/skip").json()
        hidden = [item["series_date"] for item in planner.events()]
        listed_skipped = [item["series_date"] for item in planner.events(include_skipped=True) if item["skipped"]]
        client.post(f"{planner.base}/occurrences/{target['occurrence_id']}/skip?skipped=false")
        visible_again = [item["series_date"] for item in planner.events()]

        end_at = planner.occurrence("2026-03-02")
        ended = client.post(f"{planner.base}/series/{series['id']}/end", json={"from_occurrence_id": end_at["occurrence_id"], "expected_version": series["version"]})
        remaining = [item["series_date"] for item in planner.events()]
        far_future = planner.events("2028-01-01")
    finally:
        client.__exit__(None, None, None)
    assert edited["exception"] is True and edited["starts_on"] == "2026-02-18"
    assert (restored["title"], restored["starts_on"], restored["description"], restored["exception"]) == ("Review", "2026-02-16", None, False)
    assert skipped["skipped"] is True
    assert "2026-02-16" not in hidden and listed_skipped == ["2026-02-16"]
    assert "2026-02-16" in visible_again
    assert ended.status_code == 200 and ended.json()["removed_occurrences"] > 40
    assert ended.json()["series"]["until"] == "2026-03-01"
    assert remaining == ["2026-02-02", "2026-02-09", "2026-02-16", "2026-02-23"]
    assert far_future == []
    with application.state.database_engine.connect() as connection:
        actions = connection.execute(text("SELECT action FROM audit_events WHERE organization_id = :id AND target_type IN ('series_occurrence', 'event_series') ORDER BY occurred_at"), {"id": organization_id}).scalars().all()
    assert actions == ["series.created", "occurrence.updated", "occurrence.restored", "occurrence.skipped", "occurrence.unskipped", "series.ended"]


def test_splitting_at_the_first_occurrence_edits_the_segment_in_place(database_url: str) -> None:
    application, client, organization_id, planner = _planner(database_url, "series-in-place")
    try:
        series = client.post(f"{planner.base}/series", json={"title": "Board", "lane_id": planner.lanes[0], "starts_on": "2026-01-31", "frequency": "MONTHLY", "occurrence_count": 6}).json()
        first = planner.occurrence("2026-01-31")
        updated = client.post(f"{planner.base}/series/{series['id']}/split", json={"from_occurrence_id": first["occurrence_id"], "expected_version": series["version"], "title": "Board meeting"}).json()
        titles = {item["title"] for item in planner.events()}
    finally:
        client.__exit__(None, None, None)
    assert updated["id"] == series["id"] and updated["version"] == 2
    assert titles == {"Board meeting"}


def test_a_successor_keeps_the_monthly_anchor(database_url: str) -> None:
    application, client, organization_id, planner = _planner(database_url, "series-anchor")
    try:
        series = client.post(f"{planner.base}/series", json={"title": "Month end", "lane_id": planner.lanes[0], "starts_on": "2026-01-31", "frequency": "MONTHLY"}).json()
        april = planner.occurrence("2026-04-30")
        successor = client.post(f"{planner.base}/series/{series['id']}/split", json={"from_occurrence_id": april["occurrence_id"], "expected_version": series["version"], "title": "Month end (new)"}).json()
        dates = [(item["series_date"], item["title"]) for item in planner.events() if item["series_date"] <= "2026-07-31"]
    finally:
        client.__exit__(None, None, None)
    assert successor["effective_from"] == "2026-04-30"
    assert dates == [("2026-01-31", "Month end"), ("2026-02-28", "Month end"), ("2026-03-31", "Month end"), ("2026-04-30", "Month end (new)"), ("2026-05-31", "Month end (new)"), ("2026-06-30", "Month end (new)"), ("2026-07-31", "Month end (new)")]


def test_occurrence_routes_are_scoped_to_their_yearclock(database_url: str) -> None:
    application, client, organization_id, planner = _planner(database_url, "series-scope")
    try:
        client.post(f"{planner.base}/series", json={"title": "Weekly", "lane_id": planner.lanes[0], "starts_on": "2026-01-05", "frequency": "WEEKLY"})
        occurrence = planner.occurrence("2026-01-05")
        other = client.post(f"/api/v1/organizations/{organization_id}/yearclocks", json={"name": "Other"}).json()
        other_base = f"/api/v1/organizations/{organization_id}/yearclocks/{other['id']}"
        responses = [
            client.patch(f"{other_base}/occurrences/{occurrence['occurrence_id']}", json={"title": "Cross", "expected_version": occurrence["version"]}).status_code,
            client.post(f"{other_base}/occurrences/{occurrence['occurrence_id']}/skip").status_code,
            client.post(f"{other_base}/occurrences/{occurrence['occurrence_id']}/restore").status_code,
            client.get(f"{other_base}/series/{occurrence['series_id']}").status_code,
        ]
    finally:
        client.__exit__(None, None, None)
    assert responses == [404, 404, 404, 404]
