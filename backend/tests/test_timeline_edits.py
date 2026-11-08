"""Canvas edits as edits inside a change (model-timeline ticket 07): compaction, refusal, stale, roles, positions, audit, RLS."""
import json
from contextlib import ExitStack
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, text

from app.database import RequestContext, transaction_session
from test_timeline_changes import World, add_connection, add_node, basic
from test_models_graph import _tenant


@pytest.fixture
def stack():
    with ExitStack() as clients:
        yield clients


def node(world: World, change: str, kind: str, name: str, client=None, **extra):
    return (client or world.owner).post(f"{world.path}/changes/{change}/nodes", json={"node_type_id": world.types[kind], "name": name, **extra})


def link(world: World, change: str, kind: str, source: str, target: str, client=None, **extra):
    return (client or world.owner).post(f"{world.path}/changes/{change}/connections", json={"connection_type_id": world.types[kind], "source_node_id": source, "target_node_id": target, **extra})


def version(world: World, change: str) -> int:
    return world.owner.get(f"{world.path}/changes/{change}").json()["version"]


def detail(world: World, change: str) -> dict:
    return world.owner.get(f"{world.path}/changes/{change}").json()


def ops(world: World, change: str) -> list[tuple[str, dict]]:
    return [(item["op"], item["payload"]) for item in detail(world, change)["edits"]]


def count(world: World, sql: str, **params) -> int:
    with transaction_session(world.factory, RequestContext(organization_id=UUID(world.org))) as session:
        return session.execute(text(sql), params).scalar_one()


def shown(world: World, change: str, line: str | None = None) -> dict:
    return world.state(line, change_id=change)


def test_a_created_node_is_one_add_edit_with_its_id_a_position_and_an_audit_entry_without_names(database_url: str, stack: ExitStack) -> None:
    world = World(stack, database_url, "edit-create")
    created = node(world, world.initial, "product", "  Secret   App ", description="d", x=12, y=34, expected_version=1)
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["node"]["id"] == body["id"] and body["node"]["name"] == "Secret App" and (body["node"]["x"], body["node"]["y"]) == (12, 34)
    assert body["change"]["version"] == 2 and body["change"]["edit_counts"] == {"add_node": 1}
    assert [(item["op"], item["element_id"]) for item in body["change"]["edits"]] == [("add_node", body["id"])]
    assert shown(world, world.initial)["nodes"][0]["id"] == body["id"]
    assert count(world, "SELECT count(*) FROM node_positions WHERE line_id = :line AND node_id = :node AND x = 12 AND y = 34", line=world.line, node=body["id"]) == 1
    audit = [item for item in world.audit() if item["action"] == "change.updated"]
    assert len(audit) == 1 and audit[0]["change_summary"]["edit_counts"] == {"add_node": 1} and audit[0]["change_summary"]["fields"] == ["edits"]
    assert "Secret" not in json.dumps(audit)


def test_adding_then_removing_an_element_leaves_no_edit_and_no_position(database_url: str, stack: ExitStack) -> None:
    world = World(stack, database_url, "edit-compact-remove")
    a = node(world, world.initial, "product", "A").json()["id"]
    b = node(world, world.initial, "journey", "B").json()["id"]
    c = link(world, world.initial, "c:features_in", a, b).json()["id"]
    assert [op for op, _ in ops(world, world.initial)] == ["add_node", "add_node", "add_connection"]
    # remove the connection again: both its edits vanish
    assert world.owner.delete(f"{world.path}/changes/{world.initial}/connections/{c}", params={"expected_version": version(world, world.initial)}).status_code == 204
    assert [op for op, _ in ops(world, world.initial)] == ["add_node", "add_node"]
    # remove a node: its add vanishes together with every edit that touched it, also its connection and its renames
    c2 = link(world, world.initial, "c:features_in", a, b).json()["id"]
    world.owner.patch(f"{world.path}/changes/{world.initial}/nodes/{a}", json={"expected_version": version(world, world.initial), "name": "A2"})
    assert world.owner.delete(f"{world.path}/changes/{world.initial}/nodes/{a}", params={"expected_version": version(world, world.initial)}).status_code == 204
    assert [(op, payload["name"]) for op, payload in ops(world, world.initial)] == [("add_node", "B")]
    assert c2 and shown(world, world.initial)["connections"] == []
    assert count(world, "SELECT count(*) FROM node_positions WHERE line_id = :line AND node_id = :node", line=world.line, node=a) == 0
    assert world.owner.delete(f"{world.path}/changes/{world.initial}/nodes/{b}", params={"expected_version": version(world, world.initial)}).status_code == 204
    final = detail(world, world.initial)
    assert final["edits"] == [] and final["edit_count"] == 0 and world.state(change_id=world.initial)["nodes"] == []


