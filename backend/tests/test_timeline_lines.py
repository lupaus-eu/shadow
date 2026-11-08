"""Scenarios and positions: branching, inheritance, rename, delete, metrics copy, limit, roles, audit, isolation (model-timeline ticket 06)."""
import json
from contextlib import ExitStack
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, text

from app.database import RequestContext, transaction_session
from test_timeline_changes import World, add_node, basic, names
from test_models_graph import _tenant


@pytest.fixture
def stack():
    with ExitStack() as clients:
        yield clients


def create(world: World, name: str, branch_change: str, client=None, **extra):
    return (client or world.owner).post(f"{world.path}/lines", json={"name": name, "branch_change_id": branch_change, **extra})


def make(world: World, name: str, branch_change: str, client=None, **extra) -> dict:
    response = create(world, name, branch_change, client, **extra)
    assert response.status_code == 201, response.text
    return response.json()


def count(world: World, sql: str, **params) -> int:
    with transaction_session(world.factory, RequestContext(organization_id=UUID(world.org))) as session:
        return session.execute(text(sql), params).scalar_one()


def readonly(world: World) -> None:
    engine = create_engine(world.database_url)
    with engine.begin() as connection:
        connection.execute(text("UPDATE organizations SET subscription_access_state = 'canceled' WHERE id = :id"), {"id": world.org})
    engine.dispose()


def test_a_scenario_branches_from_a_past_change_and_from_another_scenario_to_any_depth(database_url: str, stack: ExitStack) -> None:
    world = World(stack, database_url, "tln-depth")
    data = basic(world)
    first = make(world, "From Start", data["first"]["id"])
    assert first["kind"] == "scenario" and first["parent_line_id"] == world.line and first["branch_change_id"] == data["first"]["id"] and first["version"] == 1
    assert first["created_by_user_account_id"] and first["start_changed_at"] is None and first["change_count"] == 0
    assert names(world.state(first["id"])) == {"App", "Onboarding"}  # Ada was hired after the branch point
    own = world.ok(first["id"], "2026-03-01", "Own one", [add_node(str(uuid4()), world.types["goal"], "Goal one")])
    second = make(world, "Second", own["id"])
    assert second["parent_line_id"] == first["id"]
    own2 = world.ok(second["id"], "2026-04-01", "Own two", [add_node(str(uuid4()), world.types["goal"], "Goal two")])
    third = make(world, "Third", own2["id"])
    assert third["parent_line_id"] == second["id"]
    assert names(world.state(third["id"])) == {"App", "Onboarding", "Goal one", "Goal two"}
    assert names(world.state(first["id"])) == {"App", "Onboarding", "Goal one"} and names(world.state()) == {"App", "Onboarding", "Ada"}
    assert [item["name"] for item in world.owner.get(f"{world.path}/lines").json()] == ["Baseline", "From Start", "Second", "Third"]
    # a Scenario may branch from the initial change of the Base line, and from the very last change
    assert make(world, "From nothing", world.initial)["branch_change_id"] == world.initial
    assert names(world.state(world.lines()["From nothing"]["id"])) == set()
    assert world.owner.get(f"{world.path}/lines/{third['id']}/changes").json() == []


def test_the_branch_change_must_exist_in_this_model_and_the_name_must_be_valid_and_unique(database_url: str, stack: ExitStack) -> None:
    world = World(stack, database_url, "tln-invalid")
    data = basic(world)
    assert create(world, "Ghost", str(uuid4())).status_code == 404
    other = world.owner.post(f"{world.base}/models", json={"name": "Other"}).json()["id"]
    other_line = world.owner.get(f"{world.base}/models/{other}/lines").json()[0]["id"]
    other_change = world.owner.get(f"{world.base}/models/{other}/lines/{other_line}/changes").json()[0]["id"]
    assert create(world, "Foreign", other_change).status_code == 404  # a change of another Model of the same Organization
    assert create(world, "   ", data["first"]["id"]).status_code == 422
    assert world.owner.post(f"{world.path}/lines", json={"name": "No change"}).status_code == 422
    make(world, "  Plan   B ", data["first"]["id"])
    assert world.lines()["Plan B"]["description"] is None
    assert create(world, "plan b", data["second"]["id"]).status_code == 409 and create(world, "plan b", data["second"]["id"]).json()["detail"] == {"reason": "duplicate_name"}
    assert create(world, "baseline", data["second"]["id"]).status_code == 409  # the Base line's name counts too
    assert create(world, "x" * 121, data["first"]["id"]).status_code == 422


