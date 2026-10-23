from datetime import date as dt_date
from typing import Annotated, Literal

from pydantic import Field, FiniteFloat, Strict, StrictInt, model_validator

from app.api.v1.org_states.schemas import TimeserieTimeUnit
from app.api.v1.timeserie_generation.dates import (
    is_period_start,
    period_count,
    period_start,
)
from app.core.schemas import StrictBaseModel

MAX_GENERATED_POINTS = 20_000
MAX_DECIMALS = 10
MAX_SEED = 2**32 - 1

# Specs come from AI clients, so numbers are never coerced from strings or
# booleans, and integer fields reject floats such as 12.0. A plain alias keeps
# the JSON schema inline.
StrictFiniteFloat = Annotated[FiniteFloat, Strict()]


class NoTrend(StrictBaseModel):
    type: Literal["none"] = Field(description="Constant base level.")


class LinearTrend(StrictBaseModel):
    type: Literal["linear"] = Field(
        description="baseLevel + slope * t, where t is the period index from 0.",
    )
    slope: StrictFiniteFloat = Field(description="Level change per period.")


class PercentTrend(StrictBaseModel):
    type: Literal["percent"] = Field(
        description="baseLevel * (1 + percentPerPeriod / 100) ** t.",
    )
    percent_per_period: StrictFiniteFloat = Field(
        gt=-100,
        alias="percentPerPeriod",
        description="Compound growth per period in percent, above -100.",
    )


class LogisticTrend(StrictBaseModel):
    type: Literal["logistic"] = Field(
        description=(
            "baseLevel + (capacity - baseLevel) / "
            "(1 + exp(-growthRate * (t - midpoint)))."
        ),
    )
    capacity: StrictFiniteFloat = Field(description="Level the S-curve approaches.")
    growth_rate: StrictFiniteFloat = Field(
        gt=0,
        alias="growthRate",
        description="Steepness of the S-curve per period.",
    )
    midpoint: StrictFiniteFloat = Field(
        description="Period index at which the curve is halfway to capacity.",
    )


type TimeserieGenerationTrend = Annotated[
    NoTrend | LinearTrend | PercentTrend | LogisticTrend,
    Field(discriminator="type"),
]


class SeasonalityComponent(StrictBaseModel):
    period: StrictFiniteFloat = Field(
        ge=2,
        description="Cycle length in periods, for example 12 for months in a year.",
    )
    amplitude: StrictFiniteFloat = Field(
        ge=0,
        description=(
            "Additive: absolute peak deviation. Multiplicative: relative peak "
            "deviation from 0 to 1, for example 0.1 for +-10 %."
        ),
    )
    mode: Literal["additive", "multiplicative"] = Field(
        description="Whether the cycle is added to or multiplies the level.",
    )
    peak_offset: StrictFiniteFloat = Field(
        default=0,
        alias="peakOffset",
        description="Period index (modulo period) at which the cycle peaks.",
    )

    @model_validator(mode="after")
    def multiplicative_amplitude_is_relative(self) -> "SeasonalityComponent":
        if self.mode == "multiplicative" and self.amplitude > 1:
            raise ValueError("Multiplicative seasonality amplitude must be at most 1.")
        return self


class NoiseSpec(StrictBaseModel):
    std: StrictFiniteFloat | None = Field(
        default=None,
        ge=0,
        description="Absolute standard deviation of the noise.",
    )
    relative_std: StrictFiniteFloat | None = Field(
        default=None,
        ge=0,
        alias="relativeStd",
        description="Standard deviation as a fraction of the noiseless value.",
    )
    ar1: StrictFiniteFloat | None = Field(
        default=None,
        gt=-1,
        lt=1,
        description=(
            "Optional AR(1) autocorrelation coefficient. The noise keeps its "
            "standard deviation."
        ),
    )

    @model_validator(mode="after")
    def exactly_one_scale(self) -> "NoiseSpec":
        if (self.std is None) == (self.relative_std is None):
            raise ValueError("Provide exactly one of std or relativeStd.")
        return self


class LevelShift(StrictBaseModel):
    date: dt_date = Field(
        description="First period start date the delta applies to.",
    )
    delta: StrictFiniteFloat = Field(
        description="Permanent change added to the level from this date onwards.",
    )


def _no_trend() -> NoTrend:
    return NoTrend(type="none")


def _empty_seasonality() -> list[SeasonalityComponent]:
    return []


def _empty_level_shifts() -> list[LevelShift]:
    return []