def test_renaming_twice_leaves_one_edit_and_an_added_node_keeps_one_add(database_url: str, stack: ExitStack) -> None:
    world = World(stack, database_url, "edit-compact-rename")
    data = basic(world)
    a, later = data["ids"]["A"], data["second"]["id"]
    rename = lambda change, element, **fields: world.owner.patch(f"{world.path}/changes/{change}/nodes/{element}", json={"expected_version": version(world, change), **fields})  # noqa: E731
    assert rename(later, a, name="First").status_code == 200
    assert rename(later, a, name="Second").status_code == 200
    assert rename(later, a, description="About").status_code == 200
    assert [(op, payload) for op, payload in ops(world, later) if op == "update_node"] == [("update_node", {"name": "Second", "description": "About"})]
    # a node added in the change takes its renames into the add itself
    added = node(world, later, "goal", "Draft", x=1, y=2).json()["id"]
    rename(later, added, name="Final")
    rename(later, added, node_type_id=world.types["team"])
    adds = [payload for op, payload in ops(world, later) if op == "add_node" and payload["name"] == "Final"]
    assert adds == [{"node_type_id": world.types["team"], "name": "Final", "x": 1.0, "y": 2.0}]
    # setting back what the node already is changes nothing: no new version, no write
    before = version(world, later)
    again = rename(later, a, name="Second")
    assert again.status_code == 200 and again.json()["change"]["version"] == before
    cleared = rename(later, a, description=None)
    assert cleared.status_code == 200 and [payload for op, payload in ops(world, later) if op == "update_node"] == [{"name": "Second", "description": None}]
    # renaming back to the original name leaves no edit for that node
    other = data["ids"]["B"]
    rename(later, other, name="Temporary")
    rename(later, other, name="Onboarding")
    assert [item for item in detail(world, later)["edits"] if item["element_id"] == other] == []