def test_parent_changes_after_the_branch_do_not_show_and_earlier_inserted_changes_do_and_mark_the_start(database_url: str, stack: ExitStack) -> None:
    world = World(stack, database_url, "tln-start")
    data = basic(world)
    scenario = make(world, "From Hire", data["second"]["id"], description="What if")
    assert scenario["description"] == "What if"
    member = world.member("tln-start-m")
    deeper = make(world, "Deeper", world.ok(scenario["id"], "2026-03-01", "Mine", [])["id"], member)
    world.ok(world.line, "2026-03-01", "Later", [add_node(str(uuid4()), world.types["goal"], "After branch")])  # after the branch point: not part of the Scenario
    assert "After branch" in names(world.state()) and "After branch" not in names(world.state(scenario["id"]))
    assert all(item["start_changed_at"] is None for item in world.lines().values())
    inserted = world.ok(world.line, "2026-01-15", "Inserted", [add_node(str(uuid4()), world.types["goal"], "Before branch")])
    assert "Before branch" in names(world.state(scenario["id"])) and "Before branch" in names(world.state(deeper["id"]))
    lines = world.lines()
    assert lines["From Hire"]["start_changed_at"] is not None and lines["Deeper"]["start_changed_at"] is not None and lines["Baseline"]["start_changed_at"] is None
    assert world.state(scenario["id"])["line"]["start_changed_at"] == lines["From Hire"]["start_changed_at"]
    # the Base line cannot be acknowledged by a Member, a Scenario by any Member
    done = member.post(f"{world.path}/lines/{scenario['id']}/acknowledge-start")
    assert done.status_code == 200 and done.json()["start_changed_at"] is None and done.json()["version"] == 1
    assert world.lines()["From Hire"]["start_changed_at"] is None and world.lines()["Deeper"]["start_changed_at"] is not None
    assert world.owner.post(f"{world.path}/lines/{deeper['id']}/acknowledge-start").json()["start_changed_at"] is None
    assert member.post(f"{world.path}/lines/{world.line}/acknowledge-start").status_code == 403
    assert world.owner.post(f"{world.path}/lines/{uuid4()}/acknowledge-start").status_code == 404
    world.owner.delete(f"{world.path}/changes/{inserted['id']}", params={"expected_version": 1})
    assert world.lines()["From Hire"]["start_changed_at"] is not None  # removing an earlier change changes the start again


