"""Validated detached inputs and outputs for Forecasting calculations."""

from datetime import date as dt_date
from typing import Literal

from pydantic import ConfigDict, Field, field_validator, model_validator

from app.core.schemas import StrictBaseModel

SNAPSHOT_FORMAT = "shadow.prediction-input.v1"
CALCULATION_FORMAT = "shadow.prediction-calculation.v1"
ResultKind = Literal[
    "naive", "seasonal_naive", "average", "mlforecast", "sarima", "prophet"
]
# Canonical result-kind order (ADR-014). Snapshots stored before ADR-014 have no
# modelKinds key and calculate exactly the legacy five kinds.
RESULT_KINDS: tuple[ResultKind, ...] = (
    "naive",
    "seasonal_naive",
    "average",
    "mlforecast",
    "sarima",
    "prophet",
)
LEGACY_RESULT_KINDS: tuple[ResultKind, ...] = RESULT_KINDS[:5]
# The only kinds that use the seasonal period (ADR-014, TASK-063A amendment).
SEASONAL_PERIOD_RESULT_KINDS: frozenset[ResultKind] = frozenset(
    {"seasonal_naive", "sarima"}
)
TimeUnit = Literal["day", "week", "month", "year"]
EligibilityStatus = Literal["eligible", "ineligible", "requires_manual_seasonal_period"]
ResultStatus = Literal["available", "ineligible"]
CrossValidationStatus = Literal["available", "unavailable", "not_applicable"]
PredictionIntervalStatus = Literal["available", "unavailable", "not_applicable"]


def canonical_result_kinds(values: list[ResultKind]) -> list[ResultKind]:
    """Reject duplicate kinds and return the selection in canonical order."""
    if len(set(values)) != len(values):
        raise ValueError("Model kinds must not contain duplicates.")
    return [kind for kind in RESULT_KINDS if kind in values]


def uses_seasonal_period(model_kinds: list[ResultKind]) -> bool:
    """Whether the selection contains a kind that uses the seasonal period."""
    return not SEASONAL_PERIOD_RESULT_KINDS.isdisjoint(model_kinds)


class _FrozenModel(StrictBaseModel):
    model_config = ConfigDict(
        allow_inf_nan=False,
        extra="forbid",
        frozen=True,
        populate_by_name=True,
    )


class SnapshotObservation(_FrozenModel):
    date: dt_date
    value: float
    source: Literal["targetScenario"] = "targetScenario"


class SnapshotFeaturePeriod(_FrozenModel):
    date: dt_date
    features: dict[str, float]


class SnapshotMetricReference(_FrozenModel):
    metric_key: str = Field(alias="metricKey")
    short_name: str = Field(alias="shortName")


class PredictionTargetSnapshot(_FrozenModel):
    scenario_internal_id: int = Field(alias="scenarioInternalId")
    scenario_key: str = Field(min_length=1, alias="scenarioKey")
    scenario_name: str = Field(min_length=1, alias="scenarioName")
    metric_key: str = Field(min_length=1, alias="metricKey")
    metric_name: str = Field(min_length=1, alias="metricName")
    metric_short_name: str | None = Field(default=None, alias="metricShortName")
    time_unit: TimeUnit = Field(alias="timeUnit")
    unit: str | None
    status: EligibilityStatus
    reason: str | None
    seasonal_period: int | None = Field(alias="seasonalPeriod")
    seasonal_period_source: str | None = Field(alias="seasonalPeriodSource")
    observations: list[SnapshotObservation]
    history_periods: list[SnapshotFeaturePeriod] = Field(alias="historyPeriods")
    prediction_periods: list[SnapshotFeaturePeriod] = Field(alias="predictionPeriods")
    derived_formula: str | None = Field(default=None, alias="derivedFormula")
    referenced_metrics: list[SnapshotMetricReference] = Field(
        default_factory=lambda: list[SnapshotMetricReference](),
        alias="referencedMetrics",
    )

    @model_validator(mode="after")
    def validate_target_shape(self) -> "PredictionTargetSnapshot":
        if (
            self.derived_formula is None
            and self.status == "eligible"
            and len(self.observations) != len(self.history_periods)
        ):
            raise ValueError("Observation and historical feature grids must match.")
        if self.history_periods and [item.date for item in self.observations] != [
            item.date for item in self.history_periods
        ]:
            raise ValueError("Observation and historical feature dates must match.")
        if self.derived_formula is None and self.referenced_metrics:
            raise ValueError("Only a derived target may contain metric references.")
        if self.derived_formula is not None and self.observations:
            raise ValueError("A derived target cannot contain fitted observations.")
        if len({item.date for item in self.prediction_periods}) != len(
            self.prediction_periods
        ):
            raise ValueError("Prediction period dates must be unique.")
        if len({item.metric_key for item in self.referenced_metrics}) != len(
            self.referenced_metrics
        ):
            raise ValueError("Derived metric references must be unique.")
        return self

    def source_audit_snapshot(self) -> dict[str, object]:
        snapshot: dict[str, object] = {
            "targetScenarioId": self.scenario_key,
            "targetScenarioName": self.scenario_name,
            "observationPolicy": "targetScenarioOnly",
            "metric": {
                "id": self.metric_key,
                "name": self.metric_name,
                "shortName": self.metric_short_name,
                "timeUnit": self.time_unit,
                "unit": self.unit,
            },
            "effectiveObservations": [
                {
                    "date": item.date.isoformat(),
                    "value": item.value,
                    "source": item.source,
                }
                for item in self.observations
            ],
        }
        if self.derived_formula is not None:
            snapshot["derivedFormula"] = self.derived_formula
            snapshot["referencedMetrics"] = [
                {
                    "id": item.metric_key,
                    "shortName": item.short_name,
                }
                for item in self.referenced_metrics
            ]
        return snapshot

    def input_audit_snapshot(self) -> dict[str, object]:
        return {
            "historyPeriods": [
                {"date": item.date.isoformat(), **item.features}
                for item in self.history_periods
            ],
            "periods": [
                {"date": item.date.isoformat(), **item.features}
                for item in self.prediction_periods
            ],
        }


