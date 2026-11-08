"""Writing changes: validation of the whole chain, roles, locking, audit, limits (model-timeline ticket 05)."""
import json
import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from contextlib import ExitStack
from datetime import date
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text

from app.database import RequestContext, create_session_factory, transaction_session
from app.models import ModelLine, NodePosition, TwinModel
from app.timeline.chain import LineRecord
from app.timeline.errors import ChainBroken
from app.timeline.loader import ModelTimeline
from app.timeline.state import Metamodel
from app.timeline.validate import Validation, describe_break
from test_invitations import join, login
from test_models_graph import _graph, _tenant, _types


@pytest.fixture
def stack():
    with ExitStack() as clients:
        yield clients


class World:
    """An Organization with a Model whose Base line holds only the initial (empty) change."""

    def __init__(self, stack: ExitStack, database_url: str, subject: str) -> None:
        self.application, self.owner, self.org, self.base = _tenant(stack, database_url, subject)
        self.stack, self.database_url = stack, database_url
        self.model = self.owner.post(f"{self.base}/models", json={"name": "Timeline"}).json()["id"]
        self.path = f"{self.base}/models/{self.model}"
        self.types = _types(_graph(self.owner, self.base, self.model))
        lines = self.owner.get(f"{self.path}/lines").json()
        self.line = lines[0]["id"]
        self.initial = self.owner.get(f"{self.path}/lines/{self.line}/changes").json()[0]["id"]
        self.factory = create_session_factory(self.application.state.database_engine)
        with transaction_session(self.factory, RequestContext(organization_id=UUID(self.org))) as session:  # the initial change is dated the creation day; the tests write earlier history
            session.execute(text("UPDATE timeline_changes SET occurred_on = '2025-12-31' WHERE line_id = :line"), {"line": self.line})

    def post(self, client: TestClient | None, line: str, day: str, title: str, edits: list[dict], **extra):
        return (client or self.owner).post(f"{self.path}/lines/{line}/changes", json={"occurred_on": day, "title": title, "edits": edits, **extra})

    def ok(self, line: str, day: str, title: str, edits: list[dict], **extra) -> dict:
        response = self.post(None, line, day, title, edits, **extra)
        assert response.status_code == 201, response.text
        return response.json()

    def changes(self, line: str | None = None) -> list[dict]:
        return self.owner.get(f"{self.path}/lines/{line or self.line}/changes").json()

    def state(self, line: str | None = None, **params) -> dict:
        response = self.owner.get(f"{self.path}/lines/{line or self.line}/state", params=params)
        assert response.status_code == 200, response.text
        return response.json()

    def scenario(self, name: str, branch_change: str, parent: str | None = None) -> str:
        line_id = uuid4()
        with transaction_session(self.factory, RequestContext(organization_id=UUID(self.org))) as session:
            session.add(ModelLine(id=line_id, organization_id=UUID(self.org), model_id=UUID(self.model), name=name, kind="scenario", parent_line_id=UUID(parent or self.line), branch_change_id=UUID(branch_change)))
        return str(line_id)

    def lines(self) -> dict[str, dict]:
        return {item["name"]: item for item in self.owner.get(f"{self.path}/lines").json()}

    def member(self, subject: str = "tl-member") -> TestClient:
        member_app, _ = join(self.application, self.owner, self.org, subject=subject, email=f"{subject}@example.com")
        client = self.stack.enter_context(TestClient(member_app))
        login(client)
        return client

    def audit(self) -> list[dict]:
        return self.owner.get(f"{self.base}/audit-events", params={"limit": 100}).json()["items"]


def add_node(element: UUID | str, kind: str, name: str, **payload) -> dict:
    return {"op": "add_node", "element_id": str(element), "payload": {"node_type_id": kind, "name": name, **payload}}


def add_connection(element: UUID | str, kind: str, source: UUID | str, target: UUID | str) -> dict:
    return {"op": "add_connection", "element_id": str(element), "payload": {"connection_type_id": kind, "source_node_id": str(source), "target_node_id": str(target)}}


def update_node(element: UUID | str, **payload) -> dict:
    return {"op": "update_node", "element_id": str(element), "payload": payload}


def names(state: dict) -> set[str]:
    return {node["name"] for node in state["nodes"]}