def test_a_scenario_gets_a_copy_of_the_parents_metrics_and_values_that_is_then_independent(database_url: str, stack: ExitStack) -> None:
    world = World(stack, database_url, "tln-metrics")
    data = basic(world)
    metrics = f"{world.path}/lines/{world.line}/metrics"
    revenue = world.owner.post(metrics, json={"key": "revenue", "name": "Revenue", "unit": "EUR"}).json()
    world.owner.post(metrics, json={"key": "tied", "name": "Tied to Ada"})
    world.owner.post(metrics, json={"key": "twice", "name": "Twice", "formula": "revenue * 2"})
    world.owner.put(f"{metrics}/{revenue['id']}/values", json={"values": [{"period": "2026-01-01", "value": 10}, {"period": "2026-02-01", "value": 20}]})
    ada, app_node = data["ids"]["C"], data["ids"]["A"]
    with transaction_session(world.factory, RequestContext(organization_id=UUID(world.org))) as session:
        session.execute(text("UPDATE metrics SET node_id = :node WHERE key = 'tied'"), {"node": ada})
        session.execute(text("UPDATE metrics SET node_id = :node WHERE key = 'revenue'"), {"node": app_node})
    early = make(world, "Early", data["first"]["id"])  # Ada does not exist yet there
    late = make(world, "Late", data["second"]["id"])
    for line, tied_to in ((early, None), (late, ada)):
        listed = {item["key"]: item for item in world.owner.get(f"{world.path}/lines/{line['id']}/metrics").json()}
        assert set(listed) == {"revenue", "tied", "twice"} and listed["revenue"]["unit"] == "EUR" and listed["revenue"]["node_id"] == app_node
        assert listed["tied"]["node_id"] == tied_to and listed["twice"]["formula"] == "revenue * 2" and listed["revenue"]["version"] == 1
        copy = world.owner.get(f"{world.path}/lines/{line['id']}/metrics/{listed["revenue"]["id"]}/series").json()
        assert [(item["period"], item["value"]) for item in copy["points"]] == [("2026-01-01", 10), ("2026-02-01", 20)]
        assert listed["revenue"]["id"] != revenue["id"]
    world.owner.put(f"{metrics}/{revenue['id']}/values", json={"values": [{"period": "2026-01-01", "value": 99}]})
    copy_id = {item["key"]: item["id"] for item in world.owner.get(f"{world.path}/lines/{late['id']}/metrics").json()}["revenue"]
    assert world.owner.get(f"{world.path}/lines/{late['id']}/metrics/{copy_id}/series").json()["points"][0]["value"] == 10


def test_lines_per_model_are_limited(database_url: str, stack: ExitStack, monkeypatch) -> None:
    monkeypatch.setenv("LIMIT_LINES_PER_MODEL", "2")
    world = World(stack, database_url, "tln-limit")
    data = basic(world)
    make(world, "One", data["first"]["id"])
    refused = create(world, "Two", data["first"]["id"])
    assert refused.status_code == 409 and refused.json()["detail"] == {"reason": "limit_reached", "limit": "lines_per_model", "maximum": 2}
    assert len(world.lines()) == 2


def test_rename_follows_who_owns_the_line_and_checks_names_and_versions(database_url: str, stack: ExitStack) -> None:
    world = World(stack, database_url, "tln-rename")
    data = basic(world)
    creator, other = world.member("tln-rename-a"), world.member("tln-rename-b")
    mine = make(world, "Mine", data["first"]["id"], creator)
    path = f"{world.path}/lines/{mine['id']}"
    assert other.patch(path, json={"name": "Stolen", "expected_version": 1}).status_code == 403
    renamed = creator.patch(path, json={"name": "  Renamed  scenario", "description": "why", "expected_version": 1})
    assert renamed.status_code == 200 and renamed.json()["name"] == "Renamed scenario" and renamed.json()["description"] == "why" and renamed.json()["version"] == 2
    stale = creator.patch(path, json={"name": "Again", "expected_version": 1})
    assert stale.status_code == 409 and stale.json()["detail"] == {"latest_version": 2}
    assert world.owner.patch(path, json={"name": "By owner", "description": "why", "expected_version": 2}).json()["version"] == 3  # Owners and Admins rename any Scenario
    unchanged = world.owner.patch(path, json={"name": "By owner", "description": "why", "expected_version": 3})
    assert unchanged.status_code == 200 and unchanged.json()["version"] == 3  # nothing changed: no new version
    clear = world.owner.patch(path, json={"name": "By owner", "expected_version": 3})
    assert clear.json()["description"] is None and clear.json()["version"] == 4
    other_one = make(world, "Other one", data["first"]["id"])
    for name in ("baseline", "OTHER ONE"):
        duplicate = creator.patch(path, json={"name": name, "expected_version": 4}) if name != "baseline" else world.owner.patch(path, json={"name": name, "expected_version": 4})
        assert duplicate.status_code == 409 and duplicate.json()["detail"] == {"reason": "duplicate_name"}
    assert world.owner.patch(path, json={"name": "BY OWNER", "expected_version": 4}).status_code == 200  # a different case of its own name is not a duplicate
    # the Base line: Owner or Admin only; the Member who created a Scenario cannot rename it
    base_path = f"{world.path}/lines/{world.line}"
    assert creator.patch(base_path, json={"name": "Reality", "expected_version": 1}).status_code == 403
    assert world.owner.patch(base_path, json={"name": "Reality", "expected_version": 1}).json()["name"] == "Reality"
    assert world.owner.patch(f"{world.path}/lines/{uuid4()}", json={"name": "Nope", "expected_version": 1}).status_code == 404
    assert world.owner.patch(path, json={"name": " ", "expected_version": 5}).status_code == 422 and other_one["name"] == "Other one"


