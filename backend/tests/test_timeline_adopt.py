"""Adopting a Scenario into its parent: fast-forward, refusals, children, roles, chain check, audit, isolation (model-timeline ticket 08, ADR-0050)."""
import json
from contextlib import ExitStack
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from test_invitations import join, login
from test_models_graph import _tenant
from test_timeline_changes import World, add_node, basic, names, update_node
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
    """A Scenario from the Base line's last change with two changes of its own (a node and a connection, then a rename)."""
    scenario = make(world, name, data["second"]["id"])
    node = str(uuid4())
    first = world.ok(scenario["id"], "2026-03-01", "Open office", [add_node(node, world.types["goal"], "Office", x=1, y=2)], note="Because")
    second = world.ok(scenario["id"], "2026-04-01", "Rename app", [update_node(data["ids"]["A"], name="App 2")])
    return scenario, first, second, node


def test_a_fast_forward_appends_the_scenarios_changes_to_its_parent_and_removes_the_scenario(database_url: str, stack: ExitStack) -> None:
    world = World(stack, database_url, "adopt-ok")
    data = basic(world)
    scenario, first, second, node = planned(world, data)
    metrics = f"{world.path}/lines/{scenario['id']}/metrics"
    assert world.owner.post(metrics, json={"key": "own", "name": "Own"}).status_code == 201  # a metric only the Scenario has
    assert world.owner.put(f"{world.path}/lines/{scenario['id']}/positions", json=[{"node_id": node, "x": 77, "y": 88}]).status_code == 200
    before = world.changes()
    result = adopt(world, scenario["id"], expected_version=1)
    assert result.status_code == 200, result.text
    body = result.json()
    assert body["scenario"] is None and body["moved_scenarios"] == 0 and body["line"]["id"] == world.line and body["line"]["change_count"] == len(before) + 2
    changes = world.changes()
    assert [item["title"] for item in changes] == ["Initial situation", "Start", "Hire", "Open office", "Rename app"]
    adopted = changes[-2:]
    assert [item["id"] for item in adopted] == [item["id"] for item in body["adopted_changes"]]
    assert not {item["id"] for item in adopted} & {first["id"], second["id"]}  # new changes with new ids
    assert [item["occurred_on"] for item in adopted] == ["2026-03-01", "2026-04-01"] and adopted[0]["seq"] < adopted[1]["seq"] and adopted[0]["seq"] > before[-1]["seq"]
    detail = world.owner.get(f"{world.path}/changes/{adopted[0]['id']}").json()
    assert detail["note"] == "Because" and [(item["op"], item["element_id"], item["payload"]["name"]) for item in detail["edits"]] == [("add_node", node, "Office")]
    assert world.owner.get(f"{world.path}/changes/{adopted[1]['id']}").json()["edits"][0]["payload"] == {"name": "App 2"}
    state = world.state()
    assert names(state) == {"App 2", "Onboarding", "Ada", "Office"}
    assert {item["node_id"]: (item["x"], item["y"]) for item in state["positions"]}[node] == (77, 88)  # drawn positions of the added nodes follow
    assert "Plan" not in world.lines()
    assert world.owner.get(f"{world.path}/lines/{scenario['id']}/changes").status_code == 404
    assert world.owner.get(metrics).status_code == 404  # its metrics were not adopted; they went with it
    assert world.owner.get(f"{world.path}/lines/{world.line}/metrics").json() == []
    assert count(world, "SELECT count(*) FROM timeline_changes WHERE line_id = :id", id=scenario["id"]) == 0
    assert count(world, "SELECT count(*) FROM node_positions WHERE line_id = :id", id=scenario["id"]) == 0


