"""Metric series of a line of a Model: stored monthly values and values derived by formula."""

from datetime import date
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.formulas import FormulaError, evaluate_formula, parse_formula
from app.models import Metric, MetricValue

Series = dict[date, float]


def add_months(period: date, months: int) -> date:
    index = period.year * 12 + period.month - 1 + months
    return date(index // 12, index % 12 + 1, 1)


def month_start(value: date) -> date:
    return date(value.year, value.month, 1)


def formula_order(metrics: dict[str, Metric]) -> list[str]:
    """Keys of the derived metrics in an order where every formula comes after what it reads.

    Raises ``FormulaError`` for an unknown reference or a cycle."""
    deps: dict[str, tuple[str, ...]] = {}
    for key, metric in metrics.items():
        if metric.formula:
            parsed = parse_formula(metric.formula)
            unknown = [name for name in parsed.identifiers if name not in metrics]
            if unknown:
                raise FormulaError(f"Unknown metric key: {', '.join(unknown)}.")
            deps[key] = parsed.identifiers
    ordered: list[str] = []
    state: dict[str, int] = {}

    def visit(key: str) -> None:
        if state.get(key) == 2:
            return
        if state.get(key) == 1:
            raise FormulaError("Formulas must not depend on each other in a cycle.")
        state[key] = 1
        for name in deps.get(key, ()):
            if name in deps:
                visit(name)
        state[key] = 2
        if key in deps:
            ordered.append(key)

    for key in deps:
        visit(key)
    return ordered


def series_of_line(session: Session, line_id: UUID) -> tuple[dict[str, Metric], dict[str, Series]]:
    """Every metric of the line by key, with its series (derived ones computed)."""
    metrics = {metric.key: metric for metric in session.scalars(select(Metric).where(Metric.line_id == line_id).order_by(Metric.key)).all()}
    by_id = {metric.id: metric.key for metric in metrics.values()}
    series: dict[str, Series] = {key: {} for key in metrics}
    for value in session.scalars(select(MetricValue).where(MetricValue.line_id == line_id)).all():
        series[by_id[value.metric_id]][value.period] = value.value
    for key in formula_order(metrics):
        parsed = parse_formula(metrics[key].formula or "")
        periods = set.intersection(*(set(series[name]) for name in parsed.identifiers))
        for period in sorted(periods):
            try:
                series[key][period] = evaluate_formula(parsed, {name: series[name][period] for name in parsed.identifiers})
            except (FormulaError, ZeroDivisionError, OverflowError):
                continue  # a period where the formula is undefined (for example a division by zero) has no value
    return metrics, series