def test_connections_are_retyped_and_rerouted_and_edits_merge(database_url: str, stack: ExitStack) -> None:
    world = World(stack, database_url, "edit-connections")
    team, other, product = (node(world, world.initial, kind, name).json()["id"] for kind, name in (("team", "Platform"), ("team", "Data"), ("product", "App")))
    connection = link(world, world.initial, "c:offers", team, product).json()["id"]
    edit = lambda **fields: world.owner.patch(f"{world.path}/changes/{world.initial}/connections/{connection}", json={"expected_version": version(world, world.initial), **fields})  # noqa: E731
    # in the change that added it, re-typing and re-routing fold into the add
    assert edit(connection_type_id=world.types["c:uses"]).status_code == 200
    rerouted = edit(source_node_id=other)
    assert rerouted.status_code == 200 and rerouted.json()["connection"]["source_node_id"] == other and rerouted.json()["connection"]["connection_type_id"] == world.types["c:uses"]
    assert [payload for op, payload in ops(world, world.initial) if op == "add_connection"] == [{"connection_type_id": world.types["c:uses"], "source_node_id": other, "target_node_id": product}]
    assert [op for op, _ in ops(world, world.initial)].count("add_connection") == 1 and "reroute_connection" not in [op for op, _ in ops(world, world.initial)]
    # in a later change they are edits of their own, merged when repeated
    later = world.ok(world.line, "2026-03-01", "Later", [])["id"]
    edit_later = lambda **fields: world.owner.patch(f"{world.path}/changes/{later}/connections/{connection}", json={"expected_version": version(world, later), **fields})  # noqa: E731
    assert edit_later(connection_type_id=world.types["c:offers"]).status_code == 200
    assert edit_later(target_node_id=product).status_code == 200  # same as now: nothing to write
    assert edit_later(source_node_id=team).status_code == 200
    assert edit_later(source_node_id=other).status_code == 200
    assert ops(world, later) == [("change_connection_type", {"connection_type_id": world.types["c:offers"]})]  # the re-routes ended where the connection already started
    # a connection that does not exist, and a wrong type for the ends, are refused
    assert world.owner.patch(f"{world.path}/changes/{later}/connections/{uuid4()}", json={"expected_version": version(world, later), "source_node_id": team}).status_code == 404
    refused = edit_later(connection_type_id=world.types["c:is_assigned_to"])
    assert refused.status_code == 422 and refused.json()["detail"]["cause"] == "connection_not_allowed"
    # both at once: the order that replays is used (here the new type is only allowed between the new ends)
    world.owner.post(f"{world.path}/allowed-connections", json={"connection_type_id": world.types["c:is_assigned_to"], "source_node_type_id": world.types["team"], "target_node_type_id": world.types["team"]})
    both = edit_later(connection_type_id=world.types["c:is_assigned_to"], target_node_id=team)
    assert both.status_code == 422 and both.json()["detail"]["cause"] == "connection_not_allowed"  # neither step alone is allowed, so the pair is refused; the person removes and adds it instead
    assert both.json()["detail"]["change"] == later and [op for op, _ in ops(world, later)] == ["change_connection_type"]
    ordered = edit_later(connection_type_id=world.types["c:uses"], target_node_id=product)  # one step only: fine in either order
    assert ordered.status_code == 200 and ordered.json()["connection"]["connection_type_id"] == world.types["c:uses"]


def test_a_refusal_returns_the_chain_broken_body_and_leaves_the_change_unchanged(database_url: str, stack: ExitStack) -> None:
    world = World(stack, database_url, "edit-refuse")
    data = basic(world)
    a, c = data["ids"]["A"], data["ids"]["C"]
    first, second = data["first"]["id"], data["second"]["id"]
    team = node(world, second, "team", "Platform").json()["id"]
    join = world.ok(world.line, "2026-03-01", "Join team", [add_connection(uuid4(), world.types["c:is_assigned_to"], c, team)])
    before = detail(world, second)
    refused = world.owner.delete(f"{world.path}/changes/{second}/nodes/{team}", params={"expected_version": before["version"]})
    assert refused.status_code == 422
    body = refused.json()["detail"]
    assert body["reason"] == "chain_broken" and body["change"] == join["id"] and body["position"] == 0 and body["cause"] == "missing_endpoint" and body["element"] == team
    assert body["hint"]["change_title"] == "Join team" and body["hint"]["target_name"] == "Platform" and body["hint"]["code"] == "add_endpoint_before"
    assert detail(world, second) == before  # same version, same edits, same updated time
    assert any(item["name"] == "Platform" for item in world.state(change_id=second)["nodes"])
    assert count(world, "SELECT count(*) FROM node_positions WHERE node_id = :node", node=team) == 1  # nor did the position go
    # the same check covers an edit inside an earlier change: it must not break what comes after
    retype = world.owner.patch(f"{world.path}/changes/{second}/nodes/{c}", json={"expected_version": before["version"], "node_type_id": world.types["goal"]})
    assert retype.status_code == 422 and retype.json()["detail"]["cause"] == "connection_not_allowed" and retype.json()["detail"]["change"] == join["id"]
    assert detail(world, second) == before
    # an edit that nothing later depends on goes through: App's connection goes with the node
    removal = world.owner.delete(f"{world.path}/changes/{first}/nodes/{a}", params={"expected_version": version(world, first)})
    assert removal.status_code == 204
    assert all(item["id"] != a for item in world.state(change_id=join["id"])["nodes"]) and world.state(change_id=join["id"])["connections"][0]["target_node_id"] == team


