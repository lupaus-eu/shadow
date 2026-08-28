import math
import re
from datetime import date as dt_date
from typing import Literal

from pydantic import Field, field_validator, model_validator

from app.core.schemas import StrictBaseModel

type TimeserieTimeUnit = Literal["day", "week", "month", "year"]
type TimeserieValueUnit = Literal["number", "string", "boolean"]
type TimeserieCellValue = int | float | str | bool

EQUATION_SAFE_IDENTIFIER = re.compile(r"[A-Za-z][A-Za-z0-9_]*")


class ScenarioCreateRequest(StrictBaseModel):
    name: str = Field(min_length=1, description="Scenario display name.")
    description: str | None = Field(
        default=None,
        description="Scenario description.",
    )

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Scenario name must not be blank.")
        return stripped


class ScenarioPatchRequest(StrictBaseModel):
    name: str | None = Field(
        default=None,
        min_length=1,
        description="Scenario display name.",
    )
    description: str | None = Field(
        default=None,
        description="Scenario description.",
    )

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None

        stripped = value.strip()
        if not stripped:
            raise ValueError("Scenario name must not be blank.")
        return stripped


class ScenarioCopyRequest(StrictBaseModel):
    source_scenario_id: str = Field(
        min_length=1,
        alias="sourceScenarioId",
        description="Stable scenario key to copy from.",
    )
    source_org_state_id: str = Field(
        min_length=1,
        alias="sourceOrgStateId",
        description="Stable organisation state key to copy into the new scenario.",
    )
    name: str | None = Field(
        default=None,
        description=(
            "Copied scenario display name. Defaults to 'Fork of ' plus the "
            "source scenario name when omitted or blank."
        ),
    )
    description: str | None = Field(
        default=None,
        description="Copied scenario description.",
    )

    @field_validator("source_scenario_id", "source_org_state_id")
    @classmethod
    def required_text_fields_must_not_be_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Value must not be blank.")
        return stripped

    @field_validator("name")
    @classmethod
    def blank_name_defaults_to_none(cls, value: str | None) -> str | None:
        if value is None:
            return None

        stripped = value.strip()
        return stripped or None


class ScenarioResponse(StrictBaseModel):
    id: str = Field(description="Stable scenario key.")
    name: str = Field(description="Scenario display name.")
    description: str = Field(description="Scenario description.")
    protected: bool = Field(description="Whether the scenario is protected.")


class OrgStateCreateRequest(StrictBaseModel):
    name: str = Field(min_length=1, description="Organisation state display name.")
    description: str | None = Field(
        default=None,
        description="Organisation state description.",
    )
    target_date: dt_date = Field(
        alias="targetDate",
        description="Organisation state target date.",
    )

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Organisation state name must not be blank.")
        return stripped


class OrgStatePatchRequest(StrictBaseModel):
    name: str | None = Field(
        default=None,
        min_length=1,
        description="Organisation state display name.",
    )
    description: str | None = Field(
        default=None,
        description="Organisation state description.",
    )
    target_date: dt_date | None = Field(
        default=None,
        alias="targetDate",
        description="Organisation state target date.",
    )

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None

        stripped = value.strip()
        if not stripped:
            raise ValueError("Organisation state name must not be blank.")
        return stripped


class OrgStateResponse(StrictBaseModel):
    id: str = Field(description="Stable organisation state key.")
    name: str = Field(description="Organisation state display name.")
    description: str = Field(description="Organisation state description.")
    target_date: dt_date = Field(
        alias="targetDate",
        description="Organisation state target date.",
    )


class OrgStatesCleanResponse(StrictBaseModel):
    cleaned: int = Field(ge=0, description="Number of cleaned organisation states.")


class EventCreateRequest(StrictBaseModel):
    name: str = Field(min_length=1, description="Event display name.")
    target_date: dt_date = Field(
        alias="targetDate",
        description="Event target date.",
    )
    event_details: str | None = Field(
        default=None,
        alias="eventDetails",
        description="Event details.",
    )

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Event name must not be blank.")
        return stripped


class EventPatchRequest(StrictBaseModel):
    name: str | None = Field(
        default=None,
        min_length=1,
        description="Event display name.",
    )
    target_date: dt_date | None = Field(
        default=None,
        alias="targetDate",
        description="Event target date.",
    )
    event_details: str | None = Field(
        default=None,
        alias="eventDetails",
        description="Event details.",
    )

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None

        stripped = value.strip()
        if not stripped:
            raise ValueError("Event name must not be blank.")
        return stripped


class EventResponse(StrictBaseModel):
    id: str = Field(description="Stable event key.")
    name: str = Field(description="Event display name.")
    target_date: dt_date = Field(
        alias="targetDate",
        description="Event target date.",
    )
    event_details: str = Field(
        alias="eventDetails",
        description="Event details.",
    )