def basic(world: World) -> dict:
    """Base line: Jan 1 add App (product) and Onboarding (journey) joined by features_in; plus Ada (person)."""
    ids = {key: str(uuid4()) for key in ("A", "B", "AB", "C")}
    first = world.ok(world.line, "2026-01-01", "Start", [add_node(ids["A"], world.types["product"], "App", x=10, y=20), add_node(ids["B"], world.types["journey"], "Onboarding"), add_connection(ids["AB"], world.types["c:features_in"], ids["A"], ids["B"])])
    second = world.ok(world.line, "2026-02-01", "Hire", [add_node(ids["C"], world.types["person"], "Ada")])
    return {"ids": ids, "first": first, "second": second}


def test_a_created_change_is_stored_numbered_and_seeds_positions_and_later_states_see_it(database_url: str, stack: ExitStack) -> None:
    world = World(stack, database_url, "tle-create")
    ids = {key: str(uuid4()) for key in "AB"}
    created = world.ok(world.line, "2026-03-01", "  Launch   app ", [add_node(ids["A"], world.types["product"], "App", description="d", x=10, y=20), {"op": "add_node", "payload": {"node_type_id": world.types["journey"], "name": "Onboarding", "x": 3, "y": 4}}], note="why")
    assert created["title"] == "Launch app" and created["note"] == "why" and created["version"] == 1 and created["planned"] is False
    assert [item["position"] for item in created["edits"]] == [0, 1] and created["edit_counts"] == {"add_node": 2}
    generated = created["edits"][1]["element_id"]
    assert UUID(generated) and created["edits"][1]["payload"] == {"node_type_id": world.types["journey"], "name": "Onboarding", "x": 3, "y": 4}
    assert [item["title"] for item in world.changes()] == ["Initial situation", "Launch app"]
    state = world.state(change_id=created["id"])
    assert names(state) == {"App", "Onboarding"}
    assert {item["node_id"]: (item["x"], item["y"]) for item in state["positions"]} == {ids["A"]: (10, 20), generated: (3, 4)}
    assert world.owner.get(f"{world.path}/changes/{created['id']}").json()["edits"][0]["element_id"] == ids["A"]
    with transaction_session(world.factory, RequestContext(organization_id=UUID(world.org))) as session:
        assert session.scalar(select(NodePosition.x).where(NodePosition.node_id == UUID(ids["A"]))) == 10


def test_every_cause_of_a_broken_chain_is_refused_and_nothing_is_saved(database_url: str, stack: ExitStack) -> None:
    world = World(stack, database_url, "tle-causes")
    data = basic(world)
    ids, types = data["ids"], world.types
    unknown = str(uuid4())
    before = len(world.changes())
    cases = {
        "missing_element": [update_node(unknown, name="Ghost")],
        "duplicate_element": [add_node(ids["A"], types["product"], "Again")],
        "missing_type": [add_node(str(uuid4()), unknown, "Typeless")],
        "connection_not_allowed": [add_connection(str(uuid4()), types["c:features_in"], ids["C"], ids["B"])],
        "missing_endpoint": [add_connection(str(uuid4()), types["c:features_in"], ids["A"], unknown)],
        "self_connection": [add_connection(str(uuid4()), types["c:features_in"], ids["A"], ids["A"])],
        "duplicate_connection": [add_connection(str(uuid4()), types["c:features_in"], ids["A"], ids["B"])],
    }
    for cause, edits in cases.items():
        response = world.post(None, world.line, "2026-05-01", f"Bad {cause}", [update_node(ids["A"], name="Fine"), *edits])
        assert response.status_code == 422, (cause, response.text)
        detail = response.json()["detail"]
        assert detail["reason"] == "chain_broken" and detail["cause"] == cause and detail["position"] == 1 and detail["line"] == world.line, detail
        assert detail["change"] and set(detail) == {"reason", "change", "line", "position", "element", "cause", "hint"}
        hint = detail["hint"]
        assert hint["code"] and hint["change_title"] == f"Bad {cause}" and hint["change_date"] == "2026-05-01" and hint["line_name"] == "Baseline" and hint["scenario_name"] is None and hint["in_other_line"] is False
    detail = world.post(None, world.line, "2026-05-01", "x", [update_node(unknown, name="Ghost")]).json()["detail"]
    assert detail["element"] == unknown and detail["hint"]["element_kind"] == "node" and detail["hint"]["op"] == "update_node"
    detail = world.post(None, world.line, "2026-05-01", "x", [add_connection(str(uuid4()), types["c:features_in"], ids["C"], ids["B"])]).json()["detail"]
    assert (detail["hint"]["source_name"], detail["hint"]["target_name"]) == ("Ada", "Onboarding") and detail["hint"]["type_name"]
    detail = world.post(None, world.line, "2026-05-01", "x", [add_node(ids["A"], types["product"], "Again")]).json()["detail"]
    assert detail["hint"]["element_name"] == "App" and detail["element"] == ids["A"]
    assert len(world.changes()) == before and names(world.state()) == {"App", "Onboarding", "Ada"}
    with transaction_session(world.factory, RequestContext(organization_id=UUID(world.org))) as session:
        assert session.scalar(text("SELECT count(*) FROM change_edits")) == 4 and session.scalar(text("SELECT count(*) FROM node_positions")) == 3
    assert [item["action"] for item in world.audit()].count("change.created") == 2


