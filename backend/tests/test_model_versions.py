"""Model versions: the baseline and forks, until the line picker replaces them (feature 2).

A fork is a Scenario line with the id of the version; it shows the base's graph. The changes and merge routes
of ADR-0045 were removed in model-timeline ticket 07 (ADR-0050 replaces merge).
"""
from contextlib import ExitStack

import pytest

from test_models_graph import _add_node, _graph, _latest_event, _tenant, _types  # noqa: F401


@pytest.fixture
def stack():
    with ExitStack() as clients:
        yield clients


def test_a_model_has_a_baseline_and_forks_start_from_its_graph(database_url: str, stack: ExitStack) -> None:
    _, owner, _, base = _tenant(stack, database_url, "versions-fork")
    model_id = owner.post(f"{base}/models", json={"name": "Twin"}).json()["id"]
    path = f"{base}/models/{model_id}"
    types = _types(_graph(owner, base, model_id))
    event = _latest_event(owner, path)["id"]
    a = _add_node(owner, path, event, types["product"], "App").json()
    b = _add_node(owner, path, event, types["journey"], "Onboarding").json()
    owner.post(f"{path}/events/{event}/connections", json={"connection_type_id": types["c:features_in"], "source_node_id": a["id"], "target_node_id": b["id"]})
    baseline = _graph(owner, base, model_id)["version"]
    assert baseline["is_baseline"] and baseline["name"] == "Baseline"
    fork = owner.post(f"{path}/versions", json={"name": "Growth plan"})
    assert fork.status_code == 201 and fork.json()["base_version_id"] == baseline["id"]
    assert owner.post(f"{path}/versions", json={"name": "growth PLAN"}).status_code == 409
    forked = owner.get(path, params={"version_id": fork.json()["id"]}).json()
    assert {n["name"] for n in forked["nodes"]} == {"App", "Onboarding"} and len(forked["connections"]) == 1
    assert {n["id"] for n in forked["nodes"]} == {a["id"], b["id"]}  # element ids are the same in every line
    assert len(forked["versions"]) == 2
    # The fork's line has no events yet; its first edit goes into an event of its own and leaves the base alone.
    own = owner.post(f"{path}/lines/{fork.json()['id']}/events", json={"occurred_on": "2099-01-01", "title": "Edits", "changes": []}).json()["id"]
    assert _add_node(owner, path, own, types["goal"], "Grow").status_code == 201
    assert {n["name"] for n in owner.get(path, params={"version_id": fork.json()["id"]}).json()["nodes"]} == {"App", "Onboarding", "Grow"}
    assert [n["name"] for n in _graph(owner, base, model_id)["nodes"]] == ["App", "Onboarding"]
    assert _graph(owner, base, model_id)["latest_event"]["id"] == event
    assert owner.get(f"{path}/versions/{fork.json()['id']}/changes").status_code == 404  # removed with ticket 07
    assert owner.post(f"{path}/versions/{fork.json()['id']}/merge", json={"expected_version": 1}).status_code == 404


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