class TimeserieGenerationSpec(StrictBaseModel):
    """Numeric-only specification for deterministic timeserie generation."""

    start_date: dt_date = Field(
        alias="startDate",
        description="First period start date, aligned to timeUnit.",
    )
    periods: StrictInt | None = Field(
        default=None,
        ge=1,
        le=MAX_GENERATED_POINTS,
        description="Number of points. Provide exactly one of periods or endDate.",
    )
    end_date: dt_date | None = Field(
        default=None,
        alias="endDate",
        description=(
            "Inclusive last date. The last point is the last period start on or "
            "before it. Provide exactly one of periods or endDate."
        ),
    )
    time_unit: TimeserieTimeUnit = Field(
        alias="timeUnit",
        description="Timeserie time grain.",
    )
    base_level: StrictFiniteFloat = Field(
        alias="baseLevel",
        description=(
            "Starting level of the trend, before level shifts, seasonality and "
            "noise. It is the t=0 value for none, linear and percent trends. A "
            "logistic trend leaves it asymptotically, so its t=0 value depends "
            "on midpoint."
        ),
    )
    trend: TimeserieGenerationTrend = Field(
        default_factory=_no_trend,
        description="Level curve over the period index.",
    )
    seasonality: list[SeasonalityComponent] = Field(
        default_factory=_empty_seasonality,
        max_length=10,
        description="Cosine cycles combined with the level.",
    )
    noise: NoiseSpec | None = Field(
        default=None,
        description="Optional Gaussian noise drawn from the seed.",
    )
    level_shifts: list[LevelShift] = Field(
        default_factory=_empty_level_shifts,
        max_length=100,
        alias="levelShifts",
        description="Permanent step changes of the level.",
    )
    clamp_min: StrictFiniteFloat | None = Field(
        default=None,
        alias="clampMin",
        description="Optional lower bound applied before rounding.",
    )
    clamp_max: StrictFiniteFloat | None = Field(
        default=None,
        alias="clampMax",
        description="Optional upper bound applied before rounding.",
    )
    decimals: StrictInt = Field(
        default=2,
        ge=0,
        le=MAX_DECIMALS,
        description="Number of decimals the values are rounded to.",
    )
    seed: StrictInt = Field(
        ge=0,
        le=MAX_SEED,
        description="Random seed. Identical specs give identical values.",
    )

    @model_validator(mode="after")
    def dates_and_bounds_are_consistent(self) -> "TimeserieGenerationSpec":
        if not is_period_start(self.time_unit, self.start_date):
            raise ValueError(_unaligned_message("startDate", self))
        for shift in self.level_shifts:
            if not is_period_start(self.time_unit, shift.date):
                raise ValueError(
                    _unaligned_message("levelShifts date", self, shift.date)
                )

        if (self.periods is None) == (self.end_date is None):
            raise ValueError("Provide exactly one of periods or endDate.")
        if self.end_date is not None:
            if self.end_date < self.start_date:
                raise ValueError("endDate must not be before startDate.")
            count = period_count(self.start_date, self.time_unit, self.end_date)
            if count > MAX_GENERATED_POINTS:
                raise ValueError(
                    f"The spec produces {count} points; at most "
                    f"{MAX_GENERATED_POINTS} are allowed."
                )

        try:
            period_start(self.start_date, self.time_unit, self.point_count() - 1)
        except (OverflowError, ValueError) as error:
            raise ValueError(
                "The last period start is past the largest supported date."
            ) from error

        if (
            self.clamp_min is not None
            and self.clamp_max is not None
            and self.clamp_min > self.clamp_max
        ):
            raise ValueError("clampMin must not be greater than clampMax.")
        return self

    def point_count(self) -> int:
        if self.periods is not None:
            return self.periods
        assert self.end_date is not None
        return period_count(self.start_date, self.time_unit, self.end_date)


def _unaligned_message(
    field: str,
    spec: TimeserieGenerationSpec,
    value: dt_date | None = None,
) -> str:
    value_date = spec.start_date if value is None else value
    rule = {
        "day": "any date",
        "week": "a Monday",
        "month": "the 1st of a month",
        "year": "1 January",
    }[spec.time_unit]
    return (
        f"{field} {value_date.isoformat()} is not a valid {spec.time_unit} start "
        f"date; it must be {rule}."
    )


class GeneratedPoint(StrictBaseModel):
    date: dt_date = Field(description="Value start date.")
    value: FiniteFloat = Field(description="Generated number value.")