def test_a_scenario_change_dated_before_its_branch_change_is_refused_and_so_is_moving_the_branch_change_past_it(database_url: str, stack: ExitStack) -> None:
    world = World(stack, database_url, "tle-before")
    data = basic(world)
    scenario = world.scenario("What if", data["second"]["id"])  # branches from "Hire", 2026-02-01
    early = world.post(None, scenario, "2026-01-15", "Too early", [])
    detail = early.json()["detail"]
    assert early.status_code == 422 and detail["cause"] == "before_branch_change" and detail["position"] is None and detail["line"] == scenario
    assert detail["hint"]["scenario_name"] == "What if" and detail["hint"]["branch_change_title"] == "Hire" and detail["hint"]["branch_change_date"] == "2026-02-01" and detail["hint"]["code"] == "move_after_branch_change"
    own = world.ok(scenario, "2026-02-01", "Same day is fine", [update_node(data["ids"]["C"], name="Ada L")])
    moved = world.owner.patch(f"{world.path}/changes/{data['second']['id']}", json={"expected_version": 1, "occurred_on": "2026-03-01"})
    detail = moved.json()["detail"]
    assert moved.status_code == 422 and detail["cause"] == "before_branch_change" and detail["change"] == own["id"] and detail["line"] == scenario
    assert detail["hint"]["in_other_line"] is True and detail["hint"]["scenario_name"] == "What if" and detail["hint"]["change_title"] == "Same day is fine"
    assert {item["title"]: item["occurred_on"] for item in world.changes()}["Hire"] == "2026-02-01"


def test_a_missing_branch_change_is_described_with_its_own_cause() -> None:
    """Foreign keys keep a branch change in its parent line, so this cause only shows if the data itself is damaged; the refusal still describes it."""
    line, parent = uuid4(), uuid4()
    timeline = ModelTimeline(
        lines={parent: LineRecord(parent), line: LineRecord(line, parent, uuid4())},
        line_rows={parent: type("L", (), {"name": "Baseline", "kind": "base", "parent_line_id": None, "branch_change_id": None})(), line: type("L", (), {"name": "Lost", "kind": "scenario", "parent_line_id": parent, "branch_change_id": uuid4()})()},  # type: ignore[dict-item]
        changes={},
        metamodel=Metamodel(frozenset(), frozenset(), frozenset()),
    )
    detail = describe_break(ChainBroken(line, None, None, "missing_branch_change"), Validation(timeline, {}), parent)
    assert detail["cause"] == "missing_branch_change" and detail["hint"]["code"] == "restore_branch_change" and detail["hint"]["scenario_name"] == "Lost" and detail["hint"]["in_other_line"] is True


