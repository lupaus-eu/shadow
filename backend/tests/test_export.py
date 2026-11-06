"""Export Events to Excel and CSV (Yearclock V2, P7 ticket 02)."""
import csv
import io
from contextlib import ExitStack

import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook

from app.label_routes import LABEL_COLORS
from app.main import create_app
from test_invitations import NOW, OIDC, Stripe, Verifier, active_org, join, login


@pytest.fixture
def stack():
    with ExitStack() as clients:
        yield clients


class World:
    def __init__(self, stack, database_url, subject):
        verifier = Verifier()
        self.application = create_app(database_url=database_url, oidc_client=OIDC(subject, f"{subject}@example.com"), stripe_billing=Stripe(), stripe_webhook_verifier=verifier, clock=lambda: NOW)
        self.owner = stack.enter_context(TestClient(self.application))
        login(self.owner)
        self.organization_id = active_org(self.owner, verifier, seats=4)
        self.org = f"/api/v1/organizations/{self.organization_id}"
        self.clock = self.owner.get(self.org).json()["yearclocks"][0]
        self.base = f"{self.org}/yearclocks/{self.clock['id']}"
        self.lane = self.clock["lanes"][0]["id"]
        self.finance = self.owner.post(f"{self.base}/lanes", json={"name": "Finance"}).json()
        self.board = self.owner.post(f"{self.org}/categories", json={"name": "Board", "color": "#1f5f99"}).json()
        self.draft = self.owner.post(f"{self.org}/labels", json={"name": "Draft", "color": LABEL_COLORS[0]}).json()
        self.final = self.owner.post(f"{self.org}/labels", json={"name": "Final", "color": LABEL_COLORS[1]}).json()

    def event(self, title, starts_on, **extra):
        body = {"title": title, "lane_id": self.lane, "starts_on": starts_on, **extra}
        body["lane_id"] = extra.get("lane_id", self.lane)
        response = self.owner.post(f"{self.base}/events", json=body)
        assert response.status_code == 201, response.text
        return response.json()

    def export(self, client=None, **body):
        return (client or self.owner).post(f"{self.base}/export", json={"format": "xlsx", "scope": "all", **body})

    def audit(self):
        return self.owner.get(f"{self.org}/audit-events", params={"prefix": "yearclock"}).json()["items"]


def sheet_rows(response):
    sheet = load_workbook(io.BytesIO(response.content)).active
    return [list(row) for row in sheet.iter_rows(values_only=True)]


def test_xlsx_has_the_columns_dates_and_rows_of_the_yearclock(database_url, stack) -> None:
    world = World(stack, database_url, "export-xlsx")
    world.event("Board meeting", "2026-10-01", category_id=world.board["id"], label_ids=[world.final["id"], world.draft["id"]], description="Budget", location="Room 4", links=[{"title": "Board", "url": "https://example.com/board"}, {"title": "Slides", "url": "https://example.com/slides"}])
    world.event("Audit period", "2026-11-02", ends_on="2026-11-20")
    response = world.export()
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    assert response.headers["content-disposition"].startswith('attachment; filename="')
    assert response.headers["cache-control"] == "no-store"
    header, board, audit = sheet_rows(response)
    assert header == ["Title", "Starts", "Ends", "Start time", "End time", "Lane", "Category", "Labels", "Location", "Description", "Links", "Series", "Source"]
    assert board[0] == "Board meeting" and board[1].date().isoformat() == "2026-10-01" and board[2] is None
    assert board[3:5] == [None, None] and board[5:11] == ["General", "Board", "Draft, Final", "Room 4", "Budget", "Board | https://example.com/board\nSlides | https://example.com/slides"]
    assert audit[0] == "Audit period" and audit[2].date().isoformat() == "2026-11-20"


