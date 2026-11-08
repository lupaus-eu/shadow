"""Models and their graph: tenant ownership, the default metamodel, and graph rules (feature 1)."""
from contextlib import ExitStack

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.database import RequestContext, create_session_factory, transaction_session
from app.main import create_app
from test_invitations import NOW, OIDC, Stripe, Verifier, active_org, join, login


@pytest.fixture
def stack():
    with ExitStack() as clients:
        yield clients


def _tenant(stack: ExitStack, database_url: str, subject: str, **app_kwargs):
    verifier = Verifier()
    application = create_app(database_url=database_url, oidc_client=OIDC(subject, f"{subject}@example.com"), stripe_billing=Stripe(), stripe_webhook_verifier=verifier, clock=lambda: NOW, **app_kwargs)
    client = stack.enter_context(TestClient(application))
    login(client)
    organization_id = active_org(client, verifier, seats=3)
    return application, client, organization_id, f"/api/v1/organizations/{organization_id}"


def _graph(client: TestClient, base: str, model_id: str) -> dict:
    return client.get(f"{base}/models/{model_id}").json()


def _latest_event(client: TestClient, path: str, line_id: str | None = None) -> dict:
    """The last event of the Base line (or the given line): the event canvas edits and the old node routes' successors write into."""
    line = line_id or client.get(f"{path}/lines").json()[0]["id"]
    return client.get(f"{path}/lines/{line}/events").json()[-1]


def _event_version(client: TestClient, path: str, event_id: str) -> int:
    return client.get(f"{path}/events/{event_id}").json()["version"]


def _add_node(client: TestClient, path: str, event_id: str, node_type_id: str, name: str, **extra):
    return client.post(f"{path}/events/{event_id}/nodes", json={"node_type_id": node_type_id, "name": name, **extra})


def _types(graph: dict) -> dict[str, str]:
    return {item["key"]: item["id"] for item in graph["node_types"]} | {f"c:{item['key']}": item["id"] for item in graph["connection_types"]}


def test_a_new_model_starts_with_the_default_metamodel(database_url: str, stack: ExitStack) -> None:
    _, owner, _, base = _tenant(stack, database_url, "models-default")
    created = owner.post(f"{base}/models", json={"name": "  Acme   Oy ", "description": "Twin"})
    assert created.status_code == 201 and created.json()["name"] == "Acme Oy"
    graph = _graph(owner, base, created.json()["id"])
    assert len(graph["node_types"]) == 11 and len(graph["connection_types"]) == 9 and len(graph["allowed_connections"]) == 14
    assert graph["nodes"] == [] and graph["connections"] == []
    assert owner.post(f"{base}/models", json={"name": "acme oy"}).status_code == 409
    assert [item["name"] for item in owner.get(f"{base}/models").json()] == ["Acme Oy"]


def test_nodes_and_connections_follow_the_metamodel(database_url: str, stack: ExitStack) -> None:
    _, owner, _, base = _tenant(stack, database_url, "models-graph")
    model_id = owner.post(f"{base}/models", json={"name": "Graph"}).json()["id"]
    types = _types(_graph(owner, base, model_id))
    path = f"{base}/models/{model_id}"
    event = _latest_event(owner, path)["id"]
    product = _add_node(owner, path, event, types["product"], "App", x=10, y=20)
    journey = _add_node(owner, path, event, types["journey"], "Onboarding")
    person = _add_node(owner, path, event, types["person"], "Ada")
    assert product.status_code == journey.status_code == person.status_code == 201
    ids = {"product": product.json()["id"], "journey": journey.json()["id"], "person": person.json()["id"]}
    features = types["c:features_in"]
    connect = lambda source, target: owner.post(f"{path}/events/{event}/connections", json={"connection_type_id": features, "source_node_id": ids[source], "target_node_id": ids[target]})  # noqa: E731
    assert connect("product", "journey").status_code == 201
    causes = {name: connect(*ends) for name, ends in {"duplicate": ("product", "journey"), "not_allowed": ("person", "journey"), "self": ("product", "product")}.items()}
    assert {name: (response.status_code, response.json()["detail"]["reason"], response.json()["detail"]["cause"]) for name, response in causes.items()} == {
        "duplicate": (422, "chain_broken", "duplicate_connection"),
        "not_allowed": (422, "chain_broken", "connection_not_allowed"),
        "self": (422, "chain_broken", "self_connection"),
    }
    line = owner.get(f"{path}/lines").json()[0]["id"]
    assert len(owner.get(f"{path}/lines/{line}/state", params={"event_id": event}).json()["connections"]) == 1
    assert len(_graph(owner, base, model_id)["connections"]) == 1  # the model route reads the same replayed state


