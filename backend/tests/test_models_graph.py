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


def _tenant(stack: ExitStack, database_url: str, subject: str):
    verifier = Verifier()
    application = create_app(database_url=database_url, oidc_client=OIDC(subject, f"{subject}@example.com"), stripe_billing=Stripe(), stripe_webhook_verifier=verifier, clock=lambda: NOW)
    client = stack.enter_context(TestClient(application))
    login(client)
    organization_id = active_org(client, verifier, seats=3)
    return application, client, organization_id, f"/api/v1/organizations/{organization_id}"


def _graph(client: TestClient, base: str, model_id: str) -> dict:
    return client.get(f"{base}/models/{model_id}").json()


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
    product = owner.post(f"{path}/nodes", json={"node_type_id": types["product"], "name": "App", "x": 10, "y": 20})
    journey = owner.post(f"{path}/nodes", json={"node_type_id": types["journey"], "name": "Onboarding"})
    person = owner.post(f"{path}/nodes", json={"node_type_id": types["person"], "name": "Ada"})
    assert product.status_code == journey.status_code == person.status_code == 201
    ids = {"product": product.json()["id"], "journey": journey.json()["id"], "person": person.json()["id"]}
    features = types["c:features_in"]
    ok = owner.post(f"{path}/connections", json={"connection_type_id": features, "source_node_id": ids["product"], "target_node_id": ids["journey"]})
    assert ok.status_code == 201
    assert owner.post(f"{path}/connections", json={"connection_type_id": features, "source_node_id": ids["product"], "target_node_id": ids["journey"]}).status_code == 409
    assert owner.post(f"{path}/connections", json={"connection_type_id": features, "source_node_id": ids["person"], "target_node_id": ids["journey"]}).status_code == 422
    assert owner.post(f"{path}/connections", json={"connection_type_id": features, "source_node_id": ids["product"], "target_node_id": ids["product"]}).status_code == 422
    assert len(_graph(owner, base, model_id)["connections"]) == 1


def test_stale_versions_conflict_moves_are_quiet_and_deleting_a_node_removes_its_connections(database_url: str, stack: ExitStack) -> None:
    application, owner, organization_id, base = _tenant(stack, database_url, "models-versions")
    model_id = owner.post(f"{base}/models", json={"name": "Versions"}).json()["id"]
    types = _types(_graph(owner, base, model_id))
    path = f"{base}/models/{model_id}"
    a = owner.post(f"{path}/nodes", json={"node_type_id": types["product"], "name": "A"}).json()
    b = owner.post(f"{path}/nodes", json={"node_type_id": types["journey"], "name": "B"}).json()
    owner.post(f"{path}/connections", json={"connection_type_id": types["c:features_in"], "source_node_id": a["id"], "target_node_id": b["id"]})
    moved = owner.patch(f"{path}/nodes/{a['id']}", json={"expected_version": 1, "x": 5, "y": 6})
    assert moved.status_code == 200 and moved.json()["version"] == 2
    assert owner.patch(f"{path}/nodes/{a['id']}", json={"expected_version": 1, "name": "Late"}).status_code == 409
    renamed = owner.patch(f"{path}/nodes/{a['id']}", json={"expected_version": 2, "name": "Renamed"})
    assert renamed.json()["name"] == "Renamed" and renamed.json()["version"] == 3
    actions = [item["action"] for item in owner.get(f"{base}/audit-events", params={"limit": 100}).json()["items"]]
    assert actions.count("node.updated") == 1  # the move is not audited, the rename is
    assert owner.delete(f"{path}/nodes/{a['id']}", params={"expected_version": 1}).status_code == 409
    assert owner.delete(f"{path}/nodes/{a['id']}", params={"expected_version": 3}).status_code == 204
    assert _graph(owner, base, model_id)["connections"] == []


def test_members_edit_the_graph_but_only_managers_manage_models(database_url: str, stack: ExitStack) -> None:
    application, owner, organization_id, base = _tenant(stack, database_url, "models-roles")
    model = owner.post(f"{base}/models", json={"name": "Shared"}).json()
    member_app, _ = join(application, owner, organization_id, subject="models-member", email="models-member@example.com")
    member = stack.enter_context(TestClient(member_app))
    login(member)
    types = _types(_graph(member, base, model["id"]))
    assert member.post(f"{base}/models/{model['id']}/nodes", json={"node_type_id": types["team"], "name": "Platform"}).status_code == 201
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
    owner.post(f"{base}/models/{model_id}/nodes", json={"node_type_id": types["goal"], "name": "Secret goal"})
    assert stranger.get(f"{other_base}/models").json() == []
    assert stranger.get(f"{other_base}/models/{model_id}").status_code == 404
    assert stranger.get(f"{base}/models").status_code == 404 and stranger.get(f"{base}/models/{model_id}").status_code == 404
    assert stranger.post(f"{other_base}/models/{model_id}/nodes", json={"node_type_id": types["goal"], "name": "Injected"}).status_code == 404
    factory = create_session_factory(application.state.database_engine)
    tables = ("models", "node_types", "connection_types", "allowed_connections", "nodes", "connections")
    with transaction_session(factory, RequestContext(organization_id=other_id)) as session:
        foreign = {table: session.execute(text(f"SELECT count(*) FROM {table} WHERE organization_id = :id"), {"id": organization_id}).scalar_one() for table in tables}
    with transaction_session(factory, RequestContext()) as session:
        anonymous = {table: session.execute(text(f"SELECT count(*) FROM {table}")).scalar_one() for table in tables}
    assert set(foreign.values()) == {0}, foreign
    assert set(anonymous.values()) == {0}, anonymous