def test_csv_in_finnish_uses_a_semicolon_a_byte_order_mark_and_finnish_headers(database_url, stack) -> None:
    world = World(stack, database_url, "export-csv")
    world.event("Hallituksen kokous", "2026-10-01")
    world.owner.post(f"{world.base}/series", json={"title": "Viikkopalaveri", "lane_id": world.lane, "starts_on": "2026-10-05", "frequency": "WEEKLY"})
    response = world.export(format="csv", locale="fi", scope="window", window_start="2026-10-01", length=1)
    assert response.status_code == 200 and response.headers["content-type"].startswith("text/csv")
    assert response.content.startswith("﻿".encode())
    rows = list(csv.reader(io.StringIO(response.content.decode("utf-8-sig")), delimiter=";"))
    assert rows[0] == ["Otsikko", "Alkaa", "Päättyy", "Alkamisaika", "Päättymisaika", "Kehä", "Kategoria", "Tunnisteet", "Sijainti", "Kuvaus", "Linkit", "Sarja", "Lähde"]
    assert rows[1][:2] == ["Hallituksen kokous", "2026-10-01"]
    weekly = [row for row in rows if row[0] == "Viikkopalaveri"]
    assert len(weekly) == 4 and {row[11] for row in weekly} == {"Viikoittain"}


def test_cells_that_look_like_formulas_are_neutralized_in_both_formats(database_url, stack) -> None:
    world = World(stack, database_url, "export-formulas")
    world.event("=SUM(A1:A2)", "2026-10-01", description="@cmd", links=[{"title": "A", "url": "https://example.com/a"}])
    world.event("+1+1", "2026-10-02", description="-2+3")
    xlsx = sheet_rows(world.export())
    assert [row[0] for row in xlsx[1:]] == ["'=SUM(A1:A2)", "'+1+1"] and xlsx[1][9] == "'@cmd" and xlsx[2][9] == "'-2+3"
    text = world.export(format="csv").content.decode("utf-8-sig")
    assert "'=SUM(A1:A2)" in text and "\r\n'+1+1," in text and ",'@cmd," in text


def test_window_scope_and_filters_choose_the_rows(database_url, stack) -> None:
    world = World(stack, database_url, "export-filters")
    world.event("In window", "2026-10-01", category_id=world.board["id"], label_ids=[world.draft["id"]])
    world.event("Outside window", "2027-02-01")
    world.event("Finance event", "2026-10-03", lane_id=world.finance["id"])
    finance = world.finance["id"]
    titles = lambda response: [row[0] for row in sheet_rows(response)[1:]]
    assert titles(world.export(scope="window", window_start="2026-10-01", length=3)) == ["In window", "Finance event"]
    assert titles(world.export()) == ["In window", "Finance event", "Outside window"]
    assert titles(world.export(filters={"lanes": [finance]})) == ["Finance event"]
    assert titles(world.export(filters={"categories": [world.board["id"]]})) == ["In window"]
    assert titles(world.export(filters={"categories": ["none"]})) == ["Finance event", "Outside window"]
    assert titles(world.export(filters={"labels": [world.draft["id"]]})) == ["In window"]
    assert titles(world.export(filters={"lanes": [world.lane], "categories": ["none"]})) == ["Outside window"]


def test_skipped_occurrences_and_deleted_events_are_left_out(database_url, stack) -> None:
    world = World(stack, database_url, "export-hidden")
    gone = world.event("Deleted", "2026-10-01")
    assert world.owner.delete(f"{world.base}/events/{gone['id']}", params={"expected_version": gone["version"]}).status_code == 204
    world.owner.post(f"{world.base}/series", json={"title": "Standup", "lane_id": world.lane, "starts_on": "2026-10-05", "frequency": "WEEKLY"})
    occurrences = [item for item in world.owner.get(f"{world.base}/events", params={"window_start": "2026-10-01", "months": 1}).json() if item["occurrence_id"]]
    assert world.owner.post(f"{world.base}/occurrences/{occurrences[1]['occurrence_id']}/skip", params={"expected_version": occurrences[1]["version"]}).status_code in {200, 204}
    rows = sheet_rows(world.export(scope="window", window_start="2026-10-01", length=1))[1:]
    assert [row[0] for row in rows] == ["Standup", "Standup", "Standup"] and all(row[11] == "Weekly" for row in rows)


def test_a_linked_lane_exports_with_its_source(database_url, stack) -> None:
    world = World(stack, database_url, "export-linked")
    source = world.owner.post(f"{world.org}/yearclocks", json={"name": "Team year"}).json()
    source_lane = source["lanes"][0]
    assert world.owner.post(f"{world.org}/yearclocks/{source['id']}/events", json={"title": "Sprint review", "lane_id": source_lane["id"], "starts_on": "2026-10-10"}).status_code == 201
    assert world.owner.post(f"{world.base}/lanes/link", json={"source_lane_id": source_lane["id"]}).status_code == 201
    rows = sheet_rows(world.export())
    assert [row[0] for row in rows[1:]] == ["Sprint review"] and rows[1][12] == "Team year"


