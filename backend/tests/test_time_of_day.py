"""Time of day (Yearclock V2, P11 ticket 03)."""
import csv
import io
from datetime import UTC, datetime, time

import pytest

from app.exchange import read_time
from app.ical import calendar_text
from test_export import sheet_rows, unfold
from test_notifications import World, stack  # noqa: F401 - the fixture


def event(world, title, starts_on, **extra):
    response = world.owner.post(f"{world.base}/events", json={"title": title, "lane_id": world.clock["lanes"][0]["id"], "starts_on": starts_on, **extra})
    assert response.status_code == 201, response.text
    return response.json()


def events(world, start="2026-09-01", months=3):
    return world.owner.get(f"{world.base}/events", params={"window_start": start, "months": months}).json()


def test_times_are_saved_to_the_minute_and_validated(database_url, stack) -> None:
    world = World(stack, database_url, "time-basic")
    created = event(world, "Board", "2026-10-01", starts_at="14:00", ends_at="16:30:45")
    assert created["starts_at"] == "14:00" and created["ends_at"] == "16:30"
    assert event(world, "Open", "2026-10-02")["starts_at"] is None
    assert event(world, "Start only", "2026-10-03", starts_at="09:15")["ends_at"] is None
    base = {"title": "x", "lane_id": world.clock["lanes"][0]["id"], "starts_on": "2026-10-01"}
    path = f"{world.base}/events"
    assert world.owner.post(path, json={**base, "ends_at": "10:00"}).status_code == 422  # an end time needs a start time
    assert world.owner.post(path, json={**base, "starts_at": "10:00", "ends_at": "10:00"}).status_code == 422
    assert world.owner.post(path, json={**base, "starts_at": "10:00", "ends_at": "09:00"}).status_code == 422
    assert world.owner.post(path, json={**base, "starts_at": "25:00"}).status_code == 422
    # A longer Event: the start time is for the first day and the end time for the last, so the end may be earlier.
    assert world.owner.post(path, json={**base, "ends_on": "2026-10-03", "starts_at": "14:00", "ends_at": "10:00"}).status_code == 201
    update = world.owner.patch(f"{world.base}/events/{created['id']}", json={**base, "title": "Board", "expected_version": created["version"], "starts_at": "15:00"})
    assert update.status_code == 200 and update.json()["starts_at"] == "15:00" and update.json()["ends_at"] is None


def test_same_day_events_list_all_day_first_then_by_start_time(database_url, stack) -> None:
    world = World(stack, database_url, "time-order")
    event(world, "Late", "2026-10-05", starts_at="16:00")
    event(world, "All day", "2026-10-05")
    event(world, "Early", "2026-10-05", starts_at="08:30")
    event(world, "Next day", "2026-10-06")
    assert [item["title"] for item in events(world, "2026-10-01", 1)] == ["All day", "Early", "Late", "Next day"]