def test_an_edit_in_a_parent_line_that_breaks_a_scenario_is_refused_and_names_it(database_url: str, stack: ExitStack) -> None:
    world = World(stack, database_url, "edit-scenario")
    data = basic(world)
    a = data["ids"]["A"]
    scenario = world.scenario("What if", data["second"]["id"])
    own = world.post(None, scenario, "2026-06-01", "Rename App", [update_name(a, "App 2")])
    assert own.status_code == 201
    refused = world.owner.delete(f"{world.path}/changes/{data['first']['id']}/nodes/{a}", params={"expected_version": version(world, data["first"]["id"])})
    assert refused.status_code == 422
    hint = refused.json()["detail"]["hint"]
    assert refused.json()["detail"]["cause"] == "missing_element" and hint["in_other_line"] is True and hint["scenario_name"] == "What if" and hint["change_title"] == "Rename App"
    assert shown(world, data["first"]["id"])["nodes"][0]["id"] == a


def update_name(element: str, name: str) -> dict:
    return {"op": "update_node", "element_id": element, "payload": {"name": name}}


def test_edits_into_any_change_of_the_line_not_only_the_last(database_url: str, stack: ExitStack) -> None:
    world = World(stack, database_url, "edit-middle")
    data = basic(world)
    first, second = data["first"]["id"], data["second"]["id"]
    added = node(world, first, "goal", "Early goal")
    assert added.status_code == 201
    assert any(item["name"] == "Early goal" for item in shown(world, first)["nodes"])
    assert any(item["name"] == "Early goal" for item in shown(world, second)["nodes"])  # later changes replay it
    assert ops(world, second) == [("add_node", {"node_type_id": world.types["person"], "name": "Ada"})]  # the later change is untouched
    assert [item["title"] for item in world.changes()][1:] == ["Start", "Hire"]
    assert world.audit()[0]["action"] == "change.updated"


def test_stale_versions_conflict_and_unknown_things_are_not_found(database_url: str, stack: ExitStack) -> None:
    world = World(stack, database_url, "edit-stale")
    a = node(world, world.initial, "product", "A", expected_version=1).json()["id"]
    stale = node(world, world.initial, "journey", "B", expected_version=1)
    assert stale.status_code == 409 and stale.json()["detail"] == {"latest_version": 2}
    assert node(world, world.initial, "journey", "B").status_code == 201  # a create may leave the version out
    path = f"{world.path}/changes/{world.initial}"
    assert world.owner.patch(f"{path}/nodes/{a}", json={"expected_version": 1, "name": "X"}).status_code == 409
    assert world.owner.delete(f"{path}/nodes/{a}", params={"expected_version": 1}).status_code == 409
    assert world.owner.delete(f"{path}/nodes/{a}").status_code == 422  # a delete needs the version
    assert link(world, world.initial, "c:features_in", a, a, expected_version=1).status_code == 409
    assert world.owner.patch(f"{path}/nodes/{a}", json={"expected_version": 3}).status_code == 422  # nothing to change
    assert world.owner.patch(f"{path}/nodes/{a}", json={"expected_version": 3, "name": None}).status_code == 422
    assert world.owner.patch(f"{path}/nodes/{uuid4()}", json={"expected_version": 3, "name": "X"}).status_code == 404
    assert world.owner.delete(f"{path}/nodes/{uuid4()}", params={"expected_version": 3}).status_code == 404
    assert world.owner.delete(f"{path}/connections/{uuid4()}", params={"expected_version": 3}).status_code == 404
    assert node(world, str(uuid4()), "goal", "G").status_code == 404
    assert world.owner.post(f"{path}/nodes", json={"node_type_id": world.types["goal"], "name": "   "}).status_code == 422
    unknown = world.owner.post(f"{path}/nodes", json={"node_type_id": str(uuid4()), "name": "Typeless"})
    assert unknown.status_code == 422 and unknown.json()["detail"]["cause"] == "missing_type"
    assert version(world, world.initial) == 3