def test_a_correction_that_keeps_the_chain_valid_succeeds_and_later_states_follow(database_url: str, stack: ExitStack) -> None:
    world = World(stack, database_url, "tle-correct")
    data = basic(world)
    a = data["ids"]["A"]
    rename = world.ok(world.line, "2026-03-01", "Rename", [update_node(a, name="App 2")])
    assert names(world.state(as_of="2026-03-01")) == {"App 2", "Onboarding", "Ada"} and names(world.state(as_of="2026-02-28")) == {"App", "Onboarding", "Ada"}
    # Moving the creating change past its user breaks the chain: the later change is named, with the element.
    first = data["first"]
    broken = world.owner.patch(f"{world.path}/changes/{first['id']}", json={"expected_version": 1, "occurred_on": "2026-04-01"})
    detail = broken.json()["detail"]
    assert broken.status_code == 422 and detail["cause"] == "missing_element" and detail["change"] == rename["id"] and detail["element"] == a and detail["position"] == 0
    assert detail["hint"]["change_title"] == "Rename" and detail["hint"]["element_name"] == "App" and detail["hint"]["code"] == "add_element_before"
    assert {item["title"]: item["occurred_on"] for item in world.changes()}["Start"] == "2026-01-01"
    # Correct it in the valid order: content first, then the date.
    changed = world.owner.patch(f"{world.path}/changes/{rename['id']}", json={"expected_version": 1, "title": "Rename again", "edits": [update_node(a, name="App 3"), update_node(a, description="new")]})
    assert changed.status_code == 200 and changed.json()["version"] == 2 and [item["position"] for item in changed.json()["edits"]] == [0, 1]
    assert names(world.state(as_of="2026-03-01")) == {"App 3", "Onboarding", "Ada"}
    late = world.owner.patch(f"{world.path}/changes/{rename['id']}", json={"expected_version": 2, "occurred_on": "2026-05-01"})
    assert late.status_code == 200 and late.json()["occurred_on"] == "2026-05-01"
    assert world.owner.patch(f"{world.path}/changes/{first['id']}", json={"expected_version": 1, "occurred_on": "2026-04-01"}).status_code == 200
    assert names(world.state(as_of="2026-05-01")) == {"App 3", "Onboarding", "Ada"} and names(world.state(as_of="2026-04-01")) == {"App", "Onboarding", "Ada"} and names(world.state(as_of="2026-03-31")) == {"Ada"}
    # A no-op patch changes nothing, and a note can be cleared.
    same = world.owner.patch(f"{world.path}/changes/{rename['id']}", json={"expected_version": 3, "title": "Rename again"})
    assert same.status_code == 200 and same.json()["version"] == 3
    note = world.owner.patch(f"{world.path}/changes/{rename['id']}", json={"expected_version": 3, "note": "n"}).json()
    assert note["note"] == "n" and world.owner.patch(f"{world.path}/changes/{rename['id']}", json={"expected_version": 4, "note": None}).json()["note"] is None
    # A date moved after today makes the change planned; a planned change is allowed anywhere.
    planned = world.owner.patch(f"{world.path}/changes/{rename['id']}", json={"expected_version": 5, "occurred_on": "2027-01-01"}).json()
    assert planned["planned"] is True and "App 3" not in names(world.state())


def test_deleting_changes_checks_the_chain_and_a_branch_change_is_protected_by_name(database_url: str, stack: ExitStack) -> None:
    world = World(stack, database_url, "tle-delete")
    data = basic(world)
    a, c = data["ids"]["A"], data["ids"]["C"]
    scenario = world.scenario("What if", data["second"]["id"])
    world.ok(scenario, "2026-02-10", "Scenario edit", [update_node(a, name="Scenario App")])
    refused = world.owner.delete(f"{world.path}/changes/{data['second']['id']}", params={"expected_version": 1})
    assert refused.status_code == 409 and refused.json()["detail"]["reason"] == "branch_point" and refused.json()["detail"]["line"] == "What if" and refused.json()["detail"]["line_id"] == scenario
    broken = world.owner.delete(f"{world.path}/changes/{data['first']['id']}", params={"expected_version": 1})  # the Scenario changes A, which that change adds
    detail = broken.json()["detail"]
    assert broken.status_code == 422 and detail["reason"] == "chain_broken" and detail["line"] in (world.line, scenario)
    assert len(world.changes()) == 3
    plain = world.ok(world.line, "2026-03-01", "Plain", [update_node(c, name="Ada 2")])
    assert world.owner.delete(f"{world.path}/changes/{plain['id']}", params={"expected_version": 1}).status_code == 204
    assert [item["title"] for item in world.changes()] == ["Initial situation", "Start", "Hire"] and world.owner.get(f"{world.path}/changes/{plain['id']}").status_code == 404
    assert world.owner.delete(f"{world.path}/changes/{uuid4()}", params={"expected_version": 1}).status_code == 404
    with transaction_session(world.factory, RequestContext(organization_id=UUID(world.org))) as session:
        assert session.scalar(text("SELECT count(*) FROM change_edits WHERE change_id = :e"), {"e": plain["id"]}) == 0
    # Deleting the change that added a node also drops that node's drawn position.
    leaf = world.ok(world.line, "2026-04-01", "Leaf", [add_node(str(uuid4()), world.types["goal"], "Goal", x=1, y=1)])
    with transaction_session(world.factory, RequestContext(organization_id=UUID(world.org))) as session:
        assert session.scalar(text("SELECT count(*) FROM node_positions")) == 4
    assert world.owner.delete(f"{world.path}/changes/{leaf['id']}", params={"expected_version": 1}).status_code == 204
    with transaction_session(world.factory, RequestContext(organization_id=UUID(world.org))) as session:
        assert session.scalar(text("SELECT count(*) FROM node_positions")) == 3


