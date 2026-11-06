"""Rule-based analysis of a simulation and the action proposals it leads to (Shadow feature 5).

``analyze`` reads a finished simulation (optionally with a second one to compare against, for
example the baseline) and returns one finding per metric and a list of proposals. The rules
are deliberately plain and explainable: each proposal names the numbers it rests on.
"""

from dataclasses import dataclass, field
from datetime import date

from app.simulation_routes import MetricResult, SimulationResult

DECLINE = -0.10
GROWTH = 0.15
STABLE = 0.05
WIDE_BAND = 0.5
SCENARIO_GAIN = 0.05


@dataclass
class Finding:
    key: str
    name: str
    unit: str | None
    derived: bool
    start: float | None
    end: float | None
    change_pct: float | None
    trend: str
    turns_negative: date | None = None
    band_ratio: float | None = None
    versus: float | None = None


@dataclass
class Proposal:
    kind: str
    severity: str
    metric_key: str
    title: str
    rationale: str


@dataclass
class Analysis:
    findings: list[Finding] = field(default_factory=list)
    proposals: list[Proposal] = field(default_factory=list)


def _fmt(value: float, unit: str | None) -> str:
    text = f"{value:,.2f}".rstrip("0").rstrip(".").replace(",", " ")
    return f"{text} {unit}" if unit else text


def _finding(metric: MetricResult) -> Finding | None:
    if not metric.forecast:
        return None
    start = metric.history[-1].value if metric.history else None
    last = metric.forecast[-1]
    change = (last.value - start) / abs(start) if start not in (None, 0) else None
    trend = "unknown" if change is None else "declining" if change <= DECLINE else "growing" if change >= GROWTH else "stable" if abs(change) < STABLE else ("down" if change < 0 else "up")
    negative = next((point.period for point in metric.forecast if point.value < 0), None) if (start is None or start >= 0) else None
    band = (last.upper - last.lower) / abs(last.value) if last.lower is not None and last.upper is not None and last.value else None
    return Finding(metric.key, metric.name, metric.unit, metric.derived, start, last.value, change, trend, negative, band)


def _drivers(metric: MetricResult, findings: dict[str, Finding], formulas: dict[str, str]) -> str:
    """The inputs a derived metric reads, with their own change, largest move first."""
    formula = formulas.get(metric.key)
    if not formula:
        return ""
    moves = sorted(((abs(item.change_pct), item) for key, item in findings.items() if not item.derived and key in formula and item.change_pct is not None), key=lambda pair: -pair[0])
    return ", ".join(f"{item.name} {item.change_pct * 100:+.0f} %" for _, item in moves[:3])


def analyze(result: SimulationResult, formulas: dict[str, str] | None = None, compare: SimulationResult | None = None) -> Analysis:
    formulas = formulas or {}
    analysis = Analysis()
    findings = {finding.key: finding for metric in result.metrics if (finding := _finding(metric))}
    other = {finding.key: finding for metric in (compare.metrics if compare else []) if (finding := _finding(metric))}
    months = result.simulation.horizon_months
    for metric in result.metrics:
        finding = findings.get(metric.key)
        if finding is None:
            continue
        if finding.key in other and other[finding.key].end not in (None, 0) and finding.end is not None:
            finding.versus = (finding.end - other[finding.key].end) / abs(other[finding.key].end)  # type: ignore[operator]
        analysis.findings.append(finding)
        numbers = f"{_fmt(finding.start, finding.unit)} → {_fmt(finding.end, finding.unit)}" if finding.start is not None and finding.end is not None else ""
        driver = _drivers(metric, findings, formulas)
        if finding.turns_negative:
            analysis.proposals.append(Proposal("turns_negative", "high", finding.key, f"Prevent {finding.name} turning negative", f"The forecast of {finding.name} goes below zero from {finding.turns_negative:%Y-%m}. {numbers}.{f' Main drivers: {driver}.' if driver else ''}"))
        elif finding.trend == "declining" and finding.change_pct is not None:
            analysis.proposals.append(Proposal("decline", "high" if finding.change_pct <= 2 * DECLINE else "medium", finding.key, f"Address the decline of {finding.name}", f"{finding.name} falls {abs(finding.change_pct) * 100:.0f} % over {months} months ({numbers}).{f' Main drivers: {driver}.' if driver else ''} Find out what drives it and plan a counter-measure."))
        elif finding.trend == "growing" and finding.change_pct is not None:
            analysis.proposals.append(Proposal("growth", "low", finding.key, f"Prepare for the growth of {finding.name}", f"{finding.name} grows {finding.change_pct * 100:.0f} % over {months} months ({numbers}). Check that capacity and dependent metrics keep up."))
        if finding.band_ratio is not None and finding.band_ratio >= WIDE_BAND and not finding.derived:
            analysis.proposals.append(Proposal("uncertain", "low", finding.key, f"Reduce the uncertainty of {finding.name}", f"The 95 % band at the end of the horizon is {finding.band_ratio * 100:.0f} % of the forecast value. Add more history or review the assumptions."))
        if finding.versus is not None and finding.versus >= SCENARIO_GAIN:
            changes = ", ".join(f"{item.metric_key} {item.change_pct:+.0f} %" for item in result.simulation.adjustments)
            analysis.proposals.append(Proposal("scenario_gain", "medium", finding.key, f"Adopt the changes behind {result.simulation.name}", f"Compared with {compare.simulation.name if compare else 'the other run'}, {finding.name} ends {finding.versus * 100:.0f} % higher.{f' Changes in this run: {changes}.' if changes else ''}"))
    order = {"high": 0, "medium": 1, "low": 2}
    analysis.proposals.sort(key=lambda proposal: (order[proposal.severity], proposal.metric_key))
    return analysis