def test_a_scenario_with_children_stays_without_changes_at_the_last_adopted_change_and_its_children_follow(database_url: str, stack: ExitStack) -> None:
    world = World(stack, database_url, "adopt-children")
    data = basic(world)
    scenario, first, second, node = planned(world, data)
    child = make(world, "Child", first["id"])  # branches from the Scenario's first change
    grandchild_change = world.ok(child["id"], "2026-05-01", "Child step", [add_node(uuid4(), world.types["person"], "Bo")])
    child_before, scenario_before = names(world.state(child["id"])), names(world.state(scenario["id"]))
    assert child_before == {"App", "Onboarding", "Ada", "Office", "Bo"}
    result = adopt(world, scenario["id"])
    assert result.status_code == 200, result.text
    body = result.json()
    adopted = body["adopted_changes"]
    assert body["scenario"]["id"] == scenario["id"] and body["scenario"]["change_count"] == 0 and body["scenario"]["version"] == 2
    assert body["scenario"]["parent_line_id"] == world.line and body["scenario"]["branch_change_id"] == adopted[-1]["id"]  # the last adopted change
    assert body["moved_scenarios"] == 1
    lines = world.lines()
    assert lines["Plan"]["change_count"] == 0 and lines["Child"]["parent_line_id"] == world.line and lines["Child"]["branch_change_id"] == adopted[0]["id"]
    assert world.changes(child["id"])[0]["id"] == grandchild_change["id"]  # its own change is untouched
    assert names(world.state(child["id"])) == child_before and names(world.state(scenario["id"])) == scenario_before  # nothing changes for anyone
    assert names(world.state()) == scenario_before
    assert [item["branches"] for item in world.changes()[-2:]] == [[{"line_id": child["id"], "name": "Child"}], [{"line_id": scenario["id"], "name": "Plan"}]]
    # The emptied Scenario is a normal Scenario again: it takes new changes and can be adopted again only with changes of its own.
    assert adopt(world, scenario["id"]).status_code == 422
    assert world.post(None, scenario["id"], "2026-06-01", "More", [add_node(uuid4(), world.types["person"], "Cy")]).status_code == 201


def test_refusals_are_structured_and_save_nothing(database_url: str, stack: ExitStack) -> None:
    world = World(stack, database_url, "adopt-refuse")
    data = basic(world)
    scenario = make(world, "Early", data["first"]["id"])  # the Base line has moved on since Jan 1
    world.ok(scenario["id"], "2026-03-01", "Own", [add_node(uuid4(), world.types["goal"], "Own goal")])
    before = [item["title"] for item in world.changes()]
    refused = adopt(world, scenario["id"])
    assert refused.status_code == 409
    detail = refused.json()["detail"]
    assert detail["reason"] == "parent_moved_on" and detail["parent_line_id"] == world.line and detail["parent_name"] == "Baseline" and detail["changes_after"] == 1
    assert detail["changes"] == [{"id": data["second"]["id"], "title": "Hire", "occurred_on": "2026-02-01"}]
    assert detail["suggestion"]["action"] == "create_scenario" and detail["suggestion"]["branch_change_id"] == data["second"]["id"]
    assert [item["title"] for item in world.changes()] == before and "Early" in world.lines() and names(world.state()) == {"App", "Onboarding", "Ada"}
    # Dates that precede the parent's last change: only possible when data was changed behind the application's back.
    late = make(world, "Late", data["second"]["id"])
    own = world.ok(late["id"], "2026-03-01", "Dated", [add_node(uuid4(), world.types["goal"], "Late goal")])
    sql(world, "UPDATE timeline_changes SET occurred_on = '2026-01-15' WHERE id = :id", id=own["id"])
    dates = adopt(world, late["id"])
    assert dates.status_code == 422
    detail = dates.json()["detail"]
    assert detail["reason"] == "dates_precede" and detail["parent_last_change_id"] == data["second"]["id"] and detail["parent_last_change_date"] == "2026-02-01"
    assert detail["changes"] == [{"id": own["id"], "title": "Dated", "occurred_on": "2026-01-15"}] and detail["suggestion"] == {"action": "move_changes_after", "date": "2026-02-01"}
    assert [item["title"] for item in world.changes()] == before and "Late" in world.lines()
    # A Scenario without changes, the Base line, an unknown line and a stale version.
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
    missing = uuid4()  # an edit no write would have allowed: it names a node that does not exist
    sql(world, "INSERT INTO change_edits (id, organization_id, change_id, position, op, element_id, payload) VALUES (gen_random_uuid(), :org, :change, 5, 'remove_node', :element, '{}'::jsonb)", org=world.org, change=own["id"], element=missing)
    before = [item["title"] for item in world.changes()]
    refused = adopt(world, scenario["id"])
    assert refused.status_code == 422
    detail = refused.json()["detail"]
    assert detail["reason"] == "chain_broken" and detail["cause"] == "missing_element" and detail["element"] == str(missing) and detail["line"] == world.line
    assert detail["hint"]["change_title"] == "Fine" and detail["hint"]["code"] == "add_element_before"
    assert [item["title"] for item in world.changes()] == before and "Broken" in world.lines() and count(world, "SELECT count(*) FROM timeline_changes WHERE line_id = :id", id=scenario["id"]) == 1