def test_a_edit_that_a_scenario_depends_on_cannot_be_removed_and_the_scenario_is_named(database_url: str, stack: ExitStack) -> None:
    world = World(stack, database_url, "tle-dependent")
    data = basic(world)
    c = data["ids"]["C"]
    scenario = world.scenario("Hiring plan", data["second"]["id"])
    world.ok(scenario, "2026-02-05", "Promote Ada", [update_node(c, name="Ada Lead")])
    # Change "Hire" is the branch change; rewriting it so Ada is not added breaks the Scenario's own change.
    broken = world.owner.patch(f"{world.path}/changes/{data['second']['id']}", json={"expected_version": 1, "edits": []})
    detail = broken.json()["detail"]
    assert broken.status_code == 422 and detail["cause"] == "missing_element" and detail["line"] == scenario and detail["element"] == c
    assert detail["hint"]["scenario_name"] == "Hiring plan" and detail["hint"]["in_other_line"] is True and detail["hint"]["element_name"] == "Ada" and detail["hint"]["change_title"] == "Promote Ada"
    assert world.owner.get(f"{world.path}/changes/{data['second']['id']}").json()["edits"] != []


def test_a_scenarios_start_is_marked_changed_only_when_changes_before_its_branch_point_edit(database_url: str, stack: ExitStack) -> None:
    world = World(stack, database_url, "tle-restart")
    data = basic(world)
    a = data["ids"]["A"]
    scenario = world.scenario("What if", data["second"]["id"])
    other = world.scenario("Later", world.ok(world.line, "2026-06-01", "Later point", [])["id"])
    assert world.lines()["What if"]["start_changed_at"] is None

    def reset() -> None:
        with transaction_session(world.factory, RequestContext(organization_id=UUID(world.org))) as session:
            session.execute(text("UPDATE model_lines SET start_changed_at = NULL"))

    world.ok(world.line, "2026-02-01", "Same day, later entry", [])  # sorts after the branch change: the start is unchanged
    world.ok(world.line, "2026-09-01", "After", [])
    assert world.lines()["What if"]["start_changed_at"] is None
    inserted = world.ok(world.line, "2026-01-15", "Before", [update_node(a, description="x")])  # inserted before the branch point
    lines = world.lines()
    assert lines["What if"]["start_changed_at"] is not None and lines["Later"]["start_changed_at"] is not None
    reset()
    world.owner.patch(f"{world.path}/changes/{inserted['id']}", json={"expected_version": 1, "title": "Renamed only"})
    assert world.lines()["What if"]["start_changed_at"] is None  # a title does not change what the Scenario starts from
    world.owner.patch(f"{world.path}/changes/{inserted['id']}", json={"expected_version": 2, "edits": [update_node(a, description="y")]})
    assert world.lines()["What if"]["start_changed_at"] is not None  # content inside the prefix does
    reset()
    own = world.ok(scenario, "2026-03-01", "Own", [])
    assert world.lines()["Later"]["start_changed_at"] is None and world.lines()["What if"]["start_changed_at"] is None and own["line_id"] == scenario
    assert other and world.lines()["Later"]["branch_change_id"]