def test_delete_rules_and_everything_the_line_owned_goes_with_it(database_url: str, stack: ExitStack) -> None:
    world = World(stack, database_url, "tln-delete")
    data = basic(world)
    creator, other = world.member("tln-delete-a"), world.member("tln-delete-b")
    base_line = f"{world.path}/lines/{world.line}"
    assert world.owner.delete(base_line).status_code == 422 and world.owner.delete(base_line).json()["detail"] == {"reason": "base_line"}
    assert creator.delete(base_line).status_code == 422
    parent = make(world, "Parent", data["first"]["id"], creator)
    own = world.ok(parent["id"], "2026-03-01", "Own", [add_node(str(uuid4()), world.types["goal"], "Goal")])
    child = make(world, "Child", own["id"], other)
    assert world.owner.get(f"{world.path}/lines/{parent['id']}/changes").json()[0]["branches"] == [{"line_id": child["id"], "name": "Child"}]
    blocked = creator.delete(f"{world.path}/lines/{parent['id']}")
    assert blocked.status_code == 409 and blocked.json()["detail"] == {"reason": "has_children", "children": 1}
    assert world.owner.delete(f"{world.path}/lines/{parent['id']}").status_code == 409  # not even an Owner
    assert creator.delete(f"{world.path}/lines/{child['id']}").status_code == 403  # created by another Member
    assert other.delete(f"{world.path}/lines/{child['id']}", params={"expected_version": 9}).status_code == 409
    assert other.delete(f"{world.path}/lines/{child['id']}", params={"expected_version": 1}).status_code == 204
    # give the Scenario metrics, values, a simulation and positions, then delete it as its creator
    metrics = f"{world.path}/lines/{parent['id']}/metrics"
    metric = world.owner.post(metrics, json={"key": "m", "name": "M"}).json()
    world.owner.put(f"{metrics}/{metric['id']}/values", json={"values": [{"period": "2026-01-01", "value": 1}, {"period": "2026-02-01", "value": 2}, {"period": "2026-03-01", "value": 3}]})
    assert world.owner.post(f"{world.path}/lines/{parent['id']}/simulations", json={"name": "Run", "method": "linear", "horizon_months": 3}).status_code == 201
    node = world.state(parent["id"])["nodes"][0]["id"]
    assert world.owner.put(f"{world.path}/lines/{parent['id']}/positions", json=[{"node_id": node, "x": 1, "y": 2}]).status_code == 200
    # the copy of the metric in the deleted child and the rows of the parent are all there before the delete
    line = parent["id"]
    tables = {table: f"SELECT count(*) FROM {table} WHERE line_id = :line" for table in ("timeline_changes", "node_positions", "metrics", "metric_values", "simulations")}
    before = {table: count(world, sql, line=line) for table, sql in tables.items()}
    assert all(value > 0 for value in before.values()), before
    assert creator.delete(f"{world.path}/lines/{parent['id']}", params={"expected_version": 1}).status_code == 204
    after = {table: count(world, sql, line=line) for table, sql in tables.items()}
    assert set(after.values()) == {0}, after
    assert count(world, "SELECT count(*) FROM change_edits WHERE change_id = :change", change=own["id"]) == 0
    assert count(world, "SELECT count(*) FROM model_lines WHERE id IN (:a, :b)", a=parent["id"], b=child["id"]) == 0
    assert [item["name"] for item in world.owner.get(f"{world.path}/lines").json()] == ["Baseline"]
    assert world.owner.get(f"{world.path}/lines/{parent['id']}/state").status_code == 404
    assert world.owner.delete(f"{world.path}/lines/{parent['id']}").status_code == 404
    assert len(world.changes()) == 3 and names(world.state()) == {"App", "Onboarding", "Ada"}  # the parent line is untouched
    # an Owner may delete a Scenario another Member made; the branch change may then be deleted again
    again = make(world, "Again", data["second"]["id"], creator)
    assert world.owner.delete(f"{world.path}/changes/{data['second']['id']}", params={"expected_version": 1}).status_code == 409
    assert world.owner.delete(f"{world.path}/lines/{again['id']}").status_code == 204
    assert world.owner.delete(f"{world.path}/changes/{data['second']['id']}", params={"expected_version": 1}).status_code == 204