def test_the_base_line_belongs_to_managers_scenarios_to_members_and_read_only_blocks_both(database_url: str, stack: ExitStack) -> None:
    world = World(stack, database_url, "edit-roles")
    data = basic(world)
    member = world.member()
    second = data["second"]["id"]
    assert node(world, second, "goal", "Nope", client=member).status_code == 403
    assert member.patch(f"{world.path}/changes/{second}/nodes/{data['ids']['C']}", json={"expected_version": 1, "name": "Nope"}).status_code == 403
    assert member.delete(f"{world.path}/changes/{second}/nodes/{data['ids']['C']}", params={"expected_version": 1}).status_code == 403
    assert link(world, second, "c:features_in", data["ids"]["A"], data["ids"]["B"], client=member).status_code == 403
    scenario = world.scenario("Plan", second)
    own = member.post(f"{world.path}/lines/{scenario}/changes", json={"occurred_on": "2026-06-01", "title": "Plan", "edits": []}).json()["id"]
    created = node(world, own, "goal", "Member's goal", client=member)
    assert created.status_code == 201
    assert count(world, "SELECT count(*) FROM node_positions WHERE line_id = :line AND node_id = :node", line=scenario, node=created.json()["id"]) == 1  # the position belongs to the Scenario's line
    assert count(world, "SELECT count(*) FROM node_positions WHERE line_id = :line AND node_id = :node", line=world.line, node=created.json()["id"]) == 0
    assert member.delete(f"{world.path}/changes/{own}/nodes/{created.json()['id']}", params={"expected_version": version(world, own)}).status_code == 204
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(text("UPDATE organizations SET subscription_access_state = 'canceled' WHERE id = :id"), {"id": world.org})
    engine.dispose()
    before = version(world, second)
    assert node(world, second, "goal", "Blocked").status_code == 403
    assert node(world, own, "goal", "Blocked", client=member).status_code == 403
    assert world.owner.delete(f"{world.path}/changes/{second}/nodes/{data['ids']['C']}", params={"expected_version": before}).status_code == 403
    assert version(world, second) == before


def test_another_organization_cannot_edit_changes_of_this_one(database_url: str, stack: ExitStack) -> None:
    world = World(stack, database_url, "edit-rls-a")
    data = basic(world)
    _, stranger, _, other_base = _tenant(stack, database_url, "edit-rls-b")
    other_model = stranger.post(f"{other_base}/models", json={"name": "Mine"}).json()["id"]
    second = data["second"]["id"]
    for path in (world.path, f"{other_base}/models/{world.model}", f"{other_base}/models/{other_model}"):  # another Organization's model, a Model id of ours in their Organization, their own Model
        assert stranger.post(f"{path}/changes/{second}/nodes", json={"node_type_id": world.types["goal"], "name": "Injected"}).status_code == 404
        assert stranger.patch(f"{path}/changes/{second}/nodes/{data['ids']['C']}", json={"expected_version": 1, "name": "Injected"}).status_code == 404
        assert stranger.delete(f"{path}/changes/{second}/nodes/{data['ids']['C']}", params={"expected_version": 1}).status_code == 404
        assert stranger.post(f"{path}/changes/{second}/connections", json={"connection_type_id": world.types["c:features_in"], "source_node_id": data["ids"]["A"], "target_node_id": data["ids"]["B"]}).status_code == 404
    assert [item["name"] for item in world.state(change_id=second)["nodes"]] == ["App", "Onboarding", "Ada"]


def test_the_edit_is_validated_against_later_changes_and_scenarios_and_restarts_dependents(database_url: str, stack: ExitStack) -> None:
    world = World(stack, database_url, "edit-restart")
    data = basic(world)
    scenario = world.scenario("From Hire", data["second"]["id"])
    assert world.lines()["From Hire"]["start_changed_at"] is None
    assert node(world, data["first"]["id"], "goal", "Earlier goal").status_code == 201
    assert world.lines()["From Hire"]["start_changed_at"] is not None  # an edit before its branch point changes the Scenario's start
    assert scenario in {item["id"] for item in world.owner.get(f"{world.path}/lines").json()}
    # an edit after the branch point leaves it alone
    world.owner.post(f"{world.path}/lines/{scenario}/acknowledge-start")
    later = world.ok(world.line, "2026-07-01", "After", [])["id"]
    assert node(world, later, "goal", "Later goal").status_code == 201
    assert world.lines()["From Hire"]["start_changed_at"] is None
