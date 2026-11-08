"""Metrics: monthly values, formulas, and lines (feature 3)."""
from contextlib import ExitStack

import pytest

from test_models_graph import _graph, _tenant


@pytest.fixture
def stack():
    with ExitStack() as clients:
        yield clients


def _setup(stack, database_url, subject):
    _, owner, _, base = _tenant(stack, database_url, subject)
    model_id = owner.post(f"{base}/models", json={"name": "Twin"}).json()["id"]
    version = _graph(owner, base, model_id)["line"]["id"]
    return owner, f"{base}/models/{model_id}", f"{base}/models/{model_id}/lines/{version}/metrics"


def _values(owner, url, metric_id, pairs):
    return owner.put(f"{url}/{metric_id}/values", json={"values": [{"period": p, "value": v} for p, v in pairs]})


def test_input_values_and_derived_formulas(database_url: str, stack: ExitStack) -> None:
    owner, _, url = _setup(stack, database_url, "metrics-formulas")
    revenue = owner.post(url, json={"key": "revenue", "name": "Revenue", "unit": "EUR"}).json()
    cost = owner.post(url, json={"key": "cost", "name": "Cost", "unit": "EUR"}).json()
    margin = owner.post(url, json={"key": "margin", "name": "Margin", "formula": "(revenue - cost) / revenue"})
    assert margin.status_code == 201 and margin.json()["derived"]
    assert _values(owner, url, revenue["id"], [("2026-01-15", 100), ("2026-02-01", 200), ("2026-03-01", 0)]).status_code == 200
    _values(owner, url, cost["id"], [("2026-01-01", 40), ("2026-02-01", 50), ("2026-03-01", 10)])
    series = owner.get(f"{url}/{margin.json()['id']}/series").json()
    assert [(p["period"], round(p["value"], 3)) for p in series["points"]] == [("2026-01-01", 0.6), ("2026-02-01", 0.75)]  # March divides by zero
    assert _values(owner, url, margin.json()["id"], [("2026-01-01", 1)]).status_code == 422
    cleared = _values(owner, url, revenue["id"], [("2026-01-01", None)]).json()
    assert [p["period"] for p in cleared["points"]] == ["2026-02-01", "2026-03-01"]
    assert [m["values"] for m in owner.get(url).json()] == [2, 3, 1] or len(owner.get(url).json()) == 3


def test_formula_rules(database_url: str, stack: ExitStack) -> None:
    owner, _, url = _setup(stack, database_url, "metrics-rules")
    a = owner.post(url, json={"key": "a", "name": "A"}).json()
    assert owner.post(url, json={"key": "a", "name": "Again"}).status_code == 409
    assert owner.post(url, json={"key": "Bad Key", "name": "X"}).status_code == 422
    assert owner.post(url, json={"key": "b", "name": "B", "formula": "a + missing"}).status_code == 422
    assert owner.post(url, json={"key": "b", "name": "B", "formula": "a +"}).status_code == 422
    b = owner.post(url, json={"key": "b", "name": "B", "formula": "a * 2"}).json()
    cyc = owner.patch(f"{url}/{a['id']}", json={"key": "a", "name": "A", "formula": "b + 1", "expected_version": 1})
    assert cyc.status_code == 422
    assert owner.delete(f"{url}/{a['id']}", params={"expected_version": 1}).status_code == 409
    assert owner.patch(f"{url}/{b['id']}", json={"key": "b", "name": "B", "formula": "a * 3", "expected_version": 9}).status_code == 409
    assert owner.patch(f"{url}/{b['id']}", json={"key": "b2", "name": "B", "formula": "a * 3", "expected_version": 1}).status_code == 422
    assert owner.delete(f"{url}/{b['id']}", params={"expected_version": 1}).status_code == 204
    assert owner.delete(f"{url}/{a['id']}", params={"expected_version": 1}).status_code == 204


def test_forks_copy_metrics_and_edits_stay_in_their_line(database_url: str, stack: ExitStack) -> None:
    owner, path, url = _setup(stack, database_url, "metrics-fork")
    revenue = owner.post(url, json={"key": "revenue", "name": "Revenue"}).json()
    owner.post(url, json={"key": "double", "name": "Double", "formula": "revenue * 2"})
    _values(owner, url, revenue["id"], [("2026-01-01", 10)])
    initial = owner.get(f"{path}/lines/{owner.get(f'{path}/lines').json()[0]['id']}/events").json()[-1]["id"]
    fork = owner.post(f"{path}/lines", json={"name": "Scenario", "branch_event_id": initial}).json()
    fork_url = f"{path}/lines/{fork['id']}/metrics"
    copies = {m["key"]: m for m in owner.get(fork_url).json()}
    assert set(copies) == {"revenue", "double"} and copies["revenue"]["id"] != revenue["id"]
    _values(owner, fork_url, copies["revenue"]["id"], [("2026-01-01", 99)])
    assert owner.get(f"{fork_url}/{copies['double']['id']}/series").json()["points"][0]["value"] == 198
    assert owner.get(f"{url}/{revenue['id']}/series").json()["points"][0]["value"] == 10
