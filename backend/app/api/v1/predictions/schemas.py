from datetime import date as dt_date
from typing import Literal

from pydantic import Field, field_validator, model_validator

from app.core.schemas import StrictBaseModel

CutoffMode = Literal["asOfStart", "allCurrentScenario"]


class PredictionRequestBase(StrictBaseModel):
    target_scenario_ids: list[str] = Field(
        min_length=1, max_length=50, alias="targetScenarioIds"
    )
    start_date: dt_date = Field(alias="startDate")
    end_date: dt_date = Field(alias="endDate")
    cutoff_mode: CutoffMode = Field(alias="cutoffMode")
    manual_seasonal_periods: dict[str, int] = Field(
        default_factory=dict, alias="manualSeasonalPeriods"
    )

    @field_validator("target_scenario_ids")
    @classmethod
    def scenario_ids_are_distinct_non_blank(cls, values: list[str]) -> list[str]:
        cleaned = [value.strip() for value in values]
        if any(not value for value in cleaned) or len(set(cleaned)) != len(cleaned):
            raise ValueError("Target scenario IDs must be distinct and non-blank.")
        return cleaned

    @field_validator("manual_seasonal_periods")
    @classmethod
    def manual_periods_are_valid(cls, values: dict[str, int]) -> dict[str, int]:
        if any(not key.strip() or value < 2 for key, value in values.items()):
            raise ValueError(
                "Manual seasonal periods require non-blank metric IDs and "
                "periods of at least 2."
            )
        return values

    @model_validator(mode="after")
    def date_range_is_ordered(self) -> "PredictionRequestBase":
        if self.start_date >= self.end_date:
            raise ValueError("startDate must be earlier than endDate.")
        return self


class PredictionPreflightRequest(PredictionRequestBase):
    pass


class PredictionCreateRequest(PredictionRequestBase):
    name: str = Field(min_length=1, max_length=200)

    @field_validator("name")
    @classmethod
    def name_is_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Prediction version name must not be blank.")
        return value


class PredictionMetricPreflightResponse(StrictBaseModel):
    scenario_id: str = Field(alias="scenarioId")
    metric_id: str = Field(alias="metricId")
    status: str
    reason: str | None = None
    seasonal_period: int | None = Field(default=None, alias="seasonalPeriod")
    seasonal_period_source: str | None = Field(
        default=None, alias="seasonalPeriodSource"
    )
    requires_manual_seasonal_period: bool = Field(alias="requiresManualSeasonalPeriod")


class PredictionPreflightResponse(StrictBaseModel):
    metrics: list[PredictionMetricPreflightResponse]


class PredictionVersionListResponse(StrictBaseModel):
    id: str
    name: str
    start_date: dt_date = Field(alias="startDate")
    end_date: dt_date = Field(alias="endDate")
    cutoff_mode: CutoffMode = Field(alias="cutoffMode")
    created_time: str = Field(alias="createdTime")


class PredictionPointResponse(StrictBaseModel):
    date: dt_date
    value: float


class PredictionModelResultResponse(StrictBaseModel):
    kind: str
    status: str
    reason: str | None = None
    cross_validation_status: str = Field(alias="crossValidationStatus")
    cross_validation_mae: float | None = Field(alias="crossValidationMae")
    configuration: dict[str, object]
    points: list[PredictionPointResponse]


class PredictionTargetResponse(StrictBaseModel):
    scenario_id: str = Field(alias="scenarioId")
    metric_id: str = Field(alias="metricId")
    metric_name: str = Field(alias="metricName")
    time_unit: str = Field(alias="timeUnit")
    unit: str | None
    status: str
    reason: str | None
    seasonal_period: int | None = Field(alias="seasonalPeriod")
    seasonal_period_source: str | None = Field(alias="seasonalPeriodSource")
    source_snapshot: dict[str, object] = Field(alias="sourceSnapshot")
    input_snapshot: dict[str, object] = Field(alias="inputSnapshot")
    results: list[PredictionModelResultResponse]


class PredictionVersionDetailResponse(PredictionVersionListResponse):
    model_configuration: dict[str, object] = Field(alias="modelConfiguration")
    targets: list[PredictionTargetResponse]
