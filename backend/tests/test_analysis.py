"""Analysis findings and action proposals (feature 5)."""
from contextlib import ExitStack

import pytest

from test_metrics import _setup, _values


@pytest.fixture
def stack():
    with ExitStack() as clients:
        yield clients


def _world(stack, database_url, subject):
    owner, path, url = _setup(stack, database_url, subject)
    revenue = owner.post(url, json={"key": "revenue", "name": "Revenue", "unit": "EUR"}).json()
    cost = owner.post(url, json={"key": "cost", "name": "Cost", "unit": "EUR"}).json()
    owner.post(url, json={"key": "profit", "name": "Profit", "unit": "EUR", "formula": "revenue - cost"})
    _values(owner, url, revenue["id"], [(f"2025-{m:02d}-01", 200 - 3 * m) for m in range(1, 13)])
    _values(owner, url, cost["id"], [(f"2025-{m:02d}-01", 100 + 5 * m) for m in range(1, 13)])
    sims = f"{url.replace('/metrics', '')}/simulations"
    return owner, path, sims


def test_findings_and_proposals_name_their_numbers(database_url: str, stack: ExitStack) -> None:
    owner, path, sims = _world(stack, database_url, "analysis-rules")
    run = owner.post(sims, json={"name": "Trend", "horizon_months": 24}).json()["simulation"]["id"]
    api = f"{path}/simulations/{run}"
    analysis = owner.get(f"{api}/analysis").json()
    findings = {f["key"]: f for f in analysis["findings"]}
    assert findings["revenue"]["trend"] == "declining" and findings["cost"]["trend"] == "growing"
    assert findings["profit"]["turns_negative"] is not None
    assert analysis["recommendations"] == []  # nothing stored until generated
    generated = owner.post(f"{api}/analysis").json()["recommendations"]
    kinds = {(r["kind"], r["metric_key"]): r for r in generated}
    assert ("turns_negative", "profit") in kinds and ("decline", "revenue") in kinds and ("growth", "cost") in kinds
    negative = kinds[("turns_negative", "profit")]
    assert negative["severity"] == "high" and "Main drivers" in negative["rationale"] and "Revenue" in negative["rationale"]
    assert generated[0]["severity"] == "high"
    # accepted proposals survive a regeneration; the rest are refreshed
    accepted = owner.patch(f"{api}/recommendations/{negative['id']}", json={"status": "accepted", "expected_version": 1}).json()
    assert accepted["status"] == "accepted" and accepted["version"] == 2
    assert owner.patch(f"{api}/recommendations/{negative['id']}", json={"status": "dismissed", "expected_version": 1}).status_code == 409
    again = {(r["kind"], r["metric_key"]): r for r in owner.post(f"{api}/analysis").json()["recommendations"]}
    assert again[("turns_negative", "profit")]["status"] == "accepted" and len(again) == len(kinds)


def test_comparing_a_scenario_with_the_baseline_run(database_url: str, stack: ExitStack) -> None:
    owner, path, sims = _world(stack, database_url, "analysis-compare")
    baseline = owner.post(sims, json={"name": "Baseline run", "horizon_months": 12}).json()["simulation"]["id"]
    scenario = owner.post(sims, json={"name": "Cost cut", "horizon_months": 12, "adjustments": [{"metric_key": "cost", "change_pct": -30}]}).json()["simulation"]["id"]
    api = f"{path}/simulations/{scenario}"
    compared = owner.post(f"{api}/analysis", params={"compare_to": baseline}).json()
    assert compared["compared_to"]["name"] == "Baseline run"
    findings = {f["key"]: f for f in compared["findings"]}
    assert findings["cost"]["versus"] == pytest.approx(-0.3, abs=0.01) and findings["profit"]["versus"] > 0.05
    assert any(r["kind"] == "scenario_gain" and r["metric_key"] == "profit" and "cost -30 %" in r["rationale"] for r in compared["recommendations"])
    assert owner.get(f"{api}/analysis", params={"compare_to": "00000000-0000-0000-0000-000000000000"}).status_code == 404


