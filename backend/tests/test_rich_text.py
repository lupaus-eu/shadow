"""The formatted description (Yearclock V2, P11 ticket 02)."""
import csv
import io
import json
from pathlib import Path

from app.rich_text import parse, plain_text
from test_export import sheet_rows  # noqa: F401 - used below
from test_notifications import World, stack  # noqa: F401 - the fixture

CASES = json.loads((Path(__file__).resolve().parents[2] / "frontend" / "tests" / "unit" / "rich-text-cases.json").read_text())


def test_every_shared_case_parses_and_flattens_as_recorded() -> None:
    # The frontend runs the same cases through its own parser (`frontend/tests/unit/rich-text.test.ts`).
    assert len(CASES) >= 20
    for case in CASES:
        assert parse(case["input"]) == case["blocks"], case["name"]
        assert plain_text(case["input"]) == case["plain"], case["name"]


def test_a_plain_description_is_never_interpreted_and_nothing_is_html() -> None:
    assert plain_text("**x** *y* [a](https://e.com)", "plain") == "**x** *y* [a](https://e.com)"
    assert plain_text(None) == "" and plain_text("") == ""
    html = next(case for case in CASES if case["name"] == "html is plain text")
    assert parse(html["input"]) == [{"p": [["<b>bold</b> <script>alert(1)</script>"]]}]  # tags are only ever text


def event(world, title, starts_on, **extra):
    response = world.owner.post(f"{world.base}/events", json={"title": title, "lane_id": world.clock["lanes"][0]["id"], "starts_on": starts_on, **extra})
    assert response.status_code == 201, response.text
    return response.json()


def test_the_format_defaults_to_plain_is_kept_on_update_and_can_be_chosen(database_url, stack) -> None:
    world = World(stack, database_url, "rich-format")
    plain = event(world, "Plain", "2026-10-01", description="**stays literal**")
    formatted = event(world, "Formatted", "2026-10-02", description="**bold**", description_format="markdown")
    assert plain["description_format"] == "plain" and formatted["description_format"] == "markdown"
    body = {"title": "Formatted", "lane_id": world.clock["lanes"][0]["id"], "starts_on": "2026-10-02", "expected_version": formatted["version"], "description": "**bolder**"}
    kept = world.owner.patch(f"{world.base}/events/{formatted['id']}", json=body)
    assert kept.status_code == 200 and kept.json()["description_format"] == "markdown"  # not named: kept
    switched = world.owner.patch(f"{world.base}/events/{plain['id']}", json={"title": "Plain", "lane_id": world.clock["lanes"][0]["id"], "starts_on": "2026-10-01", "expected_version": plain["version"], "description": "**now bold**", "description_format": "markdown"})
    assert switched.json()["description_format"] == "markdown"
    assert world.owner.post(f"{world.base}/events", json={"title": "x", "lane_id": world.clock["lanes"][0]["id"], "starts_on": "2026-10-01", "description_format": "html"}).status_code == 422


def test_search_exports_and_the_calendar_file_use_the_text_without_markers(database_url, stack) -> None:
    world = World(stack, database_url, "rich-text-out")
    event(world, "Formatted", "2026-10-02", description="**Deadline** 5 Nov\n\n- see [the plan](https://example.com/plan)", description_format="markdown")
    event(world, "Literal", "2026-10-03", description="**Deadline** stars")
    found = [item["title"] for item in world.owner.get(f"{world.base}/search", params={"q": "deadline 5 nov"}).json()["items"]]
    assert found == ["Formatted"]
    assert [item["title"] for item in world.owner.get(f"{world.base}/search", params={"q": "the plan (https://example.com/plan)"}).json()["items"]] == ["Formatted"]
    rows = sheet_rows(world.owner.post(f"{world.base}/export", json={"format": "xlsx", "scope": "all"}))
    by_title = {row[0]: row[9] for row in rows[1:]}
    assert by_title["Formatted"] == "Deadline 5 Nov\n\n- see the plan (https://example.com/plan)" and by_title["Literal"] == "**Deadline** stars"
    text = world.owner.post(f"{world.base}/export", json={"format": "csv", "scope": "all"}).content.decode("utf-8-sig")
    assert "**Deadline** 5 Nov" not in text and "Deadline 5 Nov" in text
    calendar = world.owner.post(f"{world.base}/export", json={"format": "ics", "scope": "all"}).content.decode().replace("\r\n ", "")
    assert "DESCRIPTION:Deadline 5 Nov\\n\\n- see the plan (https://example.com/plan)" in calendar.replace("\\,", ",")


def test_a_series_keeps_its_format_and_an_occurrence_can_differ(database_url, stack) -> None:
    world = World(stack, database_url, "rich-series")
    created = world.owner.post(f"{world.base}/series", json={"title": "Weekly", "lane_id": world.clock["lanes"][0]["id"], "starts_on": "2026-10-05", "frequency": "WEEKLY", "description": "**agenda**", "description_format": "markdown"})
    assert created.status_code == 201 and created.json()["description_format"] == "markdown"
    items = [item for item in world.owner.get(f"{world.base}/events", params={"window_start": "2026-10-01", "months": 1}).json() if item["occurrence_id"]]
    assert {item["description_format"] for item in items} == {"markdown"}
    one = items[0]
    edited = world.owner.patch(f"{world.base}/occurrences/{one['occurrence_id']}", json={"expected_version": one["version"], "description": "**literal**", "description_format": "plain"})
    assert edited.status_code == 200 and edited.json()["description_format"] == "plain"
    assert world.owner.patch(f"{world.base}/occurrences/{one['occurrence_id']}", json={"expected_version": edited.json()["version"], "description_format": None}).json()["description_format"] == "plain"


def test_history_records_the_format_and_plan_again_and_copies_keep_it(database_url, stack) -> None:
    world = World(stack, database_url, "rich-history")
    created = event(world, "Meeting", "2026-03-10", description="**x**", description_format="markdown")
    body = {"title": "Meeting", "lane_id": world.clock["lanes"][0]["id"], "starts_on": "2026-03-10", "expected_version": created["version"], "description": "**x**", "description_format": "plain"}
    assert world.owner.patch(f"{world.base}/events/{created['id']}", json=body).status_code == 200
    changes = world.owner.get(f"{world.base}/events/{created['id']}/history").json()["items"][0]["changes"]
    assert [(change["field"], change["before"], change["after"]) for change in changes] == [("description_format", "markdown", "plain")]
    again = world.owner.post(f"{world.base}/plan-again", json={"season_start": "2026-01-01", "lane_ids": [world.clock["lanes"][0]["id"]], "include_uncategorized": True, "date_rule": "same_weekday", "dry_run": False})
    assert again.status_code == 200
    copies = [item for item in world.owner.get(f"{world.base}/events", params={"window_start": "2027-01-01", "months": 12}).json() if item["title"] == "Meeting"]
    assert copies and copies[0]["description_format"] == "plain"


def test_old_history_entries_and_the_organization_export_carry_the_format(database_url, stack) -> None:
    from app.revisions import _normalize

    old = {"title": "x", "starts_on": "2026-01-01", "ends_on": None, "lane_id": "l", "category_id": None, "label_ids": [], "description": "d", "external_url": None, "deleted": False, "skipped": False}
    assert _normalize(old)["description_format"] == "plain"
    world = World(stack, database_url, "rich-export")
    event(world, "Formatted", "2026-10-02", description="**bold**", description_format="markdown")
    assert b'"description_format": "markdown"' in world.owner.get(f"{world.org}/export").content or b'"description_format":"markdown"' in world.owner.get(f"{world.org}/export").content
