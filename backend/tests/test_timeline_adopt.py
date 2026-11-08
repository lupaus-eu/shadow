"""Adopting a Scenario into its parent: fast-forward, refusals, children, roles, chain check, audit, isolation (model-timeline ticket 08, ADR-0050)."""
import json
from contextlib import ExitStack
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from test_invitations import join, login
from test_models_graph import _tenant
from test_timeline_events import World, add_node, basic, names, update_node
from test_timeline_lines import count, make, readonly


@pytest.fixture
def stack():
    with ExitStack() as clients:
        yield clients


def adopt(world: World, line: str, client=None, **body):
    return (client or world.owner).post(f"{world.path}/lines/{line}/adopt", json=body or None)


def sql(world: World, statement: str, **params) -> None:
    engine = create_engine(world.database_url)
    with engine.begin() as connection:
        connection.execute(text(statement), params)
    engine.dispose()


def planned(world: World, data: dict, name: str = "Plan") -> tuple[dict, dict, dict, str]:
    """A Scenario from the Base line's last event with two events of its own (a node and a connection, then a rename)."""
    scenario = make(world, name, data["second"]["id"])
    node = str(uuid4())
    first = world.ok(scenario["id"], "2026-03-01", "Open office", [add_node(node, world.types["goal"], "Office", x=1, y=2)], note="Because")
    second = world.ok(scenario["id"], "2026-04-01", "Rename app", [update_node(data["ids"]["A"], name="App 2")])
    return scenario, first, second, node


def test_a_fast_forward_appends_the_scenarios_events_to_its_parent_and_removes_the_scenario(database_url: str, stack: ExitStack) -> None:
    world = World(stack, database_url, "adopt-ok")
    data = basic(world)
    scenario, first, second, node = planned(world, data)
    metrics = f"{world.path}/lines/{scenario['id']}/metrics"
    assert world.owner.post(metrics, json={"key": "own", "name": "Own"}).status_code == 201  # a metric only the Scenario has
    assert world.owner.put(f"{world.path}/lines/{scenario['id']}/positions", json=[{"node_id": node, "x": 77, "y": 88}]).status_code == 200
    before = world.events()
    result = adopt(world, scenario["id"], expected_version=1)
    assert result.status_code == 200, result.text
    body = result.json()
    assert body["scenario"] is None and body["moved_scenarios"] == 0 and body["line"]["id"] == world.line and body["line"]["event_count"] == len(before) + 2
    events = world.events()
    assert [item["title"] for item in events] == ["Initial situation", "Start", "Hire", "Open office", "Rename app"]
    adopted = events[-2:]
    assert [item["id"] for item in adopted] == [item["id"] for item in body["adopted_events"]]
    assert not {item["id"] for item in adopted} & {first["id"], second["id"]}  # new events with new ids
    assert [item["occurred_on"] for item in adopted] == ["2026-03-01", "2026-04-01"] and adopted[0]["seq"] < adopted[1]["seq"] and adopted[0]["seq"] > before[-1]["seq"]
    detail = world.owner.get(f"{world.path}/events/{adopted[0]['id']}").json()
    assert detail["note"] == "Because" and [(item["op"], item["element_id"], item["payload"]["name"]) for item in detail["changes"]] == [("add_node", node, "Office")]
    assert world.owner.get(f"{world.path}/events/{adopted[1]['id']}").json()["changes"][0]["payload"] == {"name": "App 2"}
    state = world.state()
    assert names(state) == {"App 2", "Onboarding", "Ada", "Office"}
    assert {item["node_id"]: (item["x"], item["y"]) for item in state["positions"]}[node] == (77, 88)  # drawn positions of the added nodes follow
    assert "Plan" not in world.lines()
    assert world.owner.get(f"{world.path}/lines/{scenario['id']}/events").status_code == 404
    assert world.owner.get(metrics).status_code == 404  # its metrics were not adopted; they went with it
    assert world.owner.get(f"{world.path}/lines/{world.line}/metrics").json() == []
    assert count(world, "SELECT count(*) FROM timeline_events WHERE line_id = :id", id=scenario["id"]) == 0
    assert count(world, "SELECT count(*) FROM node_positions WHERE line_id = :id", id=scenario["id"]) == 0