def test_stale_events_conflict_moves_are_quiet_and_deleting_a_node_removes_its_connections(database_url: str, stack: ExitStack) -> None:
    application, owner, organization_id, base = _tenant(stack, database_url, "models-versions")
    model_id = owner.post(f"{base}/models", json={"name": "Versions"}).json()["id"]
    types = _types(_graph(owner, base, model_id))
    path = f"{base}/models/{model_id}"
    line = owner.get(f"{path}/lines").json()[0]["id"]
    event = _latest_event(owner, path)["id"]
    a = _add_node(owner, path, event, types["product"], "A").json()
    b = _add_node(owner, path, event, types["journey"], "B").json()
    assert owner.post(f"{path}/events/{event}/connections", json={"connection_type_id": types["c:features_in"], "source_node_id": a["id"], "target_node_id": b["id"]}).status_code == 201
    version = _event_version(owner, path, event)
    assert version == 4
    moved = owner.put(f"{path}/lines/{line}/positions", json=[{"node_id": a["id"], "x": 5, "y": 6}])
    assert moved.status_code == 200 and _event_version(owner, path, event) == version  # a move is a position, not an edit
    assert owner.patch(f"{path}/events/{event}/nodes/{a['id']}", json={"expected_version": version - 1, "name": "Late"}).status_code == 409
    renamed = owner.patch(f"{path}/events/{event}/nodes/{a['id']}", json={"expected_version": version, "name": "Renamed"})
    assert renamed.status_code == 200 and renamed.json()["node"]["name"] == "Renamed" and renamed.json()["node"]["x"] == 5 and renamed.json()["event"]["version"] == version + 1
    actions = [item["action"] for item in owner.get(f"{base}/audit-events", params={"limit": 100}).json()["items"]]
    assert actions.count("event.updated") == 4 and "node.updated" not in actions  # the edits are audited as event updates, the move is not
    assert owner.delete(f"{path}/events/{event}/nodes/{a['id']}", params={"expected_version": version}).status_code == 409
    assert owner.delete(f"{path}/events/{event}/nodes/{a['id']}", params={"expected_version": version + 1}).status_code == 204
    assert owner.get(f"{path}/lines/{line}/state", params={"event_id": event}).json()["connections"] == []


def test_members_edit_scenarios_but_only_managers_edit_the_base_line_and_manage_models(database_url: str, stack: ExitStack) -> None:
    application, owner, organization_id, base = _tenant(stack, database_url, "models-roles")
    model = owner.post(f"{base}/models", json={"name": "Shared"}).json()
    member_app, _ = join(application, owner, organization_id, subject="models-member", email="models-member@example.com")
    member = stack.enter_context(TestClient(member_app))
    login(member)
    path = f"{base}/models/{model['id']}"
    types = _types(_graph(member, base, model["id"]))
    initial = _latest_event(member, path)["id"]
    assert _add_node(member, path, initial, types["team"], "Platform").status_code == 403
    assert _add_node(owner, path, initial, types["team"], "Platform").status_code == 201
    scenario = member.post(f"{path}/lines", json={"name": "What if", "branch_event_id": initial})
    assert scenario.status_code == 201
    own = member.post(f"{path}/lines/{scenario.json()['id']}/events", json={"occurred_on": "2099-01-01", "title": "Hire", "changes": []})
    assert own.status_code == 201
    assert _add_node(member, path, own.json()["id"], types["person"], "Ada").status_code == 201
    assert member.post(f"{base}/models", json={"name": "Nope"}).status_code == 403
    assert member.patch(f"{base}/models/{model['id']}", json={"name": "Renamed", "expected_version": 1}).status_code == 403
    assert member.delete(f"{base}/models/{model['id']}", params={"expected_version": 1}).status_code == 403
    assert owner.patch(f"{base}/models/{model['id']}", json={"name": "Renamed", "expected_version": 1}).json()["version"] == 2
    assert owner.delete(f"{base}/models/{model['id']}", params={"expected_version": 2}).status_code == 204
    assert owner.get(f"{base}/models/{model['id']}").status_code == 404


def test_another_organization_cannot_see_or_reach_a_model(database_url: str, stack: ExitStack) -> None:
    application, owner, organization_id, base = _tenant(stack, database_url, "models-owner-a")
    other_app, stranger, other_id, other_base = _tenant(stack, database_url, "models-owner-b")
    model_id = owner.post(f"{base}/models", json={"name": "Private"}).json()["id"]
    types = _types(_graph(owner, base, model_id))
    path = f"{base}/models/{model_id}"
    event = _latest_event(owner, path)["id"]
    _add_node(owner, path, event, types["goal"], "Secret goal")
    assert stranger.get(f"{other_base}/models").json() == []
    assert stranger.get(f"{other_base}/models/{model_id}").status_code == 404
    assert stranger.get(f"{base}/models").status_code == 404 and stranger.get(f"{base}/models/{model_id}").status_code == 404
    assert _add_node(stranger, f"{other_base}/models/{model_id}", event, types["goal"], "Injected").status_code == 404
    assert _add_node(stranger, path, event, types["goal"], "Injected").status_code == 404
    factory = create_session_factory(application.state.database_engine)
    tables = ("models", "node_types", "connection_types", "allowed_connections", "model_lines", "timeline_events", "event_changes", "node_positions")
    with transaction_session(factory, RequestContext(organization_id=other_id)) as session:
        foreign = {table: session.execute(text(f"SELECT count(*) FROM {table} WHERE organization_id = :id"), {"id": organization_id}).scalar_one() for table in tables}
    with transaction_session(factory, RequestContext()) as session:
        anonymous = {table: session.execute(text(f"SELECT count(*) FROM {table}")).scalar_one() for table in tables}
    assert set(foreign.values()) == {0}, foreign
    assert set(anonymous.values()) == {0}, anonymous