class FakeAI:
    def __init__(self, answer: str) -> None:
        self.answer, self.calls = answer, []

    def complete(self, system: str, prompt: str) -> str:
        self.calls.append((system, prompt))
        return self.answer


def _ai_world(stack, database_url, subject, ai):
    from test_models_graph import _graph, _tenant

    _, owner, _, base = _tenant(stack, database_url, subject, ai_client=ai)
    model_id = owner.post(f"{base}/models", json={"name": "Twin"}).json()["id"]
    path = f"{base}/models/{model_id}"
    url = f"{path}/versions/{_graph(owner, base, model_id)['version']['id']}/metrics"
    revenue = owner.post(url, json={"key": "revenue", "name": "Revenue", "unit": "EUR"}).json()
    _values(owner, url, revenue["id"], [(f"2025-{m:02d}-01", 200 - 3 * m) for m in range(1, 13)])
    run = owner.post(f"{url.replace('/metrics', '')}/simulations", json={"name": "Trend", "horizon_months": 12}).json()["simulation"]["id"]
    return owner, f"{path}/simulations/{run}"


def test_ai_analysis_is_stored_next_to_the_rule_based_proposals(database_url: str, stack: ExitStack) -> None:
    answer = '```json\n{"summary": "Revenue falls steadily.", "proposals": [{"metric_key": "revenue", "severity": "high", "title": "Protect revenue", "rationale": "Down 18 %."}, {"metric_key": "ghost", "severity": "low", "title": "Unknown metric", "rationale": "x"}]}\n```'
    ai = FakeAI(answer)
    owner, api = _ai_world(stack, database_url, "analysis-ai", ai)
    assert owner.get(f"{api}/analysis").json()["ai_available"] is True
    owner.post(f"{api}/analysis")  # the rule-based proposals
    result = owner.post(f"{api}/analysis/ai", json={"language": "fi"})
    assert result.status_code == 200
    body = result.json()
    assert body["ai_summary"] == "Revenue falls steadily." and body["ai_generated_at"]
    kinds = {(r["kind"], r["metric_key"]) for r in body["recommendations"]}
    assert ("ai", "revenue") in kinds and ("decline", "revenue") in kinds and ("ai", "ghost") not in kinds
    assert "Finnish" in ai.calls[0][0] and '"revenue"' in ai.calls[0][1]
    # decisions survive a new AI run, and regenerating the rules leaves the AI proposals alone
    proposal = next(r for r in body["recommendations"] if r["kind"] == "ai")
    owner.patch(f"{api}/recommendations/{proposal['id']}", json={"status": "accepted", "expected_version": proposal["version"]})
    ai.answer = '{"summary": "Second.", "proposals": [{"metric_key": "revenue", "severity": "low", "title": "Changed", "rationale": "y"}]}'
    owner.post(f"{api}/analysis/ai", json={})
    owner.post(f"{api}/analysis")
    after = owner.get(f"{api}/analysis").json()
    kept = next(r for r in after["recommendations"] if r["kind"] == "ai")
    assert kept["status"] == "accepted" and kept["title"] == "Protect revenue" and after["ai_summary"] == "Second."


def test_ai_analysis_fails_cleanly(database_url: str, stack: ExitStack) -> None:
    owner, api = _ai_world(stack, database_url, "analysis-ai-bad", FakeAI("no json here"))
    assert owner.post(f"{api}/analysis/ai", json={}).status_code == 502
    assert owner.get(f"{api}/analysis").json()["ai_summary"] is None
    owner, api = _ai_world(stack, database_url, "analysis-ai-off", None)
    assert owner.get(f"{api}/analysis").json()["ai_available"] is False
    assert owner.post(f"{api}/analysis/ai", json={}).status_code == 503