def test_a_scenario_with_children_stays_without_events_at_the_last_adopted_event_and_its_children_follow(database_url: str, stack: ExitStack) -> None:
    world = World(stack, database_url, "adopt-children")
    data = basic(world)
    scenario, first, second, node = planned(world, data)
    child = make(world, "Child", first["id"])  # branches from the Scenario's first event
    grandchild_event = world.ok(child["id"], "2026-05-01", "Child step", [add_node(uuid4(), world.types["person"], "Bo")])
    child_before, scenario_before = names(world.state(child["id"])), names(world.state(scenario["id"]))
    assert child_before == {"App", "Onboarding", "Ada", "Office", "Bo"}
    result = adopt(world, scenario["id"])
    assert result.status_code == 200, result.text
    body = result.json()
    adopted = body["adopted_events"]
    assert body["scenario"]["id"] == scenario["id"] and body["scenario"]["event_count"] == 0 and body["scenario"]["version"] == 2
    assert body["scenario"]["parent_line_id"] == world.line and body["scenario"]["branch_event_id"] == adopted[-1]["id"]  # the last adopted event
    assert body["moved_scenarios"] == 1
    lines = world.lines()
    assert lines["Plan"]["event_count"] == 0 and lines["Child"]["parent_line_id"] == world.line and lines["Child"]["branch_event_id"] == adopted[0]["id"]
    assert world.events(child["id"])[0]["id"] == grandchild_event["id"]  # its own event is untouched
    assert names(world.state(child["id"])) == child_before and names(world.state(scenario["id"])) == scenario_before  # nothing changes for anyone
    assert names(world.state()) == scenario_before
    assert [item["branches"] for item in world.events()[-2:]] == [[{"line_id": child["id"], "name": "Child"}], [{"line_id": scenario["id"], "name": "Plan"}]]
    # The emptied Scenario is a normal Scenario again: it takes new events and can be adopted again only with events of its own.
    assert adopt(world, scenario["id"]).status_code == 422
    assert world.post(None, scenario["id"], "2026-06-01", "More", [add_node(uuid4(), world.types["person"], "Cy")]).status_code == 201


def test_refusals_are_structured_and_save_nothing(database_url: str, stack: ExitStack) -> None:
    world = World(stack, database_url, "adopt-refuse")
    data = basic(world)
    scenario = make(world, "Early", data["first"]["id"])  # the Base line has moved on since Jan 1
    world.ok(scenario["id"], "2026-03-01", "Own", [add_node(uuid4(), world.types["goal"], "Own goal")])
    before = [item["title"] for item in world.events()]
    refused = adopt(world, scenario["id"])
    assert refused.status_code == 409
    detail = refused.json()["detail"]
    assert detail["reason"] == "parent_moved_on" and detail["parent_line_id"] == world.line and detail["parent_name"] == "Baseline" and detail["events_after"] == 1
    assert detail["events"] == [{"id": data["second"]["id"], "title": "Hire", "occurred_on": "2026-02-01"}]
    assert detail["suggestion"]["action"] == "create_scenario" and detail["suggestion"]["branch_event_id"] == data["second"]["id"]
    assert [item["title"] for item in world.events()] == before and "Early" in world.lines() and names(world.state()) == {"App", "Onboarding", "Ada"}
    # Dates that precede the parent's last event: only possible when data was changed behind the application's back.
    late = make(world, "Late", data["second"]["id"])
    own = world.ok(late["id"], "2026-03-01", "Dated", [add_node(uuid4(), world.types["goal"], "Late goal")])
    sql(world, "UPDATE timeline_events SET occurred_on = '2026-01-15' WHERE id = :id", id=own["id"])
    dates = adopt(world, late["id"])
    assert dates.status_code == 422
    detail = dates.json()["detail"]
    assert detail["reason"] == "dates_precede" and detail["parent_last_event_id"] == data["second"]["id"] and detail["parent_last_event_date"] == "2026-02-01"
    assert detail["events"] == [{"id": own["id"], "title": "Dated", "occurred_on": "2026-01-15"}] and detail["suggestion"] == {"action": "move_events_after", "date": "2026-02-01"}
    assert [item["title"] for item in world.events()] == before and "Late" in world.lines()
    # A Scenario without events, the Base line, an unknown line and a stale version.
    empty = make(world, "Empty", data["second"]["id"])
    assert adopt(world, empty["id"]).json()["detail"] == {"reason": "nothing_to_adopt"} and adopt(world, empty["id"]).status_code == 422
    assert adopt(world, world.line).json()["detail"] == {"reason": "base_line"}
    assert adopt(world, str(uuid4())).status_code == 404
    stale = adopt(world, late["id"], expected_version=5)
    assert stale.status_code == 409 and stale.json()["detail"] == {"latest_version": 1}


def test_the_chain_is_checked_before_saving(database_url: str, stack: ExitStack) -> None:
    world = World(stack, database_url, "adopt-chain")
    data = basic(world)
    scenario = make(world, "Broken", data["second"]["id"])
    own = world.ok(scenario["id"], "2026-03-01", "Fine", [add_node(uuid4(), world.types["goal"], "Goal")])
    missing = uuid4()  # a change no write would have allowed: it names a node that does not exist
    sql(world, "INSERT INTO event_changes (id, organization_id, event_id, position, op, element_id, payload) VALUES (gen_random_uuid(), :org, :event, 5, 'remove_node', :element, '{}'::jsonb)", org=world.org, event=own["id"], element=missing)
    before = [item["title"] for item in world.events()]
    refused = adopt(world, scenario["id"])
    assert refused.status_code == 422
    detail = refused.json()["detail"]
    assert detail["reason"] == "chain_broken" and detail["cause"] == "missing_element" and detail["element"] == str(missing) and detail["line"] == world.line
    assert detail["hint"]["event_title"] == "Fine" and detail["hint"]["code"] == "add_element_before"
    assert [item["title"] for item in world.events()] == before and "Broken" in world.lines() and count(world, "SELECT count(*) FROM timeline_events WHERE line_id = :id", id=scenario["id"]) == 1


