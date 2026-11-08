"""Reading lines, events and the state after an event or on a date (model-timeline ticket 03)."""
from contextlib import ExitStack
from datetime import date
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.database import RequestContext, create_session_factory, transaction_session
from app.models import EventChange, ModelLine, NodePosition, TimelineEvent
from test_invitations import join, login
from test_models_graph import _graph, _tenant, _types


@pytest.fixture
def stack():
    with ExitStack() as clients:
        yield clients


def _event(session, organization_id, model_id, line_id, day, title, changes, event_id=None):
    event = TimelineEvent(id=event_id or uuid4(), organization_id=organization_id, model_id=model_id, line_id=line_id, occurred_on=day, title=title)
    session.add(event)
    session.flush()
    for position, (op, element, payload) in enumerate(changes):
        session.add(EventChange(id=uuid4(), organization_id=organization_id, event_id=event.id, position=position, op=op, element_id=element, payload=payload))
    session.flush()
    return event


def _seed(stack: ExitStack, database_url: str, subject: str):
    """Base line: initial (A, B, A-B), 2026-06-01 (rename A, add C), same day (describe C), 2026-07-30 (drop B), 2026-09-01 (add D).

    The test clock is 2026-07-30 09:00 UTC, so the last event is planned. Scenario "What if" branches from the 2026-06-01 event.
    """
    application, owner, organization_id, base = _tenant(stack, database_url, subject)
    model_id = owner.post(f"{base}/models", json={"name": "Timeline"}).json()["id"]
    types = _types(_graph(owner, base, model_id))
    base_line = UUID(owner.get(f"{base}/models/{model_id}/lines").json()[0]["id"])
    ids = {name: uuid4() for name in "ABCDE"} | {"AB": uuid4()}
    factory = create_session_factory(application.state.database_engine)
    org, model = UUID(organization_id), UUID(model_id)
    with transaction_session(factory, RequestContext(organization_id=org)) as session:
        initial = session.get(TimelineEvent, session.execute(text("SELECT id FROM timeline_events WHERE line_id = :l"), {"l": base_line}).scalar_one())
        initial.occurred_on = date(2026, 1, 1)
        session.add_all(
            [
                EventChange(id=uuid4(), organization_id=org, event_id=initial.id, position=0, op="add_node", element_id=ids["A"], payload={"node_type_id": types["product"], "name": "App", "description": "The product", "x": 10, "y": 20}),
                EventChange(id=uuid4(), organization_id=org, event_id=initial.id, position=1, op="add_node", element_id=ids["B"], payload={"node_type_id": types["journey"], "name": "Onboarding", "x": 30, "y": 40}),
                EventChange(id=uuid4(), organization_id=org, event_id=initial.id, position=2, op="add_connection", element_id=ids["AB"], payload={"connection_type_id": types["c:features_in"], "source_node_id": str(ids["A"]), "target_node_id": str(ids["B"])}),
            ]
        )
        session.flush()
        e2 = _event(session, org, model, base_line, date(2026, 6, 1), "Growth", [("update_node", ids["A"], {"name": "App 2"}), ("add_node", ids["C"], {"node_type_id": types["person"], "name": "Ada", "x": 1, "y": 2})])
        _event(session, org, model, base_line, date(2026, 6, 1), "Same day", [("update_node", ids["C"], {"description": "late"})])
        _event(session, org, model, base_line, date(2026, 7, 30), "Today", [("remove_node", ids["B"], {})])
        _event(session, org, model, base_line, date(2026, 9, 1), "Planned", [("add_node", ids["D"], {"node_type_id": types["product"], "name": "Future", "x": 3, "y": 4})])
        scenario = ModelLine(id=uuid4(), organization_id=org, model_id=model, name="What if", kind="scenario", parent_line_id=base_line, branch_event_id=e2.id)
        session.add(scenario)
        session.flush()
        _event(session, org, model, scenario.id, date(2026, 8, 1), "Try E", [("add_node", ids["E"], {"node_type_id": types["product"], "name": "Experiment", "x": 5, "y": 6})])
        session.add_all(
            [
                NodePosition(line_id=base_line, node_id=ids["A"], organization_id=org, model_id=model, x=50, y=60),
                NodePosition(line_id=base_line, node_id=ids["B"], organization_id=org, model_id=model, x=7, y=8),
                NodePosition(line_id=scenario.id, node_id=ids["A"], organization_id=org, model_id=model, x=100, y=200),
            ]
        )
    return {"application": application, "owner": owner, "org": organization_id, "base": base, "model": model_id, "path": f"{base}/models/{model_id}", "line": str(base_line), "scenario": str(scenario.id), "ids": {key: str(value) for key, value in ids.items()}, "types": types, "e2": str(e2.id)}


