"""Statistical forecasts of monthly series (no external dependencies).

Three methods: ``linear`` (least-squares trend), ``seasonal`` (trend plus an average
month-of-year effect, from 24 months of history) and ``holt`` (double exponential
smoothing, parameters chosen by one-step error). Each returns point forecasts with an
approximate 95% prediction interval.
"""

import math
from dataclasses import dataclass
from datetime import date

from app.metric_engine import add_months

METHODS = ("linear", "seasonal", "holt")
MIN_HISTORY = {"linear": 3, "seasonal": 24, "holt": 4}
Z95 = 1.96


@dataclass(frozen=True)
class ForecastPoint:
    period: date
    value: float
    lower: float
    upper: float


class InsufficientHistory(ValueError):
    pass


def continuous(series: dict[date, float]) -> tuple[date, list[float]]:
    """The series as consecutive months from its first period, gaps filled by interpolation."""
    first, last = min(series), max(series)
    values: list[float] = []
    period = first
    known = sorted(series)
    while period <= last:
        if period in series:
            values.append(series[period])
        else:
            before = max(p for p in known if p < period)
            after = min(p for p in known if p > period)
            span = (after.year - before.year) * 12 + after.month - before.month
            step = (period.year - before.year) * 12 + period.month - before.month
            values.append(series[before] + (series[after] - series[before]) * step / span)
        period = add_months(period, 1)
    return first, values


def _linear_fit(values: list[float]) -> tuple[float, float, float]:
    n = len(values)
    mean_t = (n - 1) / 2
    mean_y = sum(values) / n
    sxx = sum((t - mean_t) ** 2 for t in range(n)) or 1.0
    slope = sum((t - mean_t) * (y - mean_y) for t, y in enumerate(values)) / sxx
    return mean_y - slope * mean_t, slope, sxx


def _sigma(residuals: list[float], parameters: int) -> float:
    dof = max(len(residuals) - parameters, 1)
    return math.sqrt(sum(r * r for r in residuals) / dof)


def forecast(series: dict[date, float], method: str, until: date) -> list[ForecastPoint]:
    """Forecast months after the series' last period up to and including ``until``."""
    if method not in METHODS:
        raise ValueError(f"unknown method {method!r}")
    first, values = continuous(series)
    n = len(values)
    if n < MIN_HISTORY[method]:
        raise InsufficientHistory(f"{method} needs {MIN_HISTORY[method]} months of history")
    last = add_months(first, n - 1)
    months = (until.year - last.year) * 12 + until.month - last.month
    if months <= 0:
        return []
    points: list[ForecastPoint] = []
    if method in ("linear", "seasonal"):
        intercept, slope, sxx = _linear_fit(values)
        trend = [intercept + slope * t for t in range(n)]
        seasonal = [0.0] * 12
        if method == "seasonal":
            buckets: dict[int, list[float]] = {}
            for t, (y, fitted) in enumerate(zip(values, trend)):
                buckets.setdefault(add_months(first, t).month - 1, []).append(y - fitted)
            means = {month: sum(items) / len(items) for month, items in buckets.items()}
            offset = sum(means.values()) / len(means)
            seasonal = [means.get(month, offset) - offset for month in range(12)]
        fitted = [trend[t] + seasonal[add_months(first, t).month - 1] for t in range(n)]
        sigma = _sigma([y - f for y, f in zip(values, fitted)], 2 + (11 if method == "seasonal" else 0))
        mean_t = (n - 1) / 2
        for h in range(1, months + 1):
            t = n - 1 + h
            period = add_months(last, h)
            value = intercept + slope * t + seasonal[period.month - 1]
            width = Z95 * sigma * math.sqrt(1 + 1 / n + (t - mean_t) ** 2 / sxx)
            points.append(ForecastPoint(period, value, value - width, value + width))
        return points
    best: tuple[float, float, float, float, float] | None = None
    for alpha in (0.2, 0.4, 0.6, 0.8):
        for beta in (0.1, 0.3, 0.5):
            level, trend_ = values[0], values[1] - values[0]
            sse = 0.0
            for y in values[1:]:
                error = y - (level + trend_)
                sse += error * error
                new_level = alpha * y + (1 - alpha) * (level + trend_)
                trend_ = beta * (new_level - level) + (1 - beta) * trend_
                level = new_level
            if best is None or sse < best[0]:
                best = (sse, level, trend_, alpha, beta)
    assert best is not None
    sse, level, trend_, _, _ = best
    sigma = math.sqrt(sse / max(n - 3, 1))
    for h in range(1, months + 1):
        value = level + h * trend_
        width = Z95 * sigma * math.sqrt(h)
        points.append(ForecastPoint(add_months(last, h), value, value - width, value + width))
    return points