def test_positions_are_written_per_line_with_fallback_and_without_change_or_audit(database_url: str, stack: ExitStack) -> None:
    world = World(stack, database_url, "tln-positions")
    data = basic(world)
    a, b, c = data["ids"]["A"], data["ids"]["B"], data["ids"]["C"]
    scenario = make(world, "Draw", data["second"]["id"])
    sub = make(world, "Sub", world.ok(scenario["id"], "2026-03-01", "More", [add_node(str(uuid4()), world.types["goal"], "Extra")])["id"])

    def drawn(line: str) -> dict[str, tuple[float, float]]:
        return {item["node_id"]: (item["x"], item["y"]) for item in world.state(line)["positions"]}

    assert drawn(world.line)[a] == (10, 20) and drawn(scenario["id"])[a] == (10, 20) and drawn(sub["id"])[a] == (10, 20)  # added position, inherited
    changes, audit, versions = len(world.changes()), len(world.audit()), world.lines()
    put = world.owner.put(f"{world.path}/lines/{scenario['id']}/positions", json=[{"node_id": a, "x": 100.5, "y": -3}, {"node_id": b, "x": 1, "y": 2}, {"node_id": a, "x": 111, "y": 222}])
    assert put.status_code == 200 and put.json() == [{"node_id": a, "x": 111, "y": 222}, {"node_id": b, "x": 1, "y": 2}]  # the last entry for a node wins
    assert drawn(scenario["id"])[a] == (111, 222) and drawn(scenario["id"])[b] == (1, 2)
    assert drawn(world.line)[a] == (10, 20)  # the Base line keeps its drawing
    assert drawn(sub["id"])[a] == (111, 222) and drawn(sub["id"])[c] == drawn(scenario["id"])[c]  # a Scenario of the Scenario falls back to it
    again = world.owner.put(f"{world.path}/lines/{scenario['id']}/positions", json=[{"node_id": a, "x": 5, "y": 6}])
    assert again.status_code == 200 and drawn(scenario["id"])[a] == (5, 6) and drawn(scenario["id"])[b] == (1, 2)  # upsert
    assert world.owner.put(f"{world.path}/lines/{sub['id']}/positions", json=[{"node_id": a, "x": 7, "y": 8}]).status_code == 200
    assert drawn(sub["id"])[a] == (7, 8) and drawn(scenario["id"])[a] == (5, 6)
    assert world.owner.put(f"{world.path}/lines/{world.line}/positions", json=[]).json() == []
    assert len(world.changes()) == changes and len(world.audit()) == audit and world.lines() == versions  # no change, no audit entry, no version edit
    assert count(world, "SELECT count(*) FROM node_positions WHERE line_id = :line", line=scenario["id"]) == 3  # Ada's and App's rows plus the position seeded by its own change "More"