def test_a_series_keeps_its_time_for_every_occurrence_and_one_can_move(database_url, stack) -> None:
    world = World(stack, database_url, "time-series")
    created = world.owner.post(f"{world.base}/series", json={"title": "Weekly", "lane_id": world.clock["lanes"][0]["id"], "starts_on": "2026-10-05", "frequency": "WEEKLY", "starts_at": "14:00", "ends_at": "15:00"})
    assert created.status_code == 201 and created.json()["starts_at"] == "14:00" and created.json()["ends_at"] == "15:00"
    occurrences = [item for item in events(world, "2026-10-01", 1) if item["occurrence_id"]]
    assert {(item["starts_at"], item["ends_at"]) for item in occurrences} == {("14:00", "15:00")}
    second = occurrences[1]
    moved = world.owner.patch(f"{world.base}/occurrences/{second['occurrence_id']}", json={"expected_version": second["version"], "starts_at": "15:00", "ends_at": "16:00"})
    assert moved.status_code == 200 and (moved.json()["starts_at"], moved.json()["ends_at"]) == ("15:00", "16:00")
    # Only the end changes: it is checked against the Series' start time.
    third = occurrences[2]
    assert world.owner.patch(f"{world.base}/occurrences/{third['occurrence_id']}", json={"expected_version": third["version"], "ends_at": "13:00"}).status_code == 422
    after = {item["occurrence_id"]: item for item in events(world, "2026-10-01", 1) if item["occurrence_id"]}
    assert after[third["occurrence_id"]]["ends_at"] == "15:00" and after[second["occurrence_id"]]["starts_at"] == "15:00"
    cleared = world.owner.patch(f"{world.base}/occurrences/{occurrences[0]['occurrence_id']}", json={"expected_version": occurrences[0]["version"], "starts_at": None, "ends_at": None})
    assert cleared.json()["starts_at"] is None and cleared.json()["ends_at"] is None
    split = world.owner.post(f"{world.base}/series/{created.json()['id']}/split", json={"from_occurrence_id": third["occurrence_id"], "expected_version": created.json()["version"], "starts_at": "09:00", "ends_at": "10:00"})
    assert split.status_code == 200 and split.json()["starts_at"] == "09:00"
    assert world.owner.post(f"{world.base}/series/{split.json()['id']}/split", json={"from_occurrence_id": third["occurrence_id"], "expected_version": split.json()["version"], "ends_at": "08:00"}).status_code == 422
    final = {item["occurrence_id"]: item for item in events(world, "2026-10-01", 1) if item["occurrence_id"]}
    assert final[third["occurrence_id"]]["starts_at"] == "09:00" and final[occurrences[3]["occurrence_id"]]["ends_at"] == "10:00"
    assert world.owner.post(f"{world.base}/series", json={"title": "Bad", "lane_id": world.clock["lanes"][0]["id"], "starts_on": "2026-10-05", "frequency": "WEEKLY", "starts_at": "10:00", "ends_at": "09:00"}).status_code == 422


def test_history_records_the_time_and_plan_again_and_lane_copy_keep_it(database_url, stack) -> None:
    world = World(stack, database_url, "time-history")
    created = event(world, "Meeting", "2026-03-10", starts_at="14:00", ends_at="15:00")
    body = {"title": "Meeting", "lane_id": world.clock["lanes"][0]["id"], "starts_on": "2026-03-10", "expected_version": created["version"], "starts_at": "15:00", "ends_at": "16:00"}
    assert world.owner.patch(f"{world.base}/events/{created['id']}", json=body).status_code == 200
    changes = world.owner.get(f"{world.base}/events/{created['id']}/history").json()["items"][0]["changes"]
    assert [(change["field"], change["before"], change["after"]) for change in changes] == [("starts_at", "14:00", "15:00"), ("ends_at", "15:00", "16:00")]
    first = world.owner.get(f"{world.base}/events/{created['id']}/history").json()["items"][-1]
    version = events(world, "2026-01-01", 12)[0]["version"]
    restored = world.owner.post(f"{world.base}/events/{created['id']}/history/{first['id']}/restore", json={"expected_version": version})
    assert restored.status_code == 200 and (restored.json()["starts_at"], restored.json()["ends_at"]) == ("14:00", "15:00")
    assert world.owner.post(f"{world.base}/plan-again", json={"season_start": "2026-01-01", "lane_ids": [world.clock["lanes"][0]["id"]], "include_uncategorized": True, "date_rule": "same_weekday", "dry_run": False}).status_code == 200
    copy = [item for item in events(world, "2027-01-01", 12) if item["title"] == "Meeting"]
    assert copy and (copy[0]["starts_at"], copy[0]["ends_at"]) == ("14:00", "15:00")
    other = world.owner.post(f"{world.org}/yearclocks", json={"name": "Other"}).json()
    lane = world.owner.post(f"{world.org}/yearclocks/{other['id']}/lanes/copy", json={"source_lane_id": world.clock["lanes"][0]["id"], "include_events": True})
    assert lane.status_code in {200, 201}, lane.text
    copied = [item for item in world.owner.get(f"{world.org}/yearclocks/{other['id']}/events", params={"window_start": "2026-01-01", "months": 24}).json() if item["title"] == "Meeting"]
    assert copied and copied[0]["starts_at"] == "14:00"