def test_members_write_scenarios_but_not_the_base_line(database_url: str, stack: ExitStack) -> None:
    world = World(stack, database_url, "tle-roles")
    data = basic(world)
    scenario = world.scenario("What if", data["second"]["id"])
    member = world.member()
    assert world.post(member, world.line, "2026-05-01", "Nope", []).status_code == 403
    base_change = data["second"]["id"]
    assert member.patch(f"{world.path}/changes/{base_change}", json={"expected_version": 1, "title": "x"}).status_code == 403
    assert member.delete(f"{world.path}/changes/{base_change}", params={"expected_version": 1}).status_code == 403
    created = world.post(member, scenario, "2026-03-01", "Member plan", [add_node(str(uuid4()), world.types["goal"], "Goal")])
    assert created.status_code == 201, created.text
    change = created.json()["id"]
    assert member.patch(f"{world.path}/changes/{change}", json={"expected_version": 1, "title": "Edited"}).json()["title"] == "Edited"
    assert member.get(f"{world.path}/changes/{base_change}").status_code == 200 and member.get(f"{world.path}/lines/{world.line}/changes").status_code == 200
    assert member.delete(f"{world.path}/changes/{change}", params={"expected_version": 2}).status_code == 204
    assert world.post(member, str(uuid4()), "2026-03-01", "x", []).status_code == 404
    admin_app, _ = join(world.application, world.owner, world.org, subject="tle-admin", email="tle-admin@example.com", role="admin")
    admin = stack.enter_context(TestClient(admin_app))
    login(admin)
    assert world.post(admin, world.line, "2026-05-01", "Admin edit", []).status_code == 201


def test_stale_versions_conflict_with_the_latest_version(database_url: str, stack: ExitStack) -> None:
    world = World(stack, database_url, "tle-stale")
    data = basic(world)
    change = data["second"]["id"]
    assert world.owner.patch(f"{world.path}/changes/{change}", json={"expected_version": 1, "title": "One"}).json()["version"] == 2
    stale = world.owner.patch(f"{world.path}/changes/{change}", json={"expected_version": 1, "title": "Two"})
    assert stale.status_code == 409 and stale.json()["detail"] == {"latest_version": 2}
    stale = world.owner.delete(f"{world.path}/changes/{change}", params={"expected_version": 1})
    assert stale.status_code == 409 and stale.json()["detail"] == {"latest_version": 2}
    assert world.changes()[-1]["title"] == "One"


def test_bad_input_is_refused_before_the_chain_is_checked(database_url: str, stack: ExitStack) -> None:
    world = World(stack, database_url, "tle-input")
    ok = add_node(str(uuid4()), world.types["goal"], "Goal")
    for body in (
        {"occurred_on": "2026-01-01", "title": "   "},
        {"occurred_on": "not-a-date", "title": "x"},
        {"title": "x"},
        {"occurred_on": "2026-01-01", "title": "x", "edits": [{"op": "explode", "element_id": str(uuid4()), "payload": {}}]},
        {"occurred_on": "2026-01-01", "title": "x", "edits": [{"op": "update_node", "payload": {"name": "No element"}}]},
        {"occurred_on": "2026-01-01", "title": "x", "edits": [{"op": "update_node", "element_id": str(uuid4()), "payload": {}}]},
        {"occurred_on": "2026-01-01", "title": "x", "edits": [{"op": "remove_node", "element_id": str(uuid4()), "payload": {"name": "x"}}]},
        {"occurred_on": "2026-01-01", "title": "x", "edits": [{"op": "add_node", "payload": {"node_type_id": world.types["goal"]}}]},
        {"occurred_on": "2026-01-01", "title": "x" * 201, "edits": [ok]},
    ):
        response = world.owner.post(f"{world.path}/lines/{world.line}/changes", json=body)
        assert response.status_code == 422, (body, response.text)
        assert "chain_broken" not in response.text
    change = world.ok(world.line, "2026-01-02", "Fine", [ok])
    for body in ({"expected_version": 1, "title": None}, {"expected_version": 1, "occurred_on": None}, {"expected_version": 1, "edits": None}, {"title": "no version"}):
        assert world.owner.patch(f"{world.path}/changes/{change['id']}", json=body).status_code == 422, body
    assert len(world.changes()) == 2