def test_a_position_needs_a_node_of_the_line_at_its_latest_change(database_url: str, stack: ExitStack) -> None:
    world = World(stack, database_url, "tln-position-nodes")
    data = basic(world)
    scenario = make(world, "Early", data["first"]["id"])
    path = f"{world.path}/lines/{scenario['id']}/positions"
    ada = data["ids"]["C"]  # hired on the Base line after the branch point
    refused = world.owner.put(path, json=[{"node_id": data["ids"]["A"], "x": 1, "y": 1}, {"node_id": ada, "x": 1, "y": 1}])
    assert refused.status_code == 422 and refused.json()["detail"] == {"reason": "unknown_node", "node_ids": [ada]}
    assert [item["node_id"] for item in world.state(scenario["id"])["positions"] if (item["x"], item["y"]) == (1, 1)] == []  # all or nothing
    assert world.owner.put(f"{world.path}/lines/{world.line}/positions", json=[{"node_id": ada, "x": 1, "y": 2}]).status_code == 200
    assert world.owner.put(path, json=[{"node_id": str(uuid4()), "x": 1, "y": 1}]).status_code == 422
    assert world.owner.put(f"{world.path}/lines/{uuid4()}/positions", json=[]).status_code == 404
    assert world.owner.put(path, json=[{"node_id": data["ids"]["A"], "x": "left", "y": 1}]).status_code == 422
    assert world.owner.put(path, json={"node_id": data["ids"]["A"], "x": 1, "y": 1}).status_code == 422
    removed = world.ok(scenario["id"], "2026-03-01", "Drop", [{"op": "remove_node", "element_id": data["ids"]["B"]}])
    assert removed["edit_counts"] == {"remove_node": 1}
    assert world.owner.put(path, json=[{"node_id": data["ids"]["B"], "x": 1, "y": 1}]).status_code == 422  # removed at the line's latest change
    assert world.owner.put(path, json=[{"node_id": data["ids"]["A"], "x": 9, "y": 9}]).status_code == 200


def test_roles_for_scenarios_and_positions(database_url: str, stack: ExitStack) -> None:
    world = World(stack, database_url, "tln-roles")
    data = basic(world)
    member = world.member("tln-roles-m")
    scenario = make(world, "By member", data["first"]["id"], member)  # any Member may create a Scenario, also from the Base line
    node = data["ids"]["A"]
    assert member.put(f"{world.path}/lines/{world.line}/positions", json=[{"node_id": node, "x": 1, "y": 1}]).status_code == 403
    assert world.owner.put(f"{world.path}/lines/{world.line}/positions", json=[{"node_id": node, "x": 1, "y": 1}]).status_code == 200
    assert member.put(f"{world.path}/lines/{scenario['id']}/positions", json=[{"node_id": node, "x": 2, "y": 2}]).status_code == 200
    other = world.member("tln-roles-o")
    assert other.put(f"{world.path}/lines/{scenario['id']}/positions", json=[{"node_id": node, "x": 3, "y": 3}]).status_code == 200  # drawing a Scenario is any Member's
    assert other.get(f"{world.path}/lines").status_code == 200 and member.get(f"{world.path}/lines/{world.line}/state").status_code == 200
    assert member.patch(f"{world.path}/lines/{world.line}", json={"name": "Nope", "expected_version": 1}).status_code == 403
    assert member.delete(f"{world.path}/lines/{world.line}").status_code == 422


