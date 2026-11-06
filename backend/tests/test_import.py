"""Import Events from Excel and CSV (Yearclock V2, P7 ticket 03)."""
import io
import zipfile
from contextlib import ExitStack

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook, load_workbook
from sqlalchemy import text

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

    def upload(self, content, fmt="csv", dry_run=True, client=None):
        return (client or self.owner).post(f"{self.base}/import", params={"format": fmt, "dry_run": str(dry_run).lower()}, content=content, headers={"Content-Type": "application/octet-stream"})

    def events(self):
        return [item for item in self.owner.get(f"{self.base}/events", params={"window_start": "2026-01-01", "months": 24}).json()]

    def audit(self):
        return self.owner.get(f"{self.org}/audit-events", params={"prefix": "yearclock"}).json()["items"]


def xlsx(rows, header=("Title", "Starts", "Ends", "Lane", "Category", "Labels", "Description", "Link")):
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(list(header))
    for row in rows:
        sheet.append(list(row))
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def csv_text(*lines, bom=False, encoding="utf-8"):
    return (("﻿" if bom else "") + "\r\n".join(lines) + "\r\n").encode(encoding)


GOOD = csv_text("Title,Starts,Ends,Lane,Category,Labels,Description,Link", "Board meeting,2026-10-01,,General,Board,Draft; Final,Budget,https://example.com/a", "Audit period,2026-11-02,2026-11-20,Finance,,,,")


def test_a_preview_saves_nothing_and_a_save_creates_the_events_with_history_and_audit(database_url, stack) -> None:
    world = World(stack, database_url, "import-save")
    preview = world.upload(GOOD)
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert body["rows"] == 2 and body["errors"] == [] and body["skipped"] == [] and body["created"] == 0
    assert [(row["row"], row["title"], row["lane"], row["category"], row["labels"]) for row in body["create"]] == [(2, "Board meeting", "General", "Board", ["Draft", "Final"]), (3, "Audit period", "Finance", None, [])]
    assert world.events() == []
    saved = world.upload(GOOD, dry_run=False)
    assert saved.status_code == 200, saved.text
    result = saved.json()
    assert result["created"] == 2 and result["import_id"]
    events = world.events()
    assert [(item["title"], item["starts_on"], item["ends_on"]) for item in events] == [("Board meeting", "2026-10-01", None), ("Audit period", "2026-11-02", "2026-11-20")]
    first = next(item for item in events if item["title"] == "Board meeting")
    assert first["category_id"] == world.board["id"] and sorted(first["label_ids"]) == sorted([world.draft["id"], world.final["id"]]) and first["lane_id"] == world.lane
    history = world.owner.get(f"{world.base}/events/{first['id']}/history").json()["items"]
    assert history[-1]["reason"] == "import" and history[-1]["reason_detail"]["import_id"] == result["import_id"]
    actions = [item["action"] for item in world.audit()]
    assert actions.count("yearclock.import_preview") == 1 and actions.count("yearclock.import") == 1
    summary = next(item for item in world.audit() if item["action"] == "yearclock.import")["change_summary"]
    assert summary["created"] == 2 and summary["import_id"] == result["import_id"] and "Board meeting" not in str(world.audit())
    created = [item for item in world.owner.get(f"{world.org}/audit-events", params={"prefix": "event"}).json()["items"] if item["action"] == "event.created"]
    assert len(created) == 2 and all(item["change_summary"]["import_id"] == result["import_id"] for item in created)


def test_an_exported_file_is_a_valid_import_and_series_rows_are_skipped(database_url, stack) -> None:
    world = World(stack, database_url, "import-roundtrip")
    world.owner.post(f"{world.base}/events", json={"title": "Plain", "lane_id": world.lane, "starts_on": "2026-10-01", "category_id": world.board["id"], "label_ids": [world.draft["id"]]})
    world.owner.post(f"{world.base}/series", json={"title": "Standup", "lane_id": world.lane, "starts_on": "2026-10-05", "frequency": "WEEKLY"})
    exported = world.owner.post(f"{world.base}/export", json={"format": "xlsx", "scope": "window", "window_start": "2026-10-01", "length": 1})
    target = world.owner.post(f"{world.org}/yearclocks", json={"name": "Copy"}).json()
    response = world.owner.post(f"{world.org}/yearclocks/{target['id']}/import", params={"format": "xlsx", "dry_run": "false"}, content=exported.content)
    assert response.status_code == 200, response.text
    body = response.json()
    assert [row["title"] for row in body["create"]] == ["Plain"] and {item["reason"] for item in body["skipped"]} == {"series"} and len(body["skipped"]) == 4


