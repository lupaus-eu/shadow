"""Forecast methods and simulation runs (feature 4)."""
from contextlib import ExitStack
from datetime import date

import pytest

from app.forecasting import InsufficientHistory, forecast
from app.metric_engine import add_months
from test_metrics import _setup, _values


@pytest.fixture
def stack():
    with ExitStack() as clients:
        yield clients


def _series(count, start=date(2024, 1, 1), f=lambda t: 100 + 10 * t):
    return {add_months(start, t): float(f(t)) for t in range(count)}


def test_linear_forecast_follows_the_trend_with_a_band() -> None:
    points = forecast(_series(12), "linear", date(2025, 6, 1))
    assert [p.period for p in points][:2] == [date(2025, 1, 1), date(2025, 2, 1)] and len(points) == 6
    assert points[0].value == pytest.approx(220) and points[-1].value == pytest.approx(270)
    assert points[0].lower <= points[0].value <= points[0].upper


def test_seasonal_forecast_repeats_the_yearly_shape_and_holt_extends_the_trend() -> None:
    shape = [0, 5, 10, 5, 0, -5, -10, -5, 0, 5, 10, 5]
    seasonal = forecast(_series(36, f=lambda t: 100 + 2 * t + shape[t % 12]), "seasonal", date(2027, 12, 1))
    assert len(seasonal) == 12 and seasonal[2].value - seasonal[0].value == pytest.approx(10 + 4, abs=0.5)
    holt = forecast(_series(12), "holt", date(2025, 3, 1))
    assert holt[-1].value == pytest.approx(240, abs=2)
    with pytest.raises(InsufficientHistory):
        forecast(_series(12), "seasonal", date(2026, 1, 1))
    with pytest.raises(InsufficientHistory):
        forecast(_series(2), "linear", date(2026, 1, 1))


def test_prophet_forecasts_with_a_band_and_needs_a_year_of_history() -> None:
    points = forecast(_series(24), "prophet", date(2026, 6, 1))
    assert len(points) == 6 and all(p.lower <= p.value <= p.upper for p in points)
    assert points[-1].value > points[0].value  # the rising trend continues
    with pytest.raises(InsufficientHistory):
        forecast(_series(8), "prophet", date(2025, 12, 1))


def test_gaps_are_interpolated() -> None:
    series = _series(10)
    del series[date(2024, 4, 1)]
    assert forecast(series, "linear", date(2025, 1, 1))[0].value == pytest.approx(200)


def test_a_run_forecasts_inputs_derives_the_rest_and_keeps_its_results(database_url: str, stack: ExitStack) -> None:
    owner, path, url = _setup(stack, database_url, "sim-run")
    revenue = owner.post(url, json={"key": "revenue", "name": "Revenue", "unit": "EUR"}).json()
    cost = owner.post(url, json={"key": "cost", "name": "Cost"}).json()
    owner.post(url, json={"key": "profit", "name": "Profit", "formula": "revenue - cost"})
    owner.post(url, json={"key": "empty", "name": "Empty"})
    _values(owner, url, revenue["id"], [(f"2025-{m:02d}-01", 100 + 10 * m) for m in range(1, 13)])
    _values(owner, url, cost["id"], [(f"2025-{m:02d}-01", 60 + 2 * m) for m in range(1, 13)])
    sims = f"{url.replace('/metrics', '')}/simulations"
    assert owner.post(sims, json={"name": "x", "adjustments": [{"metric_key": "nope", "change_pct": 5}]}).status_code == 422
    run = owner.post(sims, json={"name": "Base", "method": "linear", "horizon_months": 6, "adjustments": [{"metric_key": "cost", "change_pct": 10}]})
    assert run.status_code == 201, run.text
    result = run.json()
    assert result["simulation"]["history_end"] == "2025-12-01" and result["simulation"]["skipped"] == {"empty": "no_values"}
    by_key = {m["key"]: m for m in result["metrics"]}
    assert set(by_key) == {"revenue", "cost", "profit"} and by_key["profit"]["derived"]
    assert len(by_key["revenue"]["history"]) == 12 and len(by_key["revenue"]["forecast"]) == 6
    assert by_key["revenue"]["forecast"][0]["value"] == pytest.approx(230)
    assert by_key["cost"]["forecast"][0]["value"] == pytest.approx((60 + 2 * 13) * 1.1)
    assert by_key["profit"]["forecast"][0]["value"] == pytest.approx(230 - (60 + 26) * 1.1)
    assert by_key["profit"]["forecast"][0]["lower"] is None
    # editing the version afterwards does not change a finished run
    _values(owner, url, revenue["id"], [("2025-12-01", 9999)])
    again = owner.get(f"{sims}/{result['simulation']['id']}").json()
    assert {m["key"]: m for m in again["metrics"]}["revenue"]["forecast"][0]["value"] == pytest.approx(230)
    assert [s["name"] for s in owner.get(sims).json()] == ["Base"]
    assert owner.delete(f"{sims}/{result['simulation']['id']}").status_code == 204
    assert owner.get(sims).json() == []
