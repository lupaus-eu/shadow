"""The graph of a line through GET /models/{id}, and the version routes that no longer exist (model-timeline ticket 08)."""
from contextlib import ExitStack

import pytest
from sqlalchemy import create_engine, text

from test_models_graph import _add_node, _graph, _latest_change, _tenant, _types


@pytest.fixture
def stack():
    with ExitStack() as clients:
        yield clients


def test_the_model_shows_its_lines_and_the_graph_of_the_chosen_line(database_url: str, stack: ExitStack) -> None:
    _, owner, _, base = _tenant(stack, database_url, "graph-lines")
    model_id = owner.post(f"{base}/models", json={"name": "Twin"}).json()["id"]
    path = f"{base}/models/{model_id}"
    types = _types(_graph(owner, base, model_id))
    change = _latest_change(owner, path)["id"]
    a = _add_node(owner, path, change, types["product"], "App").json()
    b = _add_node(owner, path, change, types["journey"], "Onboarding").json()
    owner.post(f"{path}/changes/{change}/connections", json={"connection_type_id": types["c:features_in"], "source_node_id": a["id"], "target_node_id": b["id"]})
    graph = _graph(owner, base, model_id)
    assert graph["line"]["kind"] == "base" and graph["line"]["name"] == "Baseline" and [line["id"] for line in graph["lines"]] == [graph["line"]["id"]]
    assert graph["model"]["base_line_id"] == graph["line"]["id"]
    assert {key for key in graph} >= {"model", "line", "lines", "nodes", "connections", "latest_change"} and "versions" not in graph
    scenario = owner.post(f"{path}/lines", json={"name": "Growth plan", "branch_change_id": change})
    assert scenario.status_code == 201 and owner.post(f"{path}/lines", json={"name": "growth PLAN", "branch_change_id": change}).status_code == 409
    forked = owner.get(path, params={"line_id": scenario.json()["id"]}).json()
    assert [line["name"] for line in forked["lines"]] == ["Baseline", "Growth plan"] and forked["line"]["id"] == scenario.json()["id"]
    assert {n["name"] for n in forked["nodes"]} == {"App", "Onboarding"} and len(forked["connections"]) == 1
    assert {n["id"] for n in forked["nodes"]} == {a["id"], b["id"]}  # element ids are the same in every line
    assert forked["latest_change"] is None  # the Scenario has no changes of its own yet
    own = owner.post(f"{path}/lines/{scenario.json()['id']}/changes", json={"occurred_on": "2099-01-01", "title": "Edits", "edits": []}).json()["id"]
    assert _add_node(owner, path, own, types["goal"], "Grow").status_code == 201
    assert {n["name"] for n in owner.get(path, params={"line_id": scenario.json()["id"]}).json()["nodes"]} == {"App", "Onboarding", "Grow"}
    assert [n["name"] for n in _graph(owner, base, model_id)["nodes"]] == ["App", "Onboarding"]
    assert owner.get(path, params={"line_id": "00000000-0000-0000-0000-000000000000"}).status_code == 404


def test_the_version_routes_are_gone_and_a_new_model_has_no_version_rows(database_url: str, stack: ExitStack) -> None:
    _, owner, _, base = _tenant(stack, database_url, "graph-no-versions")
    model_id = owner.post(f"{base}/models", json={"name": "Twin"}).json()["id"]
    path = f"{base}/models/{model_id}"
    line = _graph(owner, base, model_id)["line"]["id"]
    assert owner.get(f"{path}/versions").status_code == 404
    assert owner.post(f"{path}/versions", json={"name": "One"}).status_code == 404
    assert owner.patch(f"{path}/versions/{line}", json={"name": "Two", "expected_version": 1}).status_code == 404
    assert owner.delete(f"{path}/versions/{line}", params={"expected_version": 1}).status_code == 404
    engine = create_engine(database_url)
    with engine.connect() as connection:
        tables = {row[0] for row in connection.execute(text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'"))}
    engine.dispose()
    assert not tables & {"model_versions", "nodes", "connections"}