def _names(state: dict) -> set[str]:
    return {node["name"] for node in state["nodes"]}


def _event_by_title(seed: dict, line: str, title: str) -> str:
    return next(item["id"] for item in seed["owner"].get(f"{seed['path']}/lines/{line}/events").json() if item["title"] == title)


def test_lines_are_listed_with_event_counts_and_the_base_line_first(database_url: str, stack: ExitStack) -> None:
    seed = _seed(stack, database_url, "tl-read-lines")
    lines = seed["owner"].get(f"{seed['path']}/lines").json()
    assert [(item["kind"], item["name"], item["event_count"]) for item in lines] == [("base", "Baseline", 5), ("scenario", "What if", 1)]
    assert lines[0]["id"] == seed["line"] and lines[0]["parent_line_id"] is None and lines[0]["latest_event_date"] == "2026-09-01"
    assert lines[1]["parent_line_id"] == seed["line"] and lines[1]["branch_event_id"] == seed["e2"] and lines[1]["latest_event_date"] == "2026-08-01"
    assert {"start_changed_at", "version", "created_at", "description", "created_by_user_account_id"} <= set(lines[0])


def test_events_are_listed_in_order_with_planned_flag_counts_and_branches(database_url: str, stack: ExitStack) -> None:
    seed = _seed(stack, database_url, "tl-read-events")
    events = seed["owner"].get(f"{seed['path']}/lines/{seed['line']}/events").json()
    assert [(item["title"], item["occurred_on"], item["planned"]) for item in events] == [
        ("Initial situation", "2026-01-01", False),
        ("Growth", "2026-06-01", False),
        ("Same day", "2026-06-01", False),
        ("Today", "2026-07-30", False),
        ("Planned", "2026-09-01", True),
    ]
    assert events[0]["change_count"] == 3 and events[0]["change_counts"] == {"add_connection": 1, "add_node": 2}
    assert events[1]["branches"] == [{"line_id": seed["scenario"], "name": "What if"}] and events[0]["branches"] == []
    scenario_events = seed["owner"].get(f"{seed['path']}/lines/{seed['scenario']}/events").json()
    assert [(item["title"], item["planned"]) for item in scenario_events] == [("Try E", True)]


def test_the_state_after_the_initial_event_is_the_original_graph_and_events_show_what_they_changed(database_url: str, stack: ExitStack) -> None:
    seed = _seed(stack, database_url, "tl-read-state")
    owner, path, line, ids = seed["owner"], seed["path"], seed["line"], seed["ids"]
    initial = _event_by_title(seed, line, "Initial situation")
    state = owner.get(f"{path}/lines/{line}/state", params={"event_id": initial}).json()
    assert _names(state) == {"App", "Onboarding"} and len(state["connections"]) == 1
    assert {"nodes", "connections", "node_types", "connection_types", "allowed_connections", "line", "event", "planned", "positions", "added", "updated", "removed"} <= set(state)
    assert len(state["node_types"]) == 11 and len(state["connection_types"]) == 9 and len(state["allowed_connections"]) == 14
    app = next(node for node in state["nodes"] if node["id"] == ids["A"])
    assert (app["x"], app["y"], app["description"]) == (50, 60, "The product")  # the line's position wins over the added one
    assert {item["node"]["name"] for item in state["added"]["nodes"]} == {"App", "Onboarding"} and len(state["added"]["connections"]) == 1
    assert state["updated"] == {"nodes": [], "connections": []} and state["removed"] == {"nodes": [], "connections": []}
    assert state["event"]["title"] == "Initial situation" and state["planned"] is False and state["line"]["id"] == line

    growth = owner.get(f"{path}/lines/{line}/state", params={"event_id": _event_by_title(seed, line, "Growth")}).json()
    assert _names(growth) == {"App 2", "Onboarding", "Ada"}
    assert [item["node"]["name"] for item in growth["added"]["nodes"]] == ["Ada"]
    assert [(item["node"]["name"], item["previous"]["name"]) for item in growth["updated"]["nodes"]] == [("App 2", "App")]

    today = owner.get(f"{path}/lines/{line}/state", params={"event_id": _event_by_title(seed, line, "Today")}).json()
    assert _names(today) == {"App 2", "Ada"} and today["connections"] == []
    assert [item["node"]["name"] for item in today["removed"]["nodes"]] == ["Onboarding"]  # removed elements keep their data
    assert today["removed"]["nodes"][0]["node"]["id"] == ids["B"] and today["removed"]["nodes"][0]["node"]["x"] == 7
    assert [item["connection"]["id"] for item in today["removed"]["connections"]] == [ids["AB"]]


