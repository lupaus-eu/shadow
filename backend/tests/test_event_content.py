"""Location and links on Events and Series (Yearclock V2, P11 ticket 01)."""
import csv
import io
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import text

from app.event_content import host_title, parse_stored_links
from app.revisions import _normalize
from test_notifications import World, stack  # noqa: F401 - the fixture

A = {"title": "Agenda", "url": "https://example.com/agenda"}
B = {"title": "Slides", "url": "https://example.com/slides"}


def event(world, title, starts_on, **extra):
    response = world.owner.post(f"{world.base}/events", json={"title": title, "lane_id": world.clock["lanes"][0]["id"], "starts_on": starts_on, **extra})
    assert response.status_code == 201, response.text
    return response.json()


def events(world, start="2026-09-01", months=3):
    return world.owner.get(f"{world.base}/events", params={"window_start": start, "months": months}).json()


def test_location_and_links_are_saved_trimmed_and_replaced_on_update(database_url, stack) -> None:
    world = World(stack, database_url, "content-basic")
    created = event(world, "Workshop", "2026-10-01", location="  Helsinki office, room 4 ", links=[A, B])
    assert created["location"] == "Helsinki office, room 4" and created["links"] == [A, B]
    assert event(world, "Plain", "2026-10-02", location="   ")["location"] is None
    updated = world.owner.patch(f"{world.base}/events/{created['id']}", json={"title": "Workshop", "lane_id": world.clock["lanes"][0]["id"], "starts_on": "2026-10-01", "expected_version": created["version"], "links": [B]})
    assert updated.status_code == 200 and updated.json()["links"] == [B] and updated.json()["location"] is None


def test_the_title_is_required_for_a_link_and_the_limits_hold(database_url, stack) -> None:
    world = World(stack, database_url, "content-limits")
    path = f"{world.base}/events"
    base = {"title": "x", "lane_id": world.clock["lanes"][0]["id"], "starts_on": "2026-10-01"}
    ten = [{"title": f"l{i}", "url": f"https://example.com/{i}"} for i in range(10)]
    assert world.owner.post(path, json={**base, "links": ten}).status_code == 201
    assert world.owner.post(path, json={**base, "links": [*ten, A]}).status_code == 422
    assert world.owner.post(path, json={**base, "links": [{"title": "t" * 101, "url": "https://example.com"}]}).status_code == 422
    assert world.owner.post(path, json={**base, "links": [{"title": "t", "url": "https://"}]}).status_code == 422
    assert world.owner.post(path, json={**base, "location": "x" * 200}).status_code == 201


def test_a_series_passes_its_location_and_links_to_each_occurrence_and_one_can_differ(database_url, stack) -> None:
    world = World(stack, database_url, "content-series")
    created = world.owner.post(f"{world.base}/series", json={"title": "Weekly", "lane_id": world.clock["lanes"][0]["id"], "starts_on": "2026-10-05", "frequency": "WEEKLY", "location": "Room 1", "links": [A]})
    assert created.status_code == 201 and created.json()["location"] == "Room 1" and created.json()["links"] == [A]
    occurrences = [item for item in events(world, "2026-10-01", 1) if item["occurrence_id"]]
    assert len(occurrences) == 4 and {item["location"] for item in occurrences} == {"Room 1"} and all(item["links"] == [A] for item in occurrences)
    second = occurrences[1]
    edited = world.owner.patch(f"{world.base}/occurrences/{second['occurrence_id']}", json={"expected_version": second["version"], "location": "Room 2", "links": [B]})
    assert edited.status_code == 200 and edited.json()["location"] == "Room 2" and edited.json()["links"] == [B]
    after = {item["occurrence_id"]: item for item in events(world, "2026-10-01", 1) if item["occurrence_id"]}
    assert after[second["occurrence_id"]]["location"] == "Room 2" and after[occurrences[2]["occurrence_id"]]["location"] == "Room 1"
    cleared = world.owner.patch(f"{world.base}/occurrences/{second['occurrence_id']}", json={"expected_version": edited.json()["version"], "location": None, "links": None})
    assert cleared.json()["location"] is None and cleared.json()["links"] == []
    third = after[occurrences[2]["occurrence_id"]]
    split = world.owner.post(f"{world.base}/series/{created.json()['id']}/split", json={"from_occurrence_id": third["occurrence_id"], "expected_version": created.json()["version"], "location": "Room 9", "links": [B]})
    assert split.status_code == 200 and split.json()["location"] == "Room 9" and split.json()["links"] == [B]
    final = {item["occurrence_id"]: item for item in events(world, "2026-10-01", 1) if item["occurrence_id"]}
    assert final[occurrences[0]["occurrence_id"]]["location"] == "Room 1" and final[occurrences[2]["occurrence_id"]]["location"] == "Room 9"
    assert world.owner.post(f"{world.base}/series", json={"title": "Bad", "lane_id": world.clock["lanes"][0]["id"], "starts_on": "2026-10-05", "frequency": "WEEKLY", "links": [{"title": "x", "url": "ftp://example.com"}]}).status_code == 422