def test_audit_entries_carry_counts_and_never_names_or_text(database_url: str, stack: ExitStack) -> None:
    world = World(stack, database_url, "tle-audit")
    node = str(uuid4())
    created = world.ok(world.line, "2026-04-01", "Secret title", [add_node(node, world.types["goal"], "Secret node name", description="Secret description"), add_node(str(uuid4()), world.types["goal"], "Another secret")], note="Secret note")
    world.owner.patch(f"{world.path}/changes/{created['id']}", json={"expected_version": 1, "occurred_on": "2026-04-02", "title": "Secret retitle", "note": "Secret note two", "edits": [add_node(node, world.types["goal"], "Secret renamed")]})
    world.owner.delete(f"{world.path}/changes/{created['id']}", params={"expected_version": 2})
    items = [item for item in world.audit() if item["action"].startswith("change.")]
    assert [item["action"] for item in items][::-1] == ["change.created", "change.updated", "change.deleted"]
    by_action = {item["action"]: item for item in items}
    for item in items:
        assert item["target_type"] == "change" and item["target_id"] == created["id"]
        assert item["change_summary"]["model_id"] == world.model and item["change_summary"]["line_id"] == world.line and item["change_summary"]["change_id"] == created["id"]
    assert by_action["change.created"]["change_summary"]["occurred_on"] == "2026-04-01" and by_action["change.created"]["change_summary"]["edit_counts"] == {"add_node": 2}
    updated = by_action["change.updated"]["change_summary"]
    assert updated["fields"] == ["occurred_on", "title", "note", "edits"] and updated["previous_occurred_on"] == "2026-04-01" and updated["edit_counts"] == {"add_node": 1} and updated["previous_edit_counts"] == {"add_node": 2}
    assert by_action["change.deleted"]["change_summary"]["occurred_on"] == "2026-04-02"
    text_of_audit = json.dumps(items)
    assert "ecret" not in text_of_audit and "renamed" not in text_of_audit.lower()


def test_changes_per_line_are_limited_per_line(database_url: str, stack: ExitStack, monkeypatch) -> None:
    monkeypatch.setenv("LIMIT_CHANGES_PER_LINE", "3")
    world = World(stack, database_url, "tle-limit")
    data = basic(world)  # the initial change, "Start" and "Hire": the Base line is full
    refused = world.post(None, world.line, "2026-05-01", "One too many", [])
    assert refused.status_code == 409 and refused.json()["detail"] == {"reason": "limit_reached", "limit": "changes_per_line", "maximum": 3}
    assert world.owner.patch(f"{world.path}/changes/{data['second']['id']}", json={"expected_version": 1, "title": "Edits are not creations"}).status_code == 200
    scenario = world.scenario("Roomy", data["second"]["id"])
    assert all(world.post(None, scenario, "2026-03-01", f"S{n}", []).status_code == 201 for n in range(3))
    assert world.post(None, scenario, "2026-03-01", "S4", []).status_code == 409


def test_a_read_only_organization_reads_but_cannot_write_changes(database_url: str, stack: ExitStack) -> None:
    world = World(stack, database_url, "tle-readonly")
    data = basic(world)
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(text("UPDATE organizations SET subscription_access_state = 'canceled' WHERE id = :id"), {"id": world.org})
    engine.dispose()
    assert world.post(None, world.line, "2026-05-01", "Blocked", []).status_code == 403
    assert world.owner.patch(f"{world.path}/changes/{data['second']['id']}", json={"expected_version": 1, "title": "x"}).status_code == 403
    assert world.owner.delete(f"{world.path}/changes/{data['second']['id']}", params={"expected_version": 1}).status_code == 403
    assert len(world.changes()) == 3 and world.owner.get(f"{world.path}/changes/{data['second']['id']}").status_code == 200