def test_every_row_problem_is_reported_with_its_row_and_a_save_with_errors_creates_nothing(database_url, stack) -> None:
    world = World(stack, database_url, "import-errors")
    linked_source = world.owner.post(f"{world.org}/yearclocks", json={"name": "Source"}).json()
    sprints = world.owner.post(f"{world.org}/yearclocks/{linked_source['id']}/lanes", json={"name": "Sprints"}).json()
    assert world.owner.post(f"{world.base}/lanes/link", json={"source_lane_id": sprints["id"]}).status_code == 201
    content = xlsx([
        ("", "2026-10-01", None, "General", None, None, None, None),
        ("No start", None, None, "General", None, None, None, None),
        ("Bad date", "someday", None, "General", None, None, None, None),
        ("Backwards", "2026-10-05", "2026-10-01", "General", None, None, None, None),
        ("No lane", "2026-10-01", None, None, None, None, None, None),
        ("Unknown lane", "2026-10-01", None, "Operations", None, None, None, None),
        ("Linked lane", "2026-10-01", None, "Sprints", None, None, None, None),
        ("Unknown category", "2026-10-01", None, "General", "Nope", None, None, None),
        ("Unknown label", "2026-10-01", None, "General", None, "Draft, Mystery", None, None),
        ("x" * 201, "2026-10-01", None, "General", None, None, None, None),
        ("Bad link", "2026-10-01", None, "General", None, None, None, "ftp://example.com"),
        ("Fine", "2026-10-02", None, "General", None, None, None, None),
    ])
    preview = world.upload(content, "xlsx").json()
    problems = {(issue["row"], issue["column"], issue["reason"]) for issue in preview["errors"]}
    assert problems == {(2, "title", "missing_title"), (3, "starts", "missing_start"), (4, "starts", "invalid_date"), (5, "ends", "end_before_start"), (6, "lane", "missing_lane"), (7, "lane", "unknown_lane"), (8, "lane", "linked_lane"), (9, "category", "unknown_category"), (10, "labels", "unknown_label"), (11, "title", "title_too_long"), (12, "links", "invalid_link")}
    assert [row["title"] for row in preview["create"]] == ["Fine"]
    refused = world.upload(content, "xlsx", dry_run=False)
    assert refused.status_code == 422 and refused.json()["detail"]["reason"] == "errors" and len(refused.json()["detail"]["errors"]) == len(preview["errors"])
    assert world.events() == []


def test_existing_events_are_skipped_and_a_repeat_in_the_file_is_an_error(database_url, stack) -> None:
    world = World(stack, database_url, "import-duplicates")
    world.owner.post(f"{world.base}/events", json={"title": "Board meeting", "lane_id": world.lane, "starts_on": "2026-10-01"})
    content = csv_text("Title,Starts,Lane", "board MEETING,2026-10-01,general", "New one,2026-10-03,General", "New one,2026-10-03,General")
    body = world.upload(content).json()
    assert [(item["row"], item["reason"]) for item in body["skipped"]] == [(2, "duplicate")]
    assert [row["title"] for row in body["create"]] == ["New one"]
    assert [(issue["row"], issue["reason"], issue["value"]) for issue in body["errors"]] == [(4, "duplicate_in_file", "3")]


def test_columns_match_in_either_language_ignoring_case_and_accents_and_extras_are_ignored(database_url, stack) -> None:
    world = World(stack, database_url, "import-headers")
    finnish = csv_text("Otsikko;ALKAA;Päättyy;kehä;Kategoria;Tunnisteet;Muistiinpano", "Hallituksen kokous;2026-10-01;;General;board;draft;ignored", bom=True)
    body = world.upload(finnish).json()
    assert body["errors"] == [] and body["create"][0]["category"] == "Board" and body["create"][0]["labels"] == ["Draft"]
    missing = world.upload(csv_text("Title,Starts", "x,2026-10-01")).json()
    assert [(issue["row"], issue["reason"]) for issue in missing["errors"]] == [(1, "missing_column")] and "Lane" in missing["errors"][0]["column"]


def test_csv_with_a_semicolon_a_tab_or_windows_text_and_finnish_dates_reads(database_url, stack) -> None:
    world = World(stack, database_url, "import-csv")
    assert world.upload(csv_text("Title;Starts;Lane", "A;10.3.2026;General")).json()["create"][0]["starts_on"] == "2026-03-10"
    assert world.upload(csv_text("Title\tStarts\tLane", "B\t2026-03-11\tGeneral")).json()["create"][0]["title"] == "B"
    windows = csv_text("Title;Starts;Lane", "Päätös;2026-03-12;General", encoding="cp1252")
    assert world.upload(windows).json()["create"][0]["title"] == "Päätös"
    assert world.upload(b"\x00\x01\x02 not a spreadsheet").status_code == 422