def test_present_state_ignores_planned_events_but_a_planned_state_can_be_read(database_url: str, stack: ExitStack) -> None:
    seed = _seed(stack, database_url, "tl-read-planned")
    owner, path, line = seed["owner"], seed["path"], seed["line"]
    present = owner.get(f"{path}/lines/{line}/state").json()
    assert _names(present) == {"App 2", "Ada"} and present["event"]["title"] == "Today" and present["planned"] is False and present["as_of"] == "2026-07-30"
    planned = owner.get(f"{path}/lines/{line}/state", params={"event_id": _event_by_title(seed, line, "Planned")}).json()
    assert _names(planned) == {"App 2", "Ada", "Future"} and planned["planned"] is True and planned["event"]["planned"] is True and planned["as_of"] is None


def test_as_of_picks_the_last_event_of_that_day_or_earlier(database_url: str, stack: ExitStack) -> None:
    seed = _seed(stack, database_url, "tl-read-asof")
    owner, path, line = seed["owner"], seed["path"], seed["line"]

    def at(day: str) -> dict:
        response = owner.get(f"{path}/lines/{line}/state", params={"as_of": day})
        assert response.status_code == 200, response.text
        return response.json()

    assert at("2026-01-01")["event"]["title"] == "Initial situation" and _names(at("2026-05-31")) == {"App", "Onboarding"}
    same_day = at("2026-06-01")
    assert same_day["event"]["title"] == "Same day" and _names(same_day) == {"App 2", "Onboarding", "Ada"}  # entry order breaks the tie
    assert next(node for node in same_day["nodes"] if node["name"] == "Ada")["description"] == "late"
    assert at("2026-07-29")["event"]["title"] == "Same day" and at("2026-07-30")["event"]["title"] == "Today"
    assert at("2026-09-01")["event"]["title"] == "Planned" and at("2026-09-01")["planned"] is True
    before_everything = at("2025-12-31")
    assert before_everything["event"] is None and before_everything["nodes"] == [] and before_everything["planned"] is False
    assert before_everything["added"] == {"nodes": [], "connections": []} and before_everything["as_of"] == "2025-12-31"


def test_a_scenario_state_has_its_parents_history_and_positions_fall_back_to_the_parent_line(database_url: str, stack: ExitStack) -> None:
    seed = _seed(stack, database_url, "tl-read-scenario")
    owner, path, scenario, ids = seed["owner"], seed["path"], seed["scenario"], seed["ids"]
    present = owner.get(f"{path}/lines/{scenario}/state").json()  # its own event is planned, so the present state is the branch point
    assert present["event"] is None and _names(present) == {"App 2", "Onboarding", "Ada"} and len(present["connections"]) == 1
    positions = {item["node_id"]: (item["x"], item["y"]) for item in present["positions"]}
    assert positions == {ids["A"]: (100, 200), ids["B"]: (7, 8), ids["C"]: (1, 2)}  # scenario, then parent line, then where it was added
    own = owner.get(f"{path}/lines/{scenario}/state", params={"event_id": _event_by_title(seed, scenario, "Try E")}).json()
    assert _names(own) == {"App 2", "Onboarding", "Ada", "Experiment"} and own["planned"] is True
    assert [item["node"]["name"] for item in own["added"]["nodes"]] == ["Experiment"] and own["line"]["kind"] == "scenario"
    base_state = owner.get(f"{path}/lines/{seed['line']}/state", params={"event_id": seed["e2"]}).json()
    assert next(node for node in base_state["nodes"] if node["id"] == ids["A"])["x"] == 50  # the scenario's drawing does not move the base


