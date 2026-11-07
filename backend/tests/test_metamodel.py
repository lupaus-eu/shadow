"""Metamodel editing: a Model owns its node and connection types (feature 6)."""
from contextlib import ExitStack

import pytest

from test_models_graph import _graph, _tenant, _types  # noqa: F401


@pytest.fixture
def stack():
    with ExitStack() as clients:
        yield clients


def test_types_can_be_added_changed_and_removed(database_url: str, stack: ExitStack) -> None:
    _, owner, _, base = _tenant(stack, database_url, "meta-types")
    model_id = owner.post(f"{base}/models", json={"name": "Twin"}).json()["id"]
    path = f"{base}/models/{model_id}"
    other_id = owner.post(f"{base}/models", json={"name": "Other"}).json()["id"]
    created = owner.post(f"{path}/node-types", json={"name": "Data center", "color": "#336699"})
    assert created.status_code == 201 and created.json()["key"] == "data_center"
    assert owner.post(f"{path}/node-types", json={"name": "data CENTER", "color": "#336699"}).status_code == 409
    assert owner.post(f"{path}/node-types", json={"name": "Bad", "color": "red"}).status_code == 422
    renamed = owner.patch(f"{path}/node-types/{created.json()['id']}", json={"expected_version": 1, "name": "Facility", "color": "#112233"})
    assert renamed.json()["name"] == "Facility" and renamed.json()["version"] == 2
    assert owner.patch(f"{path}/node-types/{created.json()['id']}", json={"expected_version": 1, "name": "X"}).status_code == 409
    link = owner.post(f"{path}/connection-types", json={"name": "Hosts", "style": "dashed", "source_end": "none", "target_end": "arrow"})
    assert link.status_code == 201 and link.json()["style"] == "dashed"
    # the types of one Model are not visible to another Model
    assert owner.patch(f"{base}/models/{other_id}/node-types/{created.json()['id']}", json={"expected_version": 2, "name": "Nope"}).status_code == 404
    graph = _graph(owner, base, model_id)
    assert len(graph["node_types"]) == 12 and len(graph["connection_types"]) == 10
    assert owner.delete(f"{path}/node-types/{created.json()['id']}", params={"expected_version": 2}).status_code == 204
    assert owner.delete(f"{path}/connection-types/{link.json()['id']}", params={"expected_version": 1}).status_code == 204


def test_allowed_connections_gate_the_graph_and_types_in_use_stay(database_url: str, stack: ExitStack) -> None:
    _, owner, _, base = _tenant(stack, database_url, "meta-rules")
    model_id = owner.post(f"{base}/models", json={"name": "Twin"}).json()["id"]
    path = f"{base}/models/{model_id}"
    site = owner.post(f"{path}/node-types", json={"name": "Site", "color": "#336699"}).json()
    hosts = owner.post(f"{path}/connection-types", json={"name": "Hosts"}).json()
    a = owner.post(f"{path}/nodes", json={"node_type_id": site["id"], "name": "Helsinki"}).json()
    b = owner.post(f"{path}/nodes", json={"node_type_id": site["id"], "name": "Tampere"}).json()
    link = {"connection_type_id": hosts["id"], "source_node_id": a["id"], "target_node_id": b["id"]}
    assert owner.post(f"{path}/connections", json=link).status_code == 422
    rule = {"connection_type_id": hosts["id"], "source_node_type_id": site["id"], "target_node_type_id": site["id"]}
    assert owner.post(f"{path}/allowed-connections", json=rule).status_code == 201
    assert owner.post(f"{path}/allowed-connections", json=rule).status_code == 409
    connection = owner.post(f"{path}/connections", json=link)
    assert connection.status_code == 201
    # in use: the node type, the connection type and the rule cannot be removed
    assert owner.delete(f"{path}/node-types/{site['id']}", params={"expected_version": 1}).status_code == 409
    assert owner.delete(f"{path}/connection-types/{hosts['id']}", params={"expected_version": 1}).status_code == 409
    assert owner.delete(f"{path}/allowed-connections", params=rule).status_code == 409
    owner.delete(f"{path}/connections/{connection.json()['id']}", params={"expected_version": 1})
    assert owner.delete(f"{path}/allowed-connections", params=rule).status_code == 204
    assert owner.delete(f"{path}/allowed-connections", params=rule).status_code == 404