def test_exports_carry_the_times_and_the_import_reads_them_back(database_url, stack) -> None:
    world = World(stack, database_url, "time-exchange")
    event(world, "Board", "2026-10-01", starts_at="14:00", ends_at="16:30")
    event(world, "Open", "2026-10-01")
    rows = sheet_rows(world.owner.post(f"{world.base}/export", json={"format": "xlsx", "scope": "all"}))
    assert [(row[0], row[3], row[4]) for row in rows[1:]] == [("Open", None, None), ("Board", "14:00", "16:30")]  # all-day first
    fi = list(csv.reader(io.StringIO(world.owner.post(f"{world.base}/export", json={"format": "csv", "scope": "all", "locale": "fi"}).content.decode("utf-8-sig")), delimiter=";"))
    assert fi[0][3:5] == ["Alkamisaika", "Päättymisaika"] and fi[2][3:5] == ["14:00", "16:30"]
    target = world.owner.post(f"{world.org}/yearclocks", json={"name": "Copy"}).json()
    lane = target["lanes"][0]["name"]
    exported = world.owner.post(f"{world.base}/export", json={"format": "xlsx", "scope": "all"}).content
    saved = world.owner.post(f"{world.org}/yearclocks/{target['id']}/import", params={"format": "xlsx", "dry_run": "false"}, content=exported)
    assert saved.status_code == 200, saved.text
    copied = {item["title"]: item for item in world.owner.get(f"{world.org}/yearclocks/{target['id']}/events", params={"window_start": "2026-01-01", "months": 24}).json()}
    assert (copied["Board"]["starts_at"], copied["Board"]["ends_at"], copied["Open"]["starts_at"]) == ("14:00", "16:30", None)


def test_the_time_cell_reads_text_time_cells_and_day_fractions() -> None:
    assert read_time("14:00") == (time(14, 0), False) and read_time("9.30") == (time(9, 30), False) and read_time("08:15:59") == (time(8, 15), False)
    assert read_time(time(7, 5, 30)) == (time(7, 5), False) and read_time(datetime(1899, 12, 30, 18, 45)) == (time(18, 45), False)
    assert read_time(0.5) == (time(12, 0), False) and read_time("") == (None, False) and read_time(None) == (None, False)
    for bad in ("25:00", "10:60", "noon", "1400", 1.5, True):
        assert read_time(bad)[1] is True, bad


def test_import_problems_with_times_are_reported_per_row(database_url, stack) -> None:
    from test_import import World as ImportWorld, csv_text

    world = ImportWorld(stack, database_url, "time-import-errors")
    content = csv_text(
        "Title,Starts,Start time,End time,Lane",
        "Bad time,2026-10-01,noon,,General",
        "End alone,2026-10-01,,10:00,General",
        "Backwards,2026-10-01,10:00,09:00,General",
        "Fine,2026-10-01,10:00,11:00,General",
        "Finnish,2026-10-02,9.30,,General",
    )
    result = world.upload(content).json()
    assert {(issue["row"], issue["column"], issue["reason"]) for issue in result["errors"]} == {(2, "start_time", "invalid_time"), (3, "end_time", "end_time_without_start"), (4, "end_time", "end_time_before_start")}
    assert [row["title"] for row in result["create"]] == ["Fine", "Finnish"]
    # The same title and date with another start time is a different Event, not a duplicate.
    ok = csv_text("Title,Starts,Start time,Lane", "Twice,2026-10-05,09:00,General", "Twice,2026-10-05,14:00,General")
    assert world.upload(ok, dry_run=False).status_code == 200
    assert len([item for item in world.events() if item["title"] == "Twice"]) == 2
    assert world.upload(ok).json()["skipped"] == [{"row": 2, "title": "Twice", "reason": "duplicate"}, {"row": 3, "title": "Twice", "reason": "duplicate"}]