def test_owners_and_admins_adopt_into_the_base_line_and_members_into_scenarios_they_may_write(database_url: str, stack: ExitStack) -> None:
    world = World(stack, database_url, "adopt-roles")
    data = basic(world)
    member = world.member("adopt-roles-m")
    into_base = make(world, "Mine", data["second"]["id"], member)  # a Member made it
    world.ok(into_base["id"], "2026-03-01", "Mine event", [add_node(uuid4(), world.types["goal"], "Mine goal")])
    assert adopt(world, into_base["id"], member).status_code == 403  # the Base line is for Owners and Admins, also for the Scenario's creator
    assert world.events() and "Mine" in world.lines()
    # A Scenario of a Scenario: a Member adopts it into the parent Scenario.
    parent = make(world, "Parent", data["second"]["id"])
    parent_event = world.ok(parent["id"], "2026-03-01", "Parent event", [add_node(uuid4(), world.types["goal"], "Parent goal")])
    nested = make(world, "Nested", parent_event["id"], member)
    world.ok(nested["id"], "2026-04-01", "Nested event", [add_node(uuid4(), world.types["person"], "Nested person")])
    done = adopt(world, nested["id"], member)
    assert done.status_code == 200 and done.json()["line"]["id"] == parent["id"] and [item["title"] for item in world.events(parent["id"])] == ["Parent event", "Nested event"]
    assert names(world.state(parent["id"])) == {"App", "Onboarding", "Ada", "Parent goal", "Nested person"} and names(world.state()) == {"App", "Onboarding", "Ada"}
    # An Owner adopts into the Base line (an Admin has the same right).
    admin_app, _ = join(world.application, world.owner, world.org, subject="adopt-roles-a", email="adopt-roles-a@example.com", role="admin")
    admin = world.stack.enter_context(TestClient(admin_app))
    login(admin)
    assert adopt(world, into_base["id"], admin).status_code == 200 and "Mine" not in world.lines()
    assert "Mine event" in [item["title"] for item in world.events()]
    assert adopt(world, parent["id"]).json()["detail"]["reason"] == "parent_moved_on"  # the Base line moved on with "Mine event"


def test_a_read_only_organization_cannot_adopt(database_url: str, stack: ExitStack) -> None:
    world = World(stack, database_url, "adopt-readonly")
    data = basic(world)
    scenario, *_ = planned(world, data)
    readonly(world)
    assert adopt(world, scenario["id"]).status_code == 403
    assert "Plan" in world.lines() and len(world.events()) == 3


def test_the_audit_entry_carries_counts_and_ids_but_no_names(database_url: str, stack: ExitStack) -> None:
    world = World(stack, database_url, "adopt-audit")
    data = basic(world)
    scenario = make(world, "Secret scenario", data["second"]["id"], description="Secret description")
    world.ok(scenario["id"], "2026-03-01", "Secret title", [add_node(uuid4(), world.types["goal"], "Secret node"), add_node(uuid4(), world.types["person"], "Secret person")], note="Secret note")
    result = adopt(world, scenario["id"])
    assert result.status_code == 200
    items = [item for item in world.audit() if item["action"] == "line.adopted"]
    assert len(items) == 1
    item = items[0]
    assert item["target_type"] == "line" and item["target_id"] == scenario["id"]
    assert {key: value for key, value in item["change_summary"].items() if key != "source"} == {"model_id": world.model, "line_id": scenario["id"], "parent_line_id": world.line, "event_count": 1, "change_counts": {"add_node": 2}, "scenario_kept": False, "moved_scenarios": 0}
    assert "ecret" not in json.dumps(items)


def test_another_organization_cannot_adopt(database_url: str, stack: ExitStack) -> None:
    world = World(stack, database_url, "adopt-rls-a")
    data = basic(world)
    scenario, *_ = planned(world, data)
    _, stranger, _, other_base = _tenant(stack, database_url, "adopt-rls-b")
    other_model = stranger.post(f"{other_base}/models", json={"name": "Theirs"}).json()["id"]
    for path in (world.path, f"{other_base}/models/{world.model}", f"{other_base}/models/{other_model}"):
        assert stranger.post(f"{path}/lines/{scenario['id']}/adopt").status_code == 404
    assert "Plan" in world.lines() and len(world.events()) == 3
