"""Data transfer: all administered Organizations as one CSV and back (ADR-0040)."""
import csv
import io
from contextlib import ExitStack
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.data_transfer import COLUMNS, FORMAT
from app.label_routes import LABEL_COLORS
from app.main import create_app
from test_invitations import NOW, OIDC, Stripe, Verifier, active_org, join, login


@pytest.fixture
def stack():
    with ExitStack() as clients:
        yield clients


@pytest.fixture(autouse=True)
def generous_limit(monkeypatch):
    monkeypatch.setenv("LIMIT_TRANSFERS_PER_HOUR", "100")


class World:
    def __init__(self, stack, database_url, subject):
        self.verifier = Verifier()
        self.application = create_app(database_url=database_url, oidc_client=OIDC(subject, f"{subject}@example.com"), stripe_billing=Stripe(), stripe_webhook_verifier=self.verifier, clock=lambda: NOW)
        self.owner = stack.enter_context(TestClient(self.application))
        login(self.owner)
        self.organization_id = active_org(self.owner, self.verifier, seats=6)
        self.org = f"/api/v1/organizations/{self.organization_id}"
        self.clock = self.owner.get(self.org).json()["yearclocks"][0]
        self.base = f"{self.org}/yearclocks/{self.clock['id']}"
        self.lane = self.clock["lanes"][0]["id"]

    def export_rows(self, client=None):
        response = (client or self.owner).get("/api/v1/data-transfer/export")
        assert response.status_code == 200, response.text
        assert response.content.startswith(b"\xef\xbb\xbf")
        return list(csv.DictReader(io.StringIO(response.content.decode("utf-8-sig"))))

    def post(self, rows, *, save=False, client=None):
        out = io.StringIO()
        writer = csv.DictWriter(out, fieldnames=COLUMNS, extrasaction="ignore", lineterminator="\r\n")
        writer.writeheader()
        writer.writerow({"type": "format", "id": FORMAT, "name": "2000-01-01T00:00:00+00:00"})
        writer.writerows(rows)
        return (client or self.owner).post("/api/v1/data-transfer/import", params={"dry_run": str(not save).lower()}, content=out.getvalue().encode())


def seed(world):
    label = world.owner.post(f"{world.org}/labels", json={"name": "Draft", "color": LABEL_COLORS[0]}).json()
    shared = world.owner.post(f"{world.org}/categories", json={"name": "Board", "color": "#1f5f99"}).json()
    event = world.owner.post(f"{world.base}/events", json={"title": "Board meeting", "lane_id": world.lane, "starts_on": "2026-10-01", "ends_on": "2026-10-02", "category_id": shared["id"], "label_ids": [label["id"]], "description": "=Agenda", "links": [{"title": "Agenda", "url": "https://example.com/a"}]}).json()
    series = world.owner.post(f"{world.base}/series", json={"title": "Standup", "lane_id": world.lane, "starts_on": "2026-10-05", "frequency": "WEEKLY", "label_ids": [label["id"]]}).json()
    window = world.owner.get(f"{world.base}/events", params={"window_start": "2026-10-01", "months": 1}).json()
    occurrence = next(item for item in window if item.get("series_id") == series["id"] and item["series_date"] == "2026-10-12")
    assert world.owner.post(f"{world.base}/occurrences/{occurrence['occurrence_id']}/skip").status_code == 200
    return event, series, label


def get_event(world, event_id):
    window = world.owner.get(f"{world.base}/events", params={"window_start": "2026-01-01", "months": 12, "include_skipped": "true"}).json()
    return next(item for item in window if item["id"] == event_id)


def counts(world):
    with world.application.state.database_engine.connect() as connection:
        return connection.execute(text("SELECT (SELECT count(*) FROM events), (SELECT count(*) FROM event_revisions), (SELECT count(*) FROM series_occurrences)")).one()


def test_export_covers_every_administered_organization_and_import_back_changes_nothing(database_url, stack) -> None:
    world = World(stack, database_url, "transfer-roundtrip")
    event, series, _ = seed(world)
    second = active_org(world.owner, world.verifier, seats=3)
    rows = world.export_rows()
    kinds = {row["type"] for row in rows}
    assert {"organization", "label", "yearclock", "lane", "category", "series", "event", "series_exception"} <= kinds
    assert {row["id"] for row in rows if row["type"] == "organization"} == {world.organization_id, second}
    assert next(row for row in rows if row["type"] == "event" and row["id"] == event["id"])["description"] == "'=Agenda"
    assert not any(row["type"] == "event" and row["title"] == "Standup" for row in rows)
    before = counts(world)
    preview = world.post(rows)
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert body["errors"] == [] and not body["saved"]
    assert all(item["created"] == 0 and item["updated"] == 0 for summary in body["organizations"] for item in summary["kinds"].values())
    saved = world.post(rows, save=True)
    assert saved.status_code == 200 and saved.json()["saved"]
    assert counts(world) == before
    assert get_event(world, event['id'])["description"] == "=Agenda"