class TimeserieCreateRequest(StrictBaseModel):
    id: str = Field(min_length=1, description="Stable timeserie key.")
    name: str = Field(min_length=1, description="Timeserie display name.")
    short_name: str | None = Field(
        default=None,
        alias="shortName",
        description="Optional equation-safe timeserie identifier.",
    )
    description: str | None = Field(
        default=None,
        description="Timeserie description.",
    )
    unit: str | None = Field(
        default=None,
        description="Human-readable unit label.",
    )
    time_unit: TimeserieTimeUnit = Field(
        alias="timeUnit",
        description="Timeserie time grain.",
    )
    value_unit: TimeserieValueUnit = Field(
        alias="valueUnit",
        description="Timeserie value type.",
    )

    @field_validator("id", "name")
    @classmethod
    def required_text_fields_must_not_be_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Value must not be blank.")
        return stripped

    @field_validator("description", "unit")
    @classmethod
    def optional_text_fields_are_trimmed(cls, value: str | None) -> str | None:
        if value is None:
            return None

        stripped = value.strip()
        return stripped or None

    @field_validator("short_name")
    @classmethod
    def short_name_must_be_equation_safe(cls, value: str | None) -> str | None:
        if value is None:
            return None

        stripped = value.strip()
        if not stripped:
            return None
        if EQUATION_SAFE_IDENTIFIER.fullmatch(stripped) is None:
            raise ValueError(
                "Short name must start with a letter and contain only letters, "
                "numbers and underscores."
            )
        return stripped


class TimeserieValueRequest(StrictBaseModel):
    date: dt_date = Field(description="Value start date.")
    value: TimeserieCellValue = Field(description="Typed cell value.")

    @field_validator("value")
    @classmethod
    def numeric_values_must_be_finite(
        cls,
        value: TimeserieCellValue,
    ) -> TimeserieCellValue:
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("Number value must be finite.")
        return value


def _empty_timeserie_values() -> list[TimeserieValueRequest]:
    return []


class TimeserieValuesPatchRequest(StrictBaseModel):
    values: list[TimeserieValueRequest] = Field(
        default_factory=_empty_timeserie_values,
        description="Replacement set of active values for the timeserie.",
    )


class TimeserieShortNamePatchRequest(StrictBaseModel):
    short_name: str | None = Field(alias="shortName")

    @field_validator("short_name")
    @classmethod
    def short_name_must_be_equation_safe(cls, value: str | None) -> str | None:
        return TimeserieCreateRequest.short_name_must_be_equation_safe(value)


class DerivedMetricCreateRequest(StrictBaseModel):
    name: str = Field(min_length=1)
    unit: str | None = None
    formula: str = Field(min_length=1)

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Derived metric name must not be blank.")
        return value

    @field_validator("unit")
    @classmethod
    def unit_is_trimmed(cls, value: str | None) -> str | None:
        return value.strip() or None if value is not None else None

    @field_validator("formula")
    @classmethod
    def formula_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Formula must not be blank.")
        return value


class DerivedMetricPatchRequest(StrictBaseModel):
    name: str | None = None
    unit: str | None = None
    formula: str | None = None

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("Derived metric name must not be blank.")
        return value

    @field_validator("unit")
    @classmethod
    def unit_is_trimmed(cls, value: str | None) -> str | None:
        return value.strip() or None if value is not None else None

    @field_validator("formula")
    @classmethod
    def formula_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("Formula must not be blank.")
        return value

    @model_validator(mode="after")
    def must_update_something(self) -> "DerivedMetricPatchRequest":
        if not self.model_fields_set:
            raise ValueError("Provide at least one derived metric field to update.")
        return self


class TimeserieValueResponse(StrictBaseModel):
    date: dt_date = Field(description="Value start date.")
    value: TimeserieCellValue = Field(description="Typed cell value.")


class TimeserieResponse(StrictBaseModel):
    id: str = Field(description="Stable timeserie key.")
    name: str = Field(description="Timeserie display name.")
    short_name: str = Field(
        alias="shortName",
        description="Optional equation-safe timeserie identifier.",
    )
    description: str = Field(description="Timeserie description.")
    unit: str = Field(description="Human-readable unit label.")
    time_unit: TimeserieTimeUnit = Field(
        alias="timeUnit",
        description="Timeserie time grain.",
    )
    value_unit: TimeserieValueUnit = Field(
        alias="valueUnit",
        description="Timeserie value type.",
    )
    values: list[TimeserieValueResponse] = Field(
        description="Active values sorted by start date.",
    )
    is_derived: bool = Field(default=False, alias="isDerived")
    derived_formula: str | None = Field(default=None, alias="derivedFormula")
    short_name_editable: bool = Field(default=True, alias="shortNameEditable")


class TimeserieExistsResponse(StrictBaseModel):
    id: str = Field(description="Stable timeserie key.")
    exists: bool = Field(description="Whether an active timeserie exists.")
    short_name: str = Field(
        alias="shortName",
        description="Optional equation-safe timeserie identifier when it exists.",
    )
    short_name_editable: bool = Field(default=True, alias="shortNameEditable")