def test_a_reader_who_may_not_read_the_source_gets_none_of_its_events(database_url, stack) -> None:
    world = World(stack, database_url, "export-linked-hidden")
    source = world.owner.post(f"{world.org}/yearclocks", json={"name": "Private source"}).json()
    assert world.owner.post(f"{world.org}/yearclocks/{source['id']}/events", json={"title": "Hidden sprint", "lane_id": source["lanes"][0]["id"], "starts_on": "2026-10-10"}).status_code == 201
    assert world.owner.post(f"{world.base}/lanes/link", json={"source_lane_id": source["lanes"][0]["id"]}).status_code == 201
    world.event("Own event", "2026-10-01")
    application, user_id = join(world.application, world.owner, world.organization_id, subject="export-linked-viewer", email="export-linked-viewer@example.com")
    viewer = stack.enter_context(TestClient(application))
    login(viewer)
    assert world.owner.put(f"{world.base}/access", json={"user_account_id": user_id, "role": "viewer"}).status_code == 200
    assert [row[0] for row in sheet_rows(world.export())[1:]] == ["Own event", "Hidden sprint"]
    assert [row[0] for row in sheet_rows(world.export(viewer))[1:]] == ["Own event"]


def test_readers_export_and_everyone_else_is_refused(database_url, stack) -> None:
    world = World(stack, database_url, "export-access")
    world.event("Board meeting", "2026-10-01")
    clients = {}
    for name in ("viewer", "member"):
        application, user_id = join(world.application, world.owner, world.organization_id, subject=f"export-{name}", email=f"export-{name}@example.com")
        clients[name] = stack.enter_context(TestClient(application))
        login(clients[name])
        if name == "viewer":
            assert world.owner.put(f"{world.base}/access", json={"user_account_id": user_id, "role": "viewer"}).status_code == 200
    assert world.export(clients["viewer"]).status_code == 200
    assert world.export(clients["member"]).status_code in {403, 404}
    anonymous = TestClient(create_app(database_url=database_url, oidc_client=OIDC("export-nobody", "export-nobody@example.com"), stripe_billing=Stripe(), stripe_webhook_verifier=Verifier(), clock=lambda: NOW))
    with anonymous:
        assert world.export(anonymous).status_code == 401


def test_every_export_is_audited_without_content_and_counted(database_url, stack) -> None:
    world = World(stack, database_url, "export-audit")
    world.event("Secret title", "2026-10-01")
    assert world.export().status_code == 200
    assert world.export(format="csv", locale="fi").status_code == 200
    entries = world.audit()
    assert [(item["action"], item["change_summary"]["format"], item["change_summary"]["rows"]) for item in entries] == [("yearclock.export", "csv", 1), ("yearclock.export", "xlsx", 1)]
    assert "Secret title" not in str(entries)


def test_the_hourly_limit_refuses_with_429_and_says_when_to_retry(database_url, stack, monkeypatch) -> None:
    monkeypatch.setenv("LIMIT_EXPORTS_PER_HOUR", "2")
    world = World(stack, database_url, "export-limit")
    assert world.export().status_code == 200 and world.export().status_code == 200
    refused = world.export()
    assert refused.status_code == 429
    detail = refused.json()["detail"]
    assert detail["reason"] == "rate_limited" and detail["maximum"] == 2 and 1 <= detail["retry_after_seconds"] <= 3600
    assert refused.headers["retry-after"] == str(detail["retry_after_seconds"])
    assert len(world.audit()) == 2


def test_the_browser_may_read_the_file_name_and_retry_time(database_url, stack) -> None:
    world = World(stack, database_url, "export-cors")
    response = world.owner.post(f"{world.base}/export", json={"format": "csv", "scope": "all"}, headers={"Origin": "http://localhost:8173"})
    exposed = {name.strip().lower() for name in response.headers["access-control-expose-headers"].split(",")}
    assert {"content-disposition", "retry-after"} <= exposed