def test_owners_and_admins_adopt_into_the_base_line_and_members_into_scenarios_they_may_write(database_url: str, stack: ExitStack) -> None:
    world = World(stack, database_url, "adopt-roles")
    data = basic(world)
    member = world.member("adopt-roles-m")
    into_base = make(world, "Mine", data["second"]["id"], member)  # a Member made it
    world.ok(into_base["id"], "2026-03-01", "Mine change", [add_node(uuid4(), world.types["goal"], "Mine goal")])
    assert adopt(world, into_base["id"], member).status_code == 403  # the Base line is for Owners and Admins, also for the Scenario's creator
    assert world.changes() and "Mine" in world.lines()
    # A Scenario of a Scenario: a Member adopts it into the parent Scenario.
    parent = make(world, "Parent", data["second"]["id"])
    parent_change = world.ok(parent["id"], "2026-03-01", "Parent change", [add_node(uuid4(), world.types["goal"], "Parent goal")])
    nested = make(world, "Nested", parent_change["id"], member)
    world.ok(nested["id"], "2026-04-01", "Nested change", [add_node(uuid4(), world.types["person"], "Nested person")])
    done = adopt(world, nested["id"], member)
    assert done.status_code == 200 and done.json()["line"]["id"] == parent["id"] and [item["title"] for item in world.changes(parent["id"])] == ["Parent change", "Nested change"]
    assert names(world.state(parent["id"])) == {"App", "Onboarding", "Ada", "Parent goal", "Nested person"} and names(world.state()) == {"App", "Onboarding", "Ada"}
    # An Owner adopts into the Base line (an Admin has the same right).
    admin_app, _ = join(world.application, world.owner, world.org, subject="adopt-roles-a", email="adopt-roles-a@example.com", role="admin")
    admin = world.stack.enter_context(TestClient(admin_app))
    login(admin)
    assert adopt(world, into_base["id"], admin).status_code == 200 and "Mine" not in world.lines()
    assert "Mine change" in [item["title"] for item in world.changes()]
    assert adopt(world, parent["id"]).json()["detail"]["reason"] == "parent_moved_on"  # the Base line moved on with "Mine change"


def test_a_read_only_organization_cannot_adopt(database_url: str, stack: ExitStack) -> None:
    world = World(stack, database_url, "adopt-readonly")
    data = basic(world)
    scenario, *_ = planned(world, data)
    readonly(world)
    assert adopt(world, scenario["id"]).status_code == 403
    assert "Plan" in world.lines() and len(world.changes()) == 3


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
    assert {key: value for key, value in item["change_summary"].items() if key != "source"} == {"model_id": world.model, "line_id": scenario["id"], "parent_line_id": world.line, "change_count": 1, "edit_counts": {"add_node": 2}, "scenario_kept": False, "moved_scenarios": 0}
    assert "ecret" not in json.dumps(items)


def test_another_organization_cannot_adopt(database_url: str, stack: ExitStack) -> None:
    world = World(stack, database_url, "adopt-rls-a")
    data = basic(world)
    scenario, *_ = planned(world, data)
    _, stranger, _, other_base = _tenant(stack, database_url, "adopt-rls-b")
    other_model = stranger.post(f"{other_base}/models", json={"name": "Theirs"}).json()["id"]
    for path in (world.path, f"{other_base}/models/{world.model}", f"{other_base}/models/{other_model}"):
        assert stranger.post(f"{path}/lines/{scenario['id']}/adopt").status_code == 404
    assert "Plan" in world.lines() and len(world.changes()) == 3
