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


def test_the_analysis_has_a_summary_slot_and_no_llm_route(database_url: str, stack: ExitStack) -> None:
    owner, path, sims = _world(stack, database_url, "analysis-no-ai")
    run = owner.post(sims, json={"name": "Trend", "horizon_months": 12}).json()["simulation"]["id"]
    api = f"{path}/simulations/{run}"
    body = owner.get(f"{api}/analysis").json()
    assert body["summary"] is None and body["summary_at"] is None and body["summary_author"] is None
    assert not [key for key in body if key.startswith("ai_")]
    assert owner.post(f"{api}/analysis/ai", json={}).status_code in (404, 405)


def test_a_person_writes_a_summary_and_one_proposal_per_metric(database_url: str, stack: ExitStack) -> None:
    owner, path, sims = _world(stack, database_url, "analysis-write")
    run = owner.post(sims, json={"name": "Trend", "horizon_months": 12}).json()["simulation"]["id"]
    api = f"{path}/simulations/{run}"
    summary = owner.put(f"{api}/analysis/summary", json={"text": "  Revenue falls.  "})
    assert summary.status_code == 200 and summary.json()["summary"] == "Revenue falls." and summary.json()["summary_author"] and summary.json()["summary_at"]
    assert not summary.json()["summary_author"].startswith("agent:")
    assert owner.put(f"{api}/analysis/summary", json={"text": ""}).status_code == 422
    assert owner.put(f"{api}/analysis/summary", json={"text": "x" * 4001}).status_code == 422
    body = {"title": "Protect revenue", "rationale": "Down 18 %.", "severity": "high"}
    first = owner.put(f"{api}/analysis/proposals/revenue", json=body)
    assert first.status_code == 200 and first.json()["kind"] == "agent" and first.json()["status"] == "proposed"
    assert owner.put(f"{api}/analysis/proposals/ghost", json=body).status_code == 404
    assert owner.put(f"{api}/analysis/proposals/revenue", json={**body, "severity": "urgent"}).status_code == 422
    assert owner.put(f"{api}/analysis/proposals/revenue", json={**body, "title": ""}).status_code == 422
    # a decision survives regenerating the rules; a repeat replaces the proposal and asks for a new decision
    owner.patch(f"{api}/recommendations/{first.json()['id']}", json={"status": "accepted", "expected_version": 1})
    owner.post(f"{api}/analysis")
    kept = [r for r in owner.get(f"{api}/analysis").json()["recommendations"] if r["kind"] == "agent"]
    assert len(kept) == 1 and kept[0]["status"] == "accepted" and kept[0]["title"] == "Protect revenue"
    again = owner.put(f"{api}/analysis/proposals/revenue", json={**body, "title": "Changed"}).json()
    assert again["id"] == first.json()["id"] and again["title"] == "Changed" and again["status"] == "proposed" and again["version"] == 3
    assert len([r for r in owner.get(f"{api}/analysis").json()["recommendations"] if r["kind"] == "agent"]) == 1
    workbook = owner.get(f"{api}/analysis/export")
    assert workbook.status_code == 200
    from io import BytesIO

    from openpyxl import load_workbook

    book = load_workbook(BytesIO(workbook.content))
    rows = {row[0]: row[1] for row in book["Summary"].iter_rows(values_only=True) if row[0]}
    assert rows["Summary"] == "Revenue falls." and rows["Summary written by"]
    assert "agent" in [row[2] for row in book["Proposals"].iter_rows(values_only=True)]


def test_the_writing_routes_audit_without_text(database_url: str, stack: ExitStack) -> None:
    from sqlalchemy import text

    from test_models_graph import _tenant  # noqa: F401

    application, owner, organization_id, base = _tenant(stack, database_url, "analysis-audit")
    from test_models_graph import _graph

    model_id = owner.post(f"{base}/models", json={"name": "Twin"}).json()["id"]
    path = f"{base}/models/{model_id}"
    url = f"{path}/lines/{_graph(owner, base, model_id)['line']['id']}/metrics"
    metric = owner.post(url, json={"key": "revenue", "name": "Revenue"}).json()
    _values(owner, url, metric["id"], [(f"2025-{m:02d}-01", 100 + m) for m in range(1, 13)])
    run = owner.post(f"{url.replace('/metrics', '')}/simulations", json={"name": "Trend", "horizon_months": 6}).json()["simulation"]["id"]
    api = f"{path}/simulations/{run}"
    owner.put(f"{api}/analysis/summary", json={"text": "DISTINCTIVE-SUMMARY-TEXT"})
    owner.put(f"{api}/analysis/proposals/revenue", json={"title": "DISTINCTIVE-TITLE", "rationale": "r", "severity": "low"})
    with application.state.database_engine.connect() as connection:
        rows = connection.execute(text("SELECT action, change_summary::text FROM audit_events WHERE organization_id = :org AND action LIKE 'analysis.%'"), {"org": organization_id}).all()
    actions = {row[0] for row in rows}
    assert {"analysis.summary_set", "analysis.proposal_set"} <= actions
    assert not any("DISTINCTIVE" in row[1] for row in rows)
