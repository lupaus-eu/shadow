import math
from datetime import date as dt_date

import numpy as np
import numpy.typing as npt

from app.api.v1.timeserie_generation.dates import period_dates
from app.api.v1.timeserie_generation.schemas import (
    GeneratedPoint,
    LinearTrend,
    LogisticTrend,
    NoiseSpec,
    PercentTrend,
    TimeserieGenerationSpec,
    TimeserieGenerationTrend,
)

# Bump whenever the same spec can produce different values, so frozen values
# record which generator produced them.
GENERATOR_VERSION = 1

type FloatArray = npt.NDArray[np.float64]


class TimeserieGenerationError(ValueError):
    """A valid spec whose generated values are not finite numbers."""


def generate(spec: TimeserieGenerationSpec) -> list[GeneratedPoint]:
    """Generate numeric timeserie values deterministically from `spec`.

    The value at period index t is

        (trend(t) + level shifts) * product(multiplicative seasonality)
        + sum(additive seasonality) + noise

    then clamped and rounded. Identical specs give identical output.
    """
    count = spec.point_count()
    dates = period_dates(spec.start_date, spec.time_unit, count)
    index = np.arange(count, dtype=np.float64)

    with np.errstate(over="ignore", invalid="ignore"):
        level = _trend(spec.trend, spec.base_level, index)
        level = level + _level_shifts(spec, dates)

        multiplier = np.ones(count, dtype=np.float64)
        additive = np.zeros(count, dtype=np.float64)
        for component in spec.seasonality:
            wave = np.cos(
                2 * np.pi * (index - component.peak_offset) / component.period
            )
            if component.mode == "multiplicative":
                multiplier = multiplier * (1 + component.amplitude * wave)
            else:
                additive = additive + component.amplitude * wave
        values = level * multiplier + additive

        if spec.noise is not None:
            values = values + _noise(spec.noise, spec.seed, values)

    _ensure_finite(values)
    with np.errstate(over="ignore", invalid="ignore"):
        if spec.clamp_min is not None or spec.clamp_max is not None:
            values = np.clip(values, spec.clamp_min, spec.clamp_max)
        # Adding 0.0 turns a rounded -0.0 into 0.0.
        values = np.round(values, spec.decimals) + 0.0
    # Rounding scales by 10 ** decimals, which can overflow values near the
    # float limit.
    _ensure_finite(values)

    return [
        GeneratedPoint(date=point_date, value=value)
        for point_date, value in zip(dates, values.tolist(), strict=True)
    ]


def _ensure_finite(values: FloatArray) -> None:
    if not bool(np.all(np.isfinite(values))):
        raise TimeserieGenerationError(
            "The spec generates values that are not finite numbers; reduce the "
            "trend, levels, periods or decimals."
        )


def _trend(
    trend: TimeserieGenerationTrend,
    base_level: float,
    index: FloatArray,
) -> FloatArray:
    if isinstance(trend, LinearTrend):
        return base_level + trend.slope * index
    if isinstance(trend, PercentTrend):
        if base_level == 0:
            # Avoid 0 * inf = NaN when the growth factor overflows.
            return np.full(index.shape, base_level, dtype=np.float64)
        return base_level * (1 + trend.percent_per_period / 100) ** index
    if isinstance(trend, LogisticTrend):
        sigmoid = 1 / (1 + np.exp(-trend.growth_rate * (index - trend.midpoint)))
        return base_level + (trend.capacity - base_level) * sigmoid
    return np.full(index.shape, base_level, dtype=np.float64)


def _level_shifts(spec: TimeserieGenerationSpec, dates: list[dt_date]) -> FloatArray:
    shifts = np.zeros(len(dates), dtype=np.float64)
    if not spec.level_shifts:
        return shifts

    day_numbers = np.array([value.toordinal() for value in dates], dtype=np.int64)
    for shift in spec.level_shifts:
        shifts = shifts + np.where(
            day_numbers >= shift.date.toordinal(), shift.delta, 0.0
        )
    return shifts


def _noise(noise: NoiseSpec, seed: int, noiseless: FloatArray) -> FloatArray:
    rng = np.random.default_rng(seed)
    count = len(noiseless)
    innovations: FloatArray = rng.standard_normal(count)

    # Stationary unit-variance AR(1), so std keeps its meaning for any ar1.
    unit_noise: FloatArray = innovations
    if noise.ar1:
        ar1 = noise.ar1
        innovation_scale = math.sqrt(1 - ar1 * ar1)
        unit_noise = innovations.copy()
        for position in range(1, count):
            unit_noise[position] = (
                ar1 * unit_noise[position - 1]
                + innovation_scale * innovations[position]
            )

    if noise.std is not None:
        return noise.std * unit_noise
    assert noise.relative_std is not None
    return noise.relative_std * np.abs(noiseless) * unit_noise