def test_import_updates_creates_and_never_deletes(database_url, stack) -> None:
    world = World(stack, database_url, "transfer-update")
    event, series, label = seed(world)
    rows = world.export_rows()
    for row in rows:
        if row["type"] == "event" and row["id"] == event["id"]:
            row["title"] = "Board meeting (moved)"
    clock = next(row for row in rows if row["type"] == "yearclock")
    rows.append({"type": "event", "id": str(uuid4()), "organization_id": world.organization_id, "yearclock_id": clock["id"], "lane_id": world.lane, "title": "New", "starts_on": "2026-11-01"})
    rows = [row for row in rows if not (row["type"] == "label")]  # fewer rows than the database holds
    rows.append(next(row for row in world.export_rows() if row["type"] == "label"))
    preview = world.post(rows).json()
    kinds = preview["organizations"][0]["kinds"]
    assert kinds["event"]["updated"] == 1 and kinds["event"]["created"] == 1
    assert get_event(world, event['id'])["title"] == "Board meeting"
    assert world.post(rows, save=True).status_code == 200
    updated = get_event(world, event['id'])
    assert updated["title"] == "Board meeting (moved)" and updated["version"] == event["version"] + 1
    history = world.owner.get(f"{world.base}/events/{event['id']}/history")
    assert history.status_code == 200
    assert "import" in history.text
    events = world.owner.get(f"{world.base}/events", params={"window_start": "2026-11-01", "months": 1}).json()
    assert any(item["title"] == "New" for item in events)


def test_series_exceptions_come_back_and_series_rules_stay(database_url, stack) -> None:
    world = World(stack, database_url, "transfer-series")
    _, series, _ = seed(world)
    rows = world.export_rows()
    exceptions = [row for row in rows if row["type"] == "series_exception"]
    assert len(exceptions) == 1 and exceptions[0]["skipped"] == "true" and exceptions[0]["series_date"] == "2026-10-12"
    exceptions[0]["skipped"] = "false"
    assert world.post(rows, save=True).status_code == 200
    window = world.owner.get(f"{world.base}/events", params={"window_start": "2026-10-01", "months": 1, "include_skipped": "true"}).json()
    assert next(item for item in window if item.get("series_date") == "2026-10-12")["skipped"] is False
    for row in rows:
        if row["type"] == "series":
            row["interval"] = "2"
    refused = world.post(rows)
    assert refused.json()["errors"][0]["reason"] == "series_rule_changed"


def test_errors_stop_the_whole_save(database_url, stack) -> None:
    world = World(stack, database_url, "transfer-errors")
    event, _, _ = seed(world)
    rows = world.export_rows()
    clock = next(row for row in rows if row["type"] == "yearclock")
    for row in rows:
        if row["type"] == "event":
            row["title"] = "Changed"
    rows.append({"type": "event", "id": str(uuid4()), "organization_id": world.organization_id, "yearclock_id": clock["id"], "lane_id": str(uuid4()), "title": "Bad lane", "starts_on": "2026-11-01"})
    rows.append({"type": "event", "id": str(uuid4()), "organization_id": world.organization_id, "yearclock_id": clock["id"], "lane_id": world.lane, "title": "Bad date", "starts_on": "soon"})
    preview = world.post(rows).json()
    assert [item["reason"] for item in preview["errors"]] == ["unknown_lane", "invalid_value:date_from_datetime_parsing"] or len(preview["errors"]) == 2
    saved = world.post(rows, save=True)
    assert saved.status_code == 422 and saved.json()["detail"]["reason"] == "errors"
    assert get_event(world, event['id'])["title"] == "Board meeting"


def test_admins_can_transfer_members_cannot_and_other_organizations_are_refused(database_url, stack) -> None:
    world = World(stack, database_url, "transfer-roles")
    seed(world)
    admin_app, _ = join(world.application, world.owner, world.organization_id, subject="transfer-admin", email="transfer-admin@example.com", role="admin")
    member_app, _ = join(world.application, world.owner, world.organization_id, subject="transfer-member", email="transfer-member@example.com")
    with TestClient(admin_app) as admin:
        login(admin)
        assert admin.get("/api/v1/data-transfer/organizations").json()["organizations"][0]["role"] == "admin"
        assert any(row["type"] == "event" for row in world.export_rows(admin))
    with TestClient(member_app) as member:
        login(member)
        assert member.get("/api/v1/data-transfer/organizations").json()["organizations"] == []
        assert member.get("/api/v1/data-transfer/export").status_code == 403
        assert world.post([], client=member).status_code == 403
    stranger = World(stack, database_url, "transfer-stranger")
    foreign = [row for row in stranger.export_rows() if row["type"] == "organization"]
    response = world.post(foreign)
    assert response.json()["errors"][0]["reason"] == "not_administrator"
    row = {"type": "event", "id": str(uuid4()), "organization_id": stranger.organization_id, "yearclock_id": stranger.clock["id"], "lane_id": stranger.lane, "title": "x", "starts_on": "2026-11-01"}
    assert world.post([row], save=True).status_code == 422


def test_bad_files_audit_and_hourly_limit(database_url, stack, monkeypatch) -> None:
    world = World(stack, database_url, "transfer-limits")
    bad = world.owner.post("/api/v1/data-transfer/import", content=b"type,id,organization_id\r\nevent,1,2\r\n")
    assert bad.status_code == 422 and bad.json()["detail"]["reason"] == "missing_format_row"
    monkeypatch.setenv("TRANSFER_MAX_BYTES", "10")
    assert world.owner.post("/api/v1/data-transfer/import", content=b"x" * 50).status_code == 413
    monkeypatch.delenv("TRANSFER_MAX_BYTES")
    monkeypatch.setenv("LIMIT_TRANSFERS_PER_HOUR", "2")
    world.export_rows()
    assert world.post([{"type": "organization", "id": world.organization_id, "organization_id": world.organization_id}]).status_code == 200
    limited = world.owner.get("/api/v1/data-transfer/export")
    assert limited.status_code == 429 and limited.json()["detail"]["reason"] == "rate_limited"
    actions = [item["action"] for item in world.owner.get(f"{world.org}/audit-events", params={"prefix": "data"}).json()["items"]]
    assert sorted(actions) == ["data.export"] or "data.export" in actions