def test_a_read_only_organization_reads_but_cannot_edit_lines_or_positions(database_url: str, stack: ExitStack) -> None:
    world = World(stack, database_url, "tln-readonly")
    data = basic(world)
    scenario = make(world, "Before", data["first"]["id"])
    readonly(world)
    path = f"{world.path}/lines"
    node = data["ids"]["A"]
    assert create(world, "Blocked", data["first"]["id"]).status_code == 403
    assert world.owner.patch(f"{path}/{scenario['id']}", json={"name": "Blocked", "expected_version": 1}).status_code == 403
    assert world.owner.delete(f"{path}/{scenario['id']}").status_code == 403
    assert world.owner.post(f"{path}/{scenario['id']}/acknowledge-start").status_code == 403
    assert world.owner.put(f"{path}/{scenario['id']}/positions", json=[{"node_id": node, "x": 1, "y": 1}]).status_code == 403
    assert len(world.lines()) == 2 and world.state(scenario["id"])["line"]["name"] == "Before"


def test_audit_entries_carry_ids_and_never_names_or_descriptions(database_url: str, stack: ExitStack) -> None:
    world = World(stack, database_url, "tln-audit")
    data = basic(world)
    scenario = make(world, "Secret name", data["first"]["id"], description="Secret description")
    path = f"{world.path}/lines/{scenario['id']}"
    world.owner.patch(path, json={"name": "Secret renamed", "description": "Secret again", "expected_version": 1})
    node = data["ids"]["A"]
    world.owner.put(f"{path}/positions", json=[{"node_id": node, "x": 1, "y": 1}])
    world.owner.post(f"{path}/acknowledge-start")
    world.owner.delete(path)
    items = [item for item in world.audit() if item["action"].startswith("line.")]
    assert [item["action"] for item in items][::-1] == ["line.created", "line.renamed", "line.deleted"]  # positions and acknowledging leave no entry
    for item in items:
        assert item["target_type"] == "line" and item["target_id"] == scenario["id"]
        assert item["change_summary"]["model_id"] == world.model and item["change_summary"]["line_id"] == scenario["id"]
    by_action = {item["action"]: item["change_summary"] for item in items}
    assert by_action["line.created"]["parent_line_id"] == world.line and by_action["line.created"]["branch_change_id"] == data["first"]["id"]
    assert by_action["line.renamed"]["fields"] == ["name", "description"] and by_action["line.deleted"]["change_count"] == 0
    assert "ecret" not in json.dumps(items)


def test_another_organization_cannot_touch_lines_or_branch_from_its_changes(database_url: str, stack: ExitStack) -> None:
    world = World(stack, database_url, "tln-rls-a")
    data = basic(world)
    scenario = make(world, "Mine", data["first"]["id"])
    _, stranger, other_org, other_base = _tenant(stack, database_url, "tln-rls-b")
    node = data["ids"]["A"]
    for path in (world.path, f"{other_base}/models/{world.model}"):
        assert stranger.post(f"{path}/lines", json={"name": "Injected", "branch_change_id": data["first"]["id"]}).status_code == 404
        assert stranger.patch(f"{path}/lines/{scenario['id']}", json={"name": "Injected", "expected_version": 1}).status_code == 404
        assert stranger.delete(f"{path}/lines/{scenario['id']}").status_code == 404
        assert stranger.post(f"{path}/lines/{scenario['id']}/acknowledge-start").status_code == 404
        assert stranger.put(f"{path}/lines/{scenario['id']}/positions", json=[{"node_id": node, "x": 1, "y": 1}]).status_code == 404
    other_model = stranger.post(f"{other_base}/models", json={"name": "Mine too"}).json()["id"]
    assert stranger.post(f"{other_base}/models/{other_model}/lines", json={"name": "Cross", "branch_change_id": data["first"]["id"]}).status_code == 404  # a change of another Organization
    assert stranger.patch(f"{other_base}/models/{other_model}/lines/{scenario['id']}", json={"name": "Cross", "expected_version": 1}).status_code == 404
    foreign = {table: count(world, f"SELECT count(*) FROM {table} WHERE organization_id = :id", id=other_org) for table in ("model_lines", "node_positions", "metrics")}
    assert set(foreign.values()) == {0}, foreign  # row-level security hides the other Organization's rows
    assert len(world.lines()) == 2 and world.lines()["Mine"]["name"] == "Mine"