def test_macro_files_unreadable_files_and_big_files_are_refused(database_url, stack, monkeypatch) -> None:
    world = World(stack, database_url, "import-files")
    macro = io.BytesIO()
    with zipfile.ZipFile(macro, "w") as archive:
        archive.writestr("xl/workbook.xml", "<workbook/>")
        archive.writestr("xl/vbaProject.bin", b"macro")
    refused = world.upload(macro.getvalue(), "xlsx")
    assert refused.status_code == 422 and refused.json()["detail"]["reason"] == "macros_not_allowed"
    assert world.upload(b"not a zip", "xlsx").json()["detail"]["reason"] == "unreadable_file"
    monkeypatch.setenv("IMPORT_MAX_BYTES", "100")
    big = world.upload(b"x" * 500)
    assert big.status_code == 413 and big.json()["detail"]["reason"] == "file_too_large"
    monkeypatch.setenv("IMPORT_MAX_BYTES", "2097152")
    monkeypatch.setenv("LIMIT_IMPORT_ROWS", "2")
    many = world.upload(csv_text("Title,Starts,Lane", "a,2026-01-01,General", "b,2026-01-02,General", "c,2026-01-03,General"))
    assert many.status_code == 422 and many.json()["detail"] == {"reason": "too_many_rows", "maximum": 2}


def test_formulas_are_never_evaluated_and_neutralized_text_is_restored(database_url, stack) -> None:
    world = World(stack, database_url, "import-formulas")
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["Title", "Starts", "Lane"])
    sheet.append(["=1+1", "2026-10-01", "General"])
    sheet.append(["'=HYPERLINK(\"x\")", "2026-10-02", "General"])
    buffer = io.BytesIO()
    workbook.save(buffer)
    body = world.upload(buffer.getvalue(), "xlsx").json()
    assert [(issue["row"], issue["reason"]) for issue in body["errors"]] == [(2, "missing_title")]
    assert [row["title"] for row in body["create"]] == ['=HYPERLINK("x")']


def test_the_event_limit_is_checked_for_the_whole_batch(database_url, stack, monkeypatch) -> None:
    monkeypatch.setenv("LIMIT_EVENTS_PER_YEARCLOCK", "2")
    world = World(stack, database_url, "import-ceiling")
    world.owner.post(f"{world.base}/events", json={"title": "Existing", "lane_id": world.lane, "starts_on": "2026-10-01"})
    content = csv_text("Title,Starts,Lane", "A,2026-10-02,General", "B,2026-10-03,General")
    assert world.upload(content).status_code == 200
    refused = world.upload(content, dry_run=False)
    assert refused.status_code == 409 and refused.json()["detail"]["reason"] == "limit_reached"
    assert len(world.events()) == 1


def test_editors_import_and_viewers_and_read_only_organizations_cannot(database_url, stack) -> None:
    world = World(stack, database_url, "import-roles")
    clients = {}
    for name, role in (("viewer", "viewer"), ("editor", "editor")):
        application, user_id = join(world.application, world.owner, world.organization_id, subject=f"import-{name}", email=f"import-{name}@example.com")
        clients[name] = stack.enter_context(TestClient(application))
        login(clients[name])
        assert world.owner.put(f"{world.base}/access", json={"user_account_id": user_id, "role": role}).status_code == 200
    assert world.upload(GOOD, client=clients["viewer"]).status_code == 403
    assert world.upload(GOOD, dry_run=False, client=clients["editor"]).status_code == 200
    with world.application.state.database_engine.begin() as connection:
        connection.execute(text("UPDATE organizations SET subscription_access_state = 'canceled' WHERE id = :id"), {"id": world.organization_id})
    assert world.upload(GOOD).status_code == 403