def test_another_organization_cannot_read_or_write_changes(database_url: str, stack: ExitStack) -> None:
    world = World(stack, database_url, "tle-rls-a")
    data = basic(world)
    _, stranger, other_org, other_base = _tenant(stack, database_url, "tle-rls-b")
    change = data["second"]["id"]
    for client, path in ((stranger, world.path), (stranger, f"{other_base}/models/{world.model}")):
        assert client.post(f"{path}/lines/{world.line}/changes", json={"occurred_on": "2026-05-01", "title": "Injected"}).status_code == 404
        assert client.patch(f"{path}/changes/{change}", json={"expected_version": 1, "title": "Injected"}).status_code == 404
        assert client.delete(f"{path}/changes/{change}", params={"expected_version": 1}).status_code == 404
        assert client.get(f"{path}/changes/{change}").status_code == 404
    other_model = stranger.post(f"{other_base}/models", json={"name": "Mine"}).json()["id"]
    assert stranger.patch(f"{other_base}/models/{other_model}/changes/{change}", json={"expected_version": 1, "title": "x"}).status_code == 404  # a change of another Model
    assert stranger.post(f"{other_base}/models/{other_model}/lines/{world.line}/changes", json={"occurred_on": "2026-05-01", "title": "x"}).status_code == 404
    with transaction_session(world.factory, RequestContext(organization_id=UUID(other_org))) as session:
        foreign = {table: session.execute(text(f"SELECT count(*) FROM {table} WHERE organization_id = :id"), {"id": world.org}).scalar_one() for table in ("model_lines", "timeline_changes", "change_edits", "node_positions")}
    assert set(foreign.values()) == {0}, foreign
    assert [item["title"] for item in world.changes()][-1] == "Hire"


def test_the_model_lock_makes_a_write_wait_for_the_writer_before_it(database_url: str, stack: ExitStack) -> None:
    world = World(stack, database_url, "tle-lock")
    with ThreadPoolExecutor(1) as pool:
        with transaction_session(world.factory, RequestContext(organization_id=UUID(world.org))) as session:
            session.execute(select(TwinModel.id).where(TwinModel.id == UUID(world.model)).with_for_update()).all()
            future = pool.submit(world.post, None, world.line, "2026-05-01", "Waits", [])
            with pytest.raises(FutureTimeout):
                future.result(timeout=1.0)  # blocked on the Model row, not done
        assert future.result(timeout=15).status_code == 201


def test_two_concurrent_writes_cannot_together_break_the_chain(database_url: str, stack: ExitStack) -> None:
    """Each write is valid alone: one removes the change that adds a node, the other starts to use that node."""
    world = World(stack, database_url, "tle-race")
    outcomes = []
    for round_number in range(6):
        node = str(uuid4())
        adder = world.ok(world.line, f"2026-0{round_number + 1}-01", f"Adds {round_number}", [add_node(node, world.types["goal"], f"Goal {round_number}")])
        barrier = threading.Barrier(2)

        def remove() -> int:
            barrier.wait()
            return world.owner.delete(f"{world.path}/changes/{adder['id']}", params={"expected_version": 1}).status_code

        def use() -> int:
            barrier.wait()
            return world.post(None, world.line, f"2026-0{round_number + 1}-15", f"Uses {round_number}", [update_node(node, description="used")]).status_code

        with ThreadPoolExecutor(2) as pool:
            removed, used = pool.submit(remove), pool.submit(use)
            outcomes.append((removed.result(timeout=30), used.result(timeout=30)))
        state = world.owner.get(f"{world.path}/lines/{world.line}/state", params={"as_of": "2026-12-31"})
        assert state.status_code == 200, state.text  # the chain still replays
    assert all(pair in ((204, 422), (422, 201)) for pair in outcomes), outcomes


def test_the_change_routes_leave_other_lines_alone_when_the_chain_is_valid(database_url: str, stack: ExitStack) -> None:
    world = World(stack, database_url, "tle-isolated")
    data = basic(world)
    scenario = world.scenario("What if", data["second"]["id"])
    scenario_change = world.ok(scenario, "2026-03-01", "Scenario only", [add_node(str(uuid4()), world.types["goal"], "Scenario goal")])
    assert "Scenario goal" in names(world.state(scenario)) and "Scenario goal" not in names(world.state())
    world.ok(world.line, "2026-04-01", "Base later", [add_node(str(uuid4()), world.types["goal"], "Base goal")])
    assert "Base goal" not in names(world.state(scenario)) and scenario_change["line_id"] == scenario
    assert date.fromisoformat(scenario_change["occurred_on"]) == date(2026, 3, 1)
