"""Metamodel editing: a Model owns its node and connection types (feature 6)."""
from contextlib import ExitStack

import pytest

from test_models_graph import _add_node, _graph, _latest_event, _tenant, _types  # noqa: F401


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
    event = _latest_event(owner, path)["id"]
    a = _add_node(owner, path, event, site["id"], "Helsinki").json()
    b = _add_node(owner, path, event, site["id"], "Tampere").json()
    link = {"connection_type_id": hosts["id"], "source_node_id": a["id"], "target_node_id": b["id"]}
    refused = owner.post(f"{path}/events/{event}/connections", json=link)
    assert refused.status_code == 422 and refused.json()["detail"]["cause"] == "connection_not_allowed"
    rule = {"connection_type_id": hosts["id"], "source_node_type_id": site["id"], "target_node_type_id": site["id"]}
    assert owner.post(f"{path}/allowed-connections", json=rule).status_code == 201
    assert owner.post(f"{path}/allowed-connections", json=rule).status_code == 409
    connection = owner.post(f"{path}/events/{event}/connections", json=link)
    assert connection.status_code == 201
    # in use: the node type, the connection type and the rule cannot be removed
    assert owner.delete(f"{path}/node-types/{site['id']}", params={"expected_version": 1}).status_code == 409
    assert owner.delete(f"{path}/connection-types/{hosts['id']}", params={"expected_version": 1}).status_code == 409
    assert owner.delete(f"{path}/allowed-connections", params=rule).status_code == 409
    version = owner.get(f"{path}/events/{event}").json()["version"]
    owner.delete(f"{path}/events/{event}/connections/{connection.json()['id']}", params={"expected_version": version})
    assert owner.delete(f"{path}/allowed-connections", params=rule).status_code == 204
    assert owner.delete(f"{path}/allowed-connections", params=rule).status_code == 404
    assert owner.post(f"{path}/events/{event}/connections", json=link).status_code == 422  # the rule is gone


def test_types_used_by_any_event_stay_even_when_the_element_is_gone(database_url: str, stack: ExitStack) -> None:
    """ADR-0049: a type that an event of any line names cannot be deleted, whether or not a node of that type still exists."""
    _, owner, _, base = _tenant(stack, database_url, "meta-in-use")
    model_id = owner.post(f"{base}/models", json={"name": "Twin"}).json()["id"]
    path = f"{base}/models/{model_id}"
    line = owner.get(f"{path}/lines").json()[0]["id"]
    first = _latest_event(owner, path)["id"]
    node_type = lambda name, color: owner.post(f"{path}/node-types", json={"name": name, "color": color}).json()  # noqa: E731
    site, hall, unused, ghost = node_type("Site", "#336699"), node_type("Hall", "#336644"), node_type("Unused", "#336655"), node_type("Ghost", "#336666")
    hosts = owner.post(f"{path}/connection-types", json={"name": "Hosts"}).json()
    swaps = owner.post(f"{path}/connection-types", json={"name": "Swaps"}).json()
    free = owner.post(f"{path}/connection-types", json={"name": "Free"}).json()
    for kind, source, target in ((hosts, site, site), (swaps, site, site), (hosts, hall, hall)):
        assert owner.post(f"{path}/allowed-connections", json={"connection_type_id": kind["id"], "source_node_type_id": source["id"], "target_node_type_id": target["id"]}).status_code == 201
    a = _add_node(owner, path, first, site["id"], "A").json()
    b = _add_node(owner, path, first, site["id"], "B").json()
    d = _add_node(owner, path, first, unused["id"], "D").json()
    second = owner.post(f"{path}/lines/{line}/events", json={"occurred_on": "2099-01-01", "title": "Later", "changes": []}).json()
    version = lambda: owner.get(f"{path}/events/{second['id']}").json()["version"]  # noqa: E731
    assert owner.post(f"{path}/events/{second['id']}/connections", json={"connection_type_id": hosts["id"], "source_node_id": a["id"], "target_node_id": b["id"]}).status_code == 201
    # a node added and removed in one event leaves no trace, so its type can go
    c = _add_node(owner, path, second["id"], ghost["id"], "C").json()
    assert owner.delete(f"{path}/events/{second['id']}/nodes/{c['id']}", params={"expected_version": version()}).status_code == 204
    assert owner.delete(f"{path}/node-types/{ghost['id']}", params={"expected_version": 1}).status_code == 204
    # a later event retypes D: the update names hall, the earlier add still names unused
    assert owner.patch(f"{path}/events/{second['id']}/nodes/{d['id']}", json={"expected_version": version(), "node_type_id": hall["id"]}).status_code == 200
    assert owner.delete(f"{path}/node-types/{unused['id']}", params={"expected_version": 1}).status_code == 409
    assert owner.delete(f"{path}/node-types/{hall['id']}", params={"expected_version": 1}).status_code == 409
    assert owner.delete(f"{path}/node-types/{site['id']}", params={"expected_version": 1}).status_code == 409
    assert owner.delete(f"{path}/connection-types/{hosts['id']}", params={"expected_version": 1}).status_code == 409
    assert owner.delete(f"{path}/connection-types/{free['id']}", params={"expected_version": 1}).status_code == 204
    # a Scenario's own events count too, for the type and for the rule
    scenario = owner.post(f"{path}/lines", json={"name": "What if", "branch_event_id": second["id"]}).json()["id"]
    own = owner.post(f"{path}/lines/{scenario}/events", json={"occurred_on": "2099-02-01", "title": "Swap", "changes": []}).json()["id"]
    assert owner.post(f"{path}/events/{own}/connections", json={"connection_type_id": swaps["id"], "source_node_id": a["id"], "target_node_id": b["id"]}).status_code == 201
    assert owner.delete(f"{path}/connection-types/{swaps['id']}", params={"expected_version": 1}).status_code == 409
    rule = {"connection_type_id": swaps["id"], "source_node_type_id": site["id"], "target_node_type_id": site["id"]}
    assert owner.delete(f"{path}/allowed-connections", params=rule).status_code == 409  # only a Scenario event needs this rule
    spare = {"connection_type_id": hosts["id"], "source_node_type_id": hall["id"], "target_node_type_id": hall["id"]}
    assert owner.delete(f"{path}/allowed-connections", params=spare).status_code == 204  # no event connects halls