class PredictionInputSnapshot(_FrozenModel):
    snapshot_format: Literal["shadow.prediction-input.v1"] = Field(
        default=SNAPSHOT_FORMAT, alias="snapshotFormat"
    )
    organisation_internal_id: int = Field(alias="organisationInternalId")
    organisation_key: str = Field(min_length=1, alias="organisationKey")
    prediction_key: str = Field(min_length=1, alias="predictionKey")
    name: str = Field(min_length=1, max_length=200)
    creator_user_id: int = Field(alias="creatorUserId")
    cutoff_mode: Literal["asOfStart", "allCurrentScenario"] = Field(alias="cutoffMode")
    confidence_level: int = Field(ge=50, le=99, alias="confidenceLevel")
    start_date: dt_date = Field(alias="startDate")
    end_date: dt_date = Field(alias="endDate")
    model_configuration: dict[str, object] = Field(alias="modelConfiguration")
    model_kinds: list[ResultKind] = Field(
        default_factory=lambda: list(LEGACY_RESULT_KINDS),
        min_length=1,
        alias="modelKinds",
    )
    targets: list[PredictionTargetSnapshot]

    @field_validator("model_kinds")
    @classmethod
    def model_kinds_are_canonical(cls, values: list[ResultKind]) -> list[ResultKind]:
        return canonical_result_kinds(values)

    @model_validator(mode="after")
    def validate_snapshot_shape(self) -> "PredictionInputSnapshot":
        if self.start_date >= self.end_date:
            raise ValueError("Prediction snapshot date range is invalid.")
        identities = [(item.scenario_key, item.metric_key) for item in self.targets]
        if len(set(identities)) != len(identities):
            raise ValueError("Prediction snapshot target identities must be unique.")
        return self


class CalculatedResult(_FrozenModel):
    kind: ResultKind
    values: list[float]
    status: ResultStatus
    reason: str | None
    cross_validation_status: CrossValidationStatus = Field(
        alias="crossValidationStatus"
    )
    cross_validation_mae: float | None = Field(alias="crossValidationMae")
    prediction_interval_status: PredictionIntervalStatus = Field(
        alias="predictionIntervalStatus"
    )
    prediction_interval_reason: str | None = Field(alias="predictionIntervalReason")
    bounds: list[tuple[float, float]] | None = None

    @model_validator(mode="after")
    def validate_result_shape(self) -> "CalculatedResult":
        if self.status != "available" and self.values:
            raise ValueError("An unavailable result cannot contain values.")
        if self.bounds is not None:
            if len(self.bounds) != len(self.values):
                raise ValueError("Prediction interval bounds must be complete.")
            if any(
                lower > value or value > upper
                for value, (lower, upper) in zip(self.values, self.bounds, strict=True)
            ):
                raise ValueError("Prediction interval bounds must enclose values.")
        if self.prediction_interval_status == "available" and self.bounds is None:
            raise ValueError("An available interval must contain bounds.")
        if self.prediction_interval_status != "available" and self.bounds is not None:
            raise ValueError("Only an available interval may contain bounds.")
        return self


class CalculatedTarget(_FrozenModel):
    scenario_key: str = Field(min_length=1, alias="scenarioKey")
    metric_key: str = Field(min_length=1, alias="metricKey")
    results: list[CalculatedResult]


class PredictionCalculation(_FrozenModel):
    calculation_format: Literal["shadow.prediction-calculation.v1"] = Field(
        default=CALCULATION_FORMAT, alias="calculationFormat"
    )
    snapshot_format: Literal["shadow.prediction-input.v1"] = Field(
        alias="snapshotFormat"
    )
    prediction_key: str = Field(alias="predictionKey")
    targets: list[CalculatedTarget]

    @model_validator(mode="after")
    def validate_calculation_shape(self) -> "PredictionCalculation":
        identities = [(item.scenario_key, item.metric_key) for item in self.targets]
        if len(set(identities)) != len(identities):
            raise ValueError("Calculated target identities must be unique.")
        if any(
            len({result.kind for result in item.results}) != len(item.results)
            for item in self.targets
        ):
            raise ValueError("Calculated result kinds must be unique per target.")
        return self