def test_the_template_has_the_columns_and_the_allowed_names_in_the_users_language(database_url, stack) -> None:
    world = World(stack, database_url, "import-template")
    english = world.owner.get(f"{world.base}/import/template")
    assert english.status_code == 200 and "attachment" in english.headers["content-disposition"]
    book = load_workbook(io.BytesIO(english.content))
    assert [cell.value for cell in book.worksheets[0][1]] == ["Title", "Starts", "Ends", "Start time", "End time", "Lane", "Category", "Labels", "Location", "Description", "Links"]
    allowed = [list(row) for row in book.worksheets[1].iter_rows(values_only=True)]
    assert allowed[0] == ["Lanes", "Categories", "Labels"] and {row[0] for row in allowed[1:]} == {"General", "Finance"} and "Board" in {row[1] for row in allowed[1:]} and {"Draft", "Final"} <= {row[2] for row in allowed[1:]}
    finnish = load_workbook(io.BytesIO(world.owner.get(f"{world.base}/import/template", params={"locale": "fi"}).content))
    assert [cell.value for cell in finnish.worksheets[0][1]][:3] == ["Otsikko", "Alkaa", "Päättyy"]
    # The template is itself importable (an empty sheet creates nothing).
    assert world.upload(english.content, "xlsx").json()["rows"] == 0


def test_previews_and_saves_count_against_the_hourly_limit(database_url, stack, monkeypatch) -> None:
    monkeypatch.setenv("LIMIT_EXPORTS_PER_HOUR", "2")
    world = World(stack, database_url, "import-limit")
    assert world.upload(GOOD).status_code == 200 and world.upload(GOOD).status_code == 200
    refused = world.upload(GOOD)
    assert refused.status_code == 429 and refused.json()["detail"]["reason"] == "rate_limited"


def test_location_and_links_columns_import_and_the_old_link_column_still_works(database_url, stack) -> None:
    world = World(stack, database_url, "import-content")
    content = csv_text(
        "Title,Starts,Lane,Location,Links",
        'Workshop,2026-10-01,General,"Room 4","Agenda | https://example.com/agenda\nhttps://example.org/plain"',
        "Review,2026-10-02,General,,",
    )
    saved = world.upload(content, dry_run=False)
    assert saved.status_code == 200, saved.text
    events = {item["title"]: item for item in world.events()}
    assert events["Workshop"]["location"] == "Room 4"
    assert events["Workshop"]["links"] == [{"title": "Agenda", "url": "https://example.com/agenda"}, {"title": "example.org", "url": "https://example.org/plain"}]
    assert events["Review"]["location"] is None and events["Review"]["links"] == []
    old = world.upload(csv_text("Title,Starts,Lane,Link", "Old file,2026-10-03,General,https://example.com/old"), dry_run=False)
    assert old.status_code == 200, old.text
    assert next(item for item in world.events() if item["title"] == "Old file")["links"] == [{"title": "example.com", "url": "https://example.com/old"}]


def test_location_and_link_problems_are_reported_per_row(database_url, stack) -> None:
    world = World(stack, database_url, "import-content-errors")
    many = "\n".join(f"https://example.com/{i}" for i in range(11))
    content = csv_text(
        "Title,Starts,Lane,Location,Links",
        f"Long place,2026-10-01,General,{'x' * 201},",
        "Bad address,2026-10-01,General,,Agenda | ftp://example.com",
        f'Too many,2026-10-01,General,,"{many}"',
        'Same twice,2026-10-01,General,,"https://example.com/a\nhttps://example.com/a"',
        f"Long title,2026-10-01,General,,{'t' * 101} | https://example.com/t",
    )
    problems = {(issue["row"], issue["column"], issue["reason"]) for issue in world.upload(content).json()["errors"]}
    assert problems == {(2, "location", "location_too_long"), (3, "links", "invalid_link"), (4, "links", "too_many_links"), (5, "links", "duplicate_link"), (6, "links", "link_title_too_long")}
    assert world.events() == []


def test_an_exported_file_with_locations_and_links_imports_back(database_url, stack) -> None:
    world = World(stack, database_url, "import-content-roundtrip")
    world.owner.post(f"{world.base}/events", json={"title": "Workshop", "lane_id": world.lane, "starts_on": "2026-10-01", "location": "Room 4", "links": [{"title": "Agenda", "url": "https://example.com/a"}, {"title": "Slides", "url": "https://example.com/s"}]})
    exported = world.owner.post(f"{world.base}/export", json={"format": "xlsx", "scope": "all"})
    target = world.owner.post(f"{world.org}/yearclocks", json={"name": "Copy"}).json()
    lane = target["lanes"][0]["name"]
    assert lane == "General" or lane
    response = world.owner.post(f"{world.org}/yearclocks/{target['id']}/import", params={"format": "xlsx", "dry_run": "false"}, content=exported.content)
    assert response.status_code == 200, response.text
    copied = world.owner.get(f"{world.org}/yearclocks/{target['id']}/events", params={"window_start": "2026-01-01", "months": 24}).json()
    assert copied[0]["location"] == "Room 4" and [item["title"] for item in copied[0]["links"]] == ["Agenda", "Slides"]
