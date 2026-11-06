"""Model versions: the baseline, forks, and the changes against the base (feature 2)."""
from contextlib import ExitStack

import pytest

from test_models_graph import _graph, _tenant, _types  # noqa: F401


@pytest.fixture
def stack():
    with ExitStack() as clients:
        yield clients


def test_a_model_has_a_baseline_and_forks_copy_its_graph(database_url: str, stack: ExitStack) -> None:
    _, owner, _, base = _tenant(stack, database_url, "versions-fork")
    model_id = owner.post(f"{base}/models", json={"name": "Twin"}).json()["id"]
    path = f"{base}/models/{model_id}"
    types = _types(_graph(owner, base, model_id))
    a = owner.post(f"{path}/nodes", json={"node_type_id": types["product"], "name": "App"}).json()
    b = owner.post(f"{path}/nodes", json={"node_type_id": types["journey"], "name": "Onboarding"}).json()
    owner.post(f"{path}/connections", json={"connection_type_id": types["c:features_in"], "source_node_id": a["id"], "target_node_id": b["id"]})
    baseline = _graph(owner, base, model_id)["version"]
    assert baseline["is_baseline"] and baseline["name"] == "Baseline"
    fork = owner.post(f"{path}/versions", json={"name": "Growth plan"})
    assert fork.status_code == 201 and fork.json()["base_version_id"] == baseline["id"]
    assert owner.post(f"{path}/versions", json={"name": "growth PLAN"}).status_code == 409
    forked = owner.get(path, params={"version_id": fork.json()["id"]}).json()
    assert {n["name"] for n in forked["nodes"]} == {"App", "Onboarding"} and len(forked["connections"]) == 1
    assert {n["id"] for n in forked["nodes"]}.isdisjoint({a["id"], b["id"]})
    assert len(forked["versions"]) == 2
    assert owner.get(f"{path}/versions/{fork.json()['id']}/changes").json()["added_nodes"] == []


def test_changes_list_added_removed_and_changed(database_url: str, stack: ExitStack) -> None:
    _, owner, _, base = _tenant(stack, database_url, "versions-diff")
    model_id = owner.post(f"{base}/models", json={"name": "Twin"}).json()["id"]
    path = f"{base}/models/{model_id}"
    types = _types(_graph(owner, base, model_id))
    a = owner.post(f"{path}/nodes", json={"node_type_id": types["product"], "name": "App"}).json()
    owner.post(f"{path}/nodes", json={"node_type_id": types["journey"], "name": "Onboarding"})
    version_id = owner.post(f"{path}/versions", json={"name": "What if"}).json()["id"]
    forked = owner.get(path, params={"version_id": version_id}).json()
    by_name = {n["name"]: n for n in forked["nodes"]}
    assert owner.patch(f"{path}/nodes/{by_name['App']['id']}", json={"expected_version": 1, "name": "App 2"}).status_code == 200
    assert owner.delete(f"{path}/nodes/{by_name['Onboarding']['id']}", params={"expected_version": 1}).status_code == 204
    added = owner.post(f"{path}/nodes", json={"version_id": version_id, "node_type_id": types["goal"], "name": "Grow"}).json()
    other = owner.post(f"{path}/nodes", json={"version_id": version_id, "node_type_id": types["product"], "name": "Extra"}).json()
    # connections cannot join nodes of different versions
    assert owner.post(f"{path}/connections", json={"connection_type_id": types["c:features_in"], "source_node_id": other["id"], "target_node_id": a["id"]}).status_code == 422
    changes = owner.get(f"{path}/versions/{version_id}/changes").json()
    assert [n["name"] for n in changes["added_nodes"]] == ["Grow", "Extra"] or {n["name"] for n in changes["added_nodes"]} == {"Grow", "Extra"}
    assert [n["name"] for n in changes["removed_nodes"]] == ["Onboarding"]
    assert [(n["name"], n["fields"]) for n in changes["changed_nodes"]] == [("App 2", ["name"])]
    assert added["id"]
    # the baseline stayed untouched
    assert [n["name"] for n in _graph(owner, base, model_id)["nodes"]] == ["App", "Onboarding"]


def test_baseline_rules_and_deleting_versions(database_url: str, stack: ExitStack) -> None:
    _, owner, _, base = _tenant(stack, database_url, "versions-delete")
    model_id = owner.post(f"{base}/models", json={"name": "Twin"}).json()["id"]
    path = f"{base}/models/{model_id}"
    baseline = _graph(owner, base, model_id)["version"]
    assert owner.delete(f"{path}/versions/{baseline['id']}", params={"expected_version": 1}).status_code == 422
    assert owner.patch(f"{path}/versions/{baseline['id']}", json={"name": "Other", "expected_version": 1}).status_code == 422
    first = owner.post(f"{path}/versions", json={"name": "One"}).json()
    second = owner.post(f"{path}/versions", json={"name": "Two", "base_version_id": first["id"]}).json()
    assert owner.delete(f"{path}/versions/{first['id']}", params={"expected_version": 1}).status_code == 409
    renamed = owner.patch(f"{path}/versions/{second['id']}", json={"name": "Two b", "expected_version": 1})
    assert renamed.json()["version"] == 2
    assert owner.delete(f"{path}/versions/{second['id']}", params={"expected_version": 1}).status_code == 409
    assert owner.delete(f"{path}/versions/{second['id']}", params={"expected_version": 2}).status_code == 204
    assert owner.delete(f"{path}/versions/{first['id']}", params={"expected_version": 1}).status_code == 204
    assert [v["name"] for v in owner.get(f"{path}/versions").json()] == ["Baseline"]