def ics(rows, zone="Europe/Helsinki"):
    return unfold(calendar_text("Plan", rows, stamp=datetime(2026, 1, 1, tzinfo=UTC), time_zone=zone).replace("\r\n", "\r\n"))


def row(**extra):
    base = {"uid": "u@yearclock", "title": "T", "starts_on": datetime(2026, 7, 1).date(), "ends_on": None, "description": "", "location": "", "links": (), "categories": [], "sequence": 0, "starts_at": None, "ends_at": None}
    return {**base, **extra}


def test_the_calendar_file_writes_timed_events_as_utc_instants_across_daylight_saving() -> None:
    summer = ics([row(starts_at=time(14, 0), ends_at=time(16, 0))])
    assert "DTSTART:20260701T110000Z" in summer and "DTEND:20260701T130000Z" in summer  # Helsinki is UTC+3 in July
    winter = ics([row(starts_on=datetime(2026, 12, 1).date(), starts_at=time(14, 0), ends_at=time(16, 0))])
    assert "DTSTART:20261201T120000Z" in winter and "DTEND:20261201T140000Z" in winter  # UTC+2 in December
    change = ics([row(starts_on=datetime(2026, 3, 29).date(), starts_at=time(10, 0))])  # the clocks went forward at 03:00 that day
    assert "DTSTART:20260329T070000Z" in change
    other_zone = ics([row(starts_at=time(9, 0))], "America/New_York")
    assert "DTSTART:20260701T130000Z" in other_zone


def test_the_calendar_file_keeps_untimed_events_all_day_and_never_invents_a_duration() -> None:
    lines = ics([row(), row(uid="b@yearclock", starts_at=time(9, 30)), row(uid="c@yearclock", starts_on=datetime(2026, 7, 1).date(), ends_on=datetime(2026, 7, 3).date(), starts_at=time(9, 30)), row(uid="d@yearclock", ends_on=datetime(2026, 7, 3).date(), starts_at=time(9, 30), ends_at=time(17, 0))])
    assert "DTSTART;VALUE=DATE:20260701" in lines and "DTEND;VALUE=DATE:20260702" in lines
    assert "DTSTART:20260701T063000Z" in lines and lines.count("DTEND:20260701T063000Z") == 1  # a start time alone is a point in time
    assert "DTEND:20260703T210000Z" in lines  # runs through the last day: midnight after it, Helsinki time
    assert "DTEND:20260703T140000Z" in lines  # a longer Event with an end time ends on the last day at that time


def test_the_summary_shows_the_times(database_url, stack) -> None:
    from test_summary import MONDAY, choose, mails, run

    world = World(stack, database_url, "time-summary")
    event(world, "Workshop", "2026-10-06", starts_at="14:00", ends_at="16:00", location="Hall A")
    event(world, "Open day", "2026-10-06")
    choose(world.owner, world, "daily")
    assert run(world, MONDAY) == 1
    body = mails(world)[0]["text"]
    assert "Tue 6 Oct: Open day" in body and "Tue 6 Oct 14:00–16:00: Workshop" in body and body.index("Open day") < body.index("Workshop")


def test_the_organization_export_has_the_times(database_url, stack) -> None:
    world = World(stack, database_url, "time-orgexport")
    event(world, "Board", "2026-10-01", starts_at="14:00", ends_at="16:30")
    content = world.owner.get(f"{world.org}/export").content
    assert b'"starts_at": "14:00"' in content or b'"starts_at":"14:00"' in content