def test_an_unsupported_window_length_is_refused(database_url, stack) -> None:
    world = World(stack, database_url, "export-length")
    assert world.export(scope="window", length=5).status_code == 422
    assert world.export(format="pdf").status_code == 422


def unfold(text: str) -> list[str]:
    return text.replace("\r\n ", "").split("\r\n")


def test_ics_has_all_day_events_with_exclusive_end_dates_and_stable_uids(database_url, stack) -> None:
    world = World(stack, database_url, "export-ics")
    world.event("Board; meeting, \\ budget", "2026-10-01", category_id=world.board["id"], label_ids=[world.draft["id"]], description="Line one\nLine two", location="Room; 4, west", links=[{"title": "Board", "url": "https://example.com/board"}, {"title": "Slides", "url": "https://example.com/slides"}])
    world.event("Audit period", "2026-11-02", ends_on="2026-11-20")
    world.owner.post(f"{world.base}/series", json={"title": "Weekly", "lane_id": world.lane, "starts_on": "2026-10-05", "frequency": "WEEKLY"})
    first = world.export(format="ics", scope="window", window_start="2026-10-01", length=3)
    assert first.status_code == 200 and first.headers["content-type"].startswith("text/calendar")
    assert first.headers["content-disposition"].startswith('attachment; filename="') and '.ics"' in first.headers["content-disposition"]
    lines = unfold(first.content.decode())
    assert lines[:3] == ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Yearclock//Export//EN"] and lines[-2:] == ["END:VCALENDAR", ""]
    assert "SUMMARY:Board\\; meeting\\, \\\\ budget" in lines 
    assert "CATEGORIES:Board,Draft" in lines and "URL:https://example.com/board" in lines
    assert "LOCATION:Room\\; 4\\, west" in lines and "DESCRIPTION:Line one\\nLine two\\n\\nSlides: https://example.com/slides" in lines
    assert "DTSTART;VALUE=DATE:20261101" not in lines and "DTSTART;VALUE=DATE:20261102" in lines and "DTEND;VALUE=DATE:20261121" in lines
    assert "DTSTART;VALUE=DATE:20261001" in lines and "DTEND;VALUE=DATE:20261002" in lines
    assert not any(line.startswith(("RRULE", "BEGIN:VALARM", "ATTENDEE")) for line in lines)
    assert sum(1 for line in lines if line == "SUMMARY:Weekly") >= 12
    uids = [line for line in lines if line.startswith("UID:")]
    assert len(uids) == len(set(uids)) and all(uid.endswith("@yearclock") for uid in uids)
    again = unfold(world.export(format="ics", scope="window", window_start="2026-10-01", length=3).content.decode())
    assert [line for line in again if line.startswith("UID:")] == uids


def test_ics_lines_are_folded_at_75_octets_without_splitting_characters(database_url, stack) -> None:
    world = World(stack, database_url, "export-ics-fold")
    world.event("Ä" * 150, "2026-10-01")
    text = world.export(format="ics").content.decode()
    assert all(len(line.encode()) <= 75 for line in text.split("\r\n"))
    assert "SUMMARY:" + "Ä" * 150 in unfold(text)


def test_ics_follows_the_export_access_audit_and_limit(database_url, stack, monkeypatch) -> None:
    monkeypatch.setenv("LIMIT_EXPORTS_PER_HOUR", "2")
    world = World(stack, database_url, "export-ics-rules")
    world.event("Secret title", "2026-10-01")
    application, user_id = join(world.application, world.owner, world.organization_id, subject="export-ics-viewer", email="export-ics-viewer@example.com")
    viewer = stack.enter_context(TestClient(application))
    login(viewer)
    assert world.export(viewer, format="ics").status_code in {403, 404}
    assert world.owner.put(f"{world.base}/access", json={"user_account_id": user_id, "role": "viewer"}).status_code == 200
    assert world.export(viewer, format="ics").status_code == 200
    assert world.export(format="ics").status_code == 200 and world.export(format="ics").status_code == 200
    assert world.export(format="ics").status_code == 429
    entries = world.audit()
    assert [(item["change_summary"]["format"], item["change_summary"]["rows"]) for item in entries if item["action"] == "yearclock.export"] == [("ics", 1)] * 3
    assert "Secret title" not in str(entries)