def test_bad_requests_name_what_is_wrong(database_url: str, stack: ExitStack) -> None:
    seed = _seed(stack, database_url, "tl-read-errors")
    owner, path, line = seed["owner"], seed["path"], seed["line"]
    event = _event_by_title(seed, line, "Growth")
    assert owner.get(f"{path}/lines/{line}/state", params={"event_id": event, "as_of": "2026-06-01"}).status_code == 422
    assert owner.get(f"{path}/lines/{line}/state", params={"as_of": "not-a-date"}).status_code == 422
    assert owner.get(f"{path}/lines/{line}/state", params={"event_id": str(uuid4())}).status_code == 404
    assert owner.get(f"{path}/lines/{seed['scenario']}/state", params={"event_id": event}).status_code == 404  # an event of another line
    assert owner.get(f"{path}/lines/{uuid4()}/state").status_code == 404 and owner.get(f"{path}/lines/{uuid4()}/events").status_code == 404
    assert owner.get(f"{seed['base']}/models/{uuid4()}/lines").status_code == 404


def test_today_follows_the_organization_time_zone(database_url: str, stack: ExitStack) -> None:
    seed = _seed(stack, database_url, "tl-read-zone")
    owner, path, line = seed["owner"], seed["path"], seed["line"]
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(text("UPDATE organizations SET time_zone = 'Pacific/Honolulu' WHERE id = :id"), {"id": seed["org"]})
    try:  # 09:00 UTC on 2026-07-30 is still the 29th in Honolulu: the event dated the 30th has not happened yet
        events = {item["title"]: item["planned"] for item in owner.get(f"{path}/lines/{line}/events").json()}
        assert events["Today"] is True and events["Same day"] is False
        present = owner.get(f"{path}/lines/{line}/state").json()
        assert present["event"]["title"] == "Same day" and present["as_of"] == "2026-07-29"
    finally:
        engine.dispose()


def test_members_read_every_line_and_another_organization_gets_404(database_url: str, stack: ExitStack) -> None:
    seed = _seed(stack, database_url, "tl-read-roles")
    application, owner, base, path = seed["application"], seed["owner"], seed["base"], seed["path"]
    member_app, _ = join(application, owner, seed["org"], subject="tl-read-member", email="tl-read-member@example.com")
    member = stack.enter_context(TestClient(member_app))
    login(member)
    assert len(member.get(f"{path}/lines").json()) == 2
    for line in (seed["line"], seed["scenario"]):
        assert member.get(f"{path}/lines/{line}/events").status_code == 200 and member.get(f"{path}/lines/{line}/state").status_code == 200
    _, stranger, _, other_base = _tenant(stack, database_url, "tl-read-stranger")
    for url in (f"{path}/lines", f"{path}/lines/{seed['line']}/events", f"{path}/lines/{seed['line']}/state"):
        assert stranger.get(url).status_code == 404, url  # not a member of that Organization
    model = seed["model"]
    for url in (f"{other_base}/models/{model}/lines", f"{other_base}/models/{model}/lines/{seed['line']}/events", f"{other_base}/models/{model}/lines/{seed['line']}/state"):
        assert stranger.get(url).status_code == 404, url  # a member of another Organization, a model of this one


def test_a_read_only_organization_can_still_read_its_timeline(database_url: str, stack: ExitStack) -> None:
    seed = _seed(stack, database_url, "tl-read-readonly")
    owner, base, path = seed["owner"], seed["base"], seed["path"]
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(text("UPDATE organizations SET subscription_access_state = 'read_only' WHERE id = :id"), {"id": seed["org"]})
    try:
        assert owner.post(f"{base}/models", json={"name": "Blocked"}).status_code in (402, 403, 409)
        assert owner.get(f"{path}/lines").status_code == 200
        assert owner.get(f"{path}/lines/{seed['line']}/events").status_code == 200
        assert owner.get(f"{path}/lines/{seed['line']}/state").status_code == 200
    finally:
        engine.dispose()