def test_history_records_the_new_fields_and_old_entries_read_as_link_lists(database_url, stack) -> None:
    world = World(stack, database_url, "content-history")
    created = event(world, "Workshop", "2026-10-01", links=[A])
    updated = world.owner.patch(f"{world.base}/events/{created['id']}", json={"title": "Workshop", "lane_id": world.clock["lanes"][0]["id"], "starts_on": "2026-10-01", "expected_version": created["version"], "location": "Room 4", "links": [A, B]})
    assert updated.status_code == 200
    items = world.owner.get(f"{world.base}/events/{created['id']}/history").json()["items"]
    assert [change["field"] for change in items[0]["changes"]] == ["location", "links"]
    assert items[0]["changes"][0]["after"] == "Room 4" and items[0]["changes"][1].get("after") is None  # long content is only reported as changed
    # An entry written before P11 holds one address in `external_url`; it reads as a link list and can be restored.
    old_snapshot = {"title": "Workshop", "starts_on": "2026-10-01", "ends_on": None, "lane_id": world.clock["lanes"][0]["id"], "category_id": None, "label_ids": [], "description": None, "external_url": "https://old.example.com/page", "deleted": False, "skipped": False}
    assert _normalize(old_snapshot)["links"] == [{"title": "old.example.com", "url": "https://old.example.com/page"}]
    revision_id = uuid4()
    with world.application.state.database_engine.begin() as connection:
        connection.execute(text("INSERT INTO event_revisions (id, organization_id, yearclock_id, event_id, kind, reason, reason_detail, actor_kind, snapshot, changed_fields, created_at) VALUES (:id, :org, :clock, :event, 'updated', 'manual', '{}', 'member', CAST(:snapshot AS jsonb), '{}', now() - interval '1 day')"), {"id": revision_id, "org": world.organization_id, "clock": world.clock["id"], "event": created["id"], "snapshot": __import__("json").dumps(old_snapshot)})
    current = world.owner.get(f"{world.base}/events/{created['id']}/history").json()["items"]
    preview = world.owner.get(f"{world.base}/events/{created['id']}/history/{revision_id}/restore-preview")
    assert preview.status_code == 200, preview.text
    assert "links" in [change["field"] for change in preview.json()["changes"]]
    version = next(item for item in events(world) if item["id"] == created["id"])["version"]
    restored = world.owner.post(f"{world.base}/events/{created['id']}/history/{revision_id}/restore", json={"expected_version": version})
    assert restored.status_code == 200, restored.text
    assert restored.json()["links"] == [{"title": "old.example.com", "url": "https://old.example.com/page"}] and restored.json()["location"] is None
    assert len(current) >= 2


def test_stored_link_values_read_both_shapes_and_the_host_title_matches_the_migration() -> None:
    assert parse_stored_links("https://Example.com:8080/a?b") == [{"title": "Example.com", "url": "https://Example.com:8080/a?b"}]
    assert parse_stored_links(None) == [] and parse_stored_links("") == [] and parse_stored_links([A]) == [A]
    assert host_title("https://docs.example.com/x") == "docs.example.com" and host_title("not a url") == "not a url"


def test_the_migration_gives_an_old_link_a_title_from_its_host_name() -> None:
    import importlib.util
    import os
    from pathlib import Path

    from sqlalchemy import create_engine

    path = Path(__file__).resolve().parents[1] / "migrations" / "versions" / "0047_richer_event_content.py"
    spec = importlib.util.spec_from_file_location("richer_event_content", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = create_engine(os.environ.get("TEST_DATABASE_URL", "postgresql+psycopg://yearclock:yearclock@localhost:8132/yearclock_test"))
    with engine.connect() as connection:
        for url in ("https://Example.com:8080/a?b", "http://docs.example.com/x", "https://a.example.org", "https://" + "h" * 150 + ".example.com/x", "weird"):
            title = connection.execute(text(f"SELECT left({migration.HOST.format(url=':u')}, 100)"), {"u": url}).scalar_one()
            assert title == host_title(url), url


def test_search_finds_a_location_and_a_link_title(database_url, stack) -> None:
    world = World(stack, database_url, "content-search")
    event(world, "Workshop", "2026-10-01", location="Kaisaniemi Garden, room 4")
    event(world, "Review", "2026-10-02", links=[{"title": "Roadmap deck", "url": "https://example.com/deck"}])
    event(world, "Other", "2026-10-03")
    def found(query):
        return [item["title"] for item in world.owner.get(f"{world.base}/search", params={"q": query}).json()["items"]]
    assert found("kaisaniemi") == ["Workshop"] and found("ROADMAP") == ["Review"] and found("nothing like this") == []


def test_plan_again_lane_copy_and_the_organization_export_carry_the_fields(database_url, stack) -> None:
    world = World(stack, database_url, "content-copy")
    event(world, "Annual meeting", "2026-03-10", location="Hall A", links=[A])
    plan = world.owner.post(f"{world.base}/plan-again", json={"season_start": "2026-01-01", "lane_ids": [world.clock["lanes"][0]["id"]], "include_uncategorized": True, "date_rule": "same_weekday", "dry_run": False})
    assert plan.status_code == 200, plan.text
    copies = [item for item in events(world, "2027-01-01", 12) if item["title"] == "Annual meeting"]
    assert len(copies) == 1 and copies[0]["location"] == "Hall A" and copies[0]["links"] == [A]
    document = world.owner.get(f"{world.org}/export").content
    assert b'"location": "Hall A"' in document or b'"location":"Hall A"' in document
    assert b'"schema": "yearclock-export/2"' in document or b'"schema":"yearclock-export/2"' in document


def test_the_summary_shows_the_location(database_url, stack) -> None:
    from test_summary import MONDAY, choose, mails, run

    world = World(stack, database_url, "content-summary")
    event(world, "Workshop", "2026-10-06", location="Hall A")
    choose(world.owner, world, "daily")
    assert run(world, MONDAY) == 1
    assert "Workshop (" in mails(world)[0]["text"] and "— Hall A" in mails(world)[0]["text"]
