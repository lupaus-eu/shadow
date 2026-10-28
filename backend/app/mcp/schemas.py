"""Result envelopes of the MCP tools that bound, summarise or combine data.

They wrap the existing domain response schemas with the truncation and
summary fields an AI client needs. Field names are what FastMCP serialises.
"""

from datetime import date as dt_date

from pydantic import Field

from app.api.v1.ai_change_sets.schemas import (
    ChangeSetStatus,
    ChangeSetSummary,
    OperationResult,
    ReplacementReport,
)
from app.api.v1.org_states.schemas import TimeserieResponse
from app.api.v1.timeserie_generation.schemas import GeneratedPoint
from app.core.schemas import StrictBaseModel


class TimeserieListResult(StrictBaseModel):
    timeseries: list[TimeserieResponse] = Field(
        description="Active timeseries of the scenario, sorted by key."
    )
    values_included: bool = Field(
        description="Whether values were requested. When false every `values` "
        "list is empty, whatever the timeserie holds."
    )
    max_values: int = Field(
        description="Most values returned in total across all timeseries."
    )
    truncated: bool = Field(
        description="Whether any timeserie's values were cut to fit max_values."
    )
    truncated_timeserie_ids: list[str] = Field(
        description="Keys of the timeseries whose values were cut or omitted."
    )


class TimeserieValuesResult(StrictBaseModel):
    timeserie: TimeserieResponse = Field(
        description="The timeserie, with only the returned values."
    )
    from_date: dt_date | None = Field(description="Inclusive lower date bound.")
    to_date: dt_date | None = Field(description="Inclusive upper date bound.")
    value_count: int = Field(
        description="Number of values within the date bounds, returned or not."
    )
    max_points: int = Field(description="Most values returned per call.")
    truncated: bool = Field(
        description="Whether values within the date bounds were left out."
    )
    next_from_date: dt_date | None = Field(
        description="Date of the first value left out; pass it as from_date to "
        "read the next page. Null when nothing was left out."
    )


class GeneratedTimeseriePreview(StrictBaseModel):
    generator_version: int = Field(description="Generator version used.")
    point_count: int = Field(description="Number of generated points.")
    first_date: dt_date = Field(description="Date of the first point.")
    last_date: dt_date = Field(description="Date of the last point.")
    min: float = Field(description="Smallest generated value.")
    max: float = Field(description="Largest generated value.")
    mean: float = Field(description="Arithmetic mean of the generated values.")
    first_points: list[GeneratedPoint] = Field(
        description="The first points in date order."
    )
    last_points: list[GeneratedPoint] = Field(
        description="The last points in date order; overlaps first_points for "
        "short series."
    )


class ChangeSetListResult(StrictBaseModel):
    change_sets: list[ChangeSetSummary] = Field(
        description="Matching change sets, newest first."
    )
    max_items: int = Field(description="Most change sets returned per call.")
    truncated: bool = Field(
        description="Whether older matching change sets were left out."
    )


class OperationsAdded(StrictBaseModel):
    change_set: ChangeSetSummary
    added_positions: list[int] = Field(
        description="Positions given to the added operations, in order."
    )


class ChangeSetValidation(StrictBaseModel):
    change_set_key: str
    ok: bool = Field(description="Whether every operation validated.")
    operations: list[OperationResult] = Field(
        description="Per-operation results in order: ok, the first error, then "
        "not_run for the rest."
    )
    refs: dict[str, str] = Field(
        description="$ref symbol to key map of the dry-run. These keys are "
        "provisional: the dry-run was rolled back and apply generates new ones."
    )
    replacements: ReplacementReport = Field(
        description="For information only, not stored: operations that would "
        "replace data existing now. The human review recomputes them against "
        "the data current at review and apply time."
    )


class ChangeSetSubmission(StrictBaseModel):
    change_set_key: str
    status: ChangeSetStatus = Field(
        description="submitted when every operation validated, otherwise draft."
    )
    ok: bool = Field(description="Whether every operation validated.")
    operations: list[OperationResult] = Field(
        description="Per-operation results of the re-validation."
    )
    review_url: str | None = Field(
        description="Where a human reviews and applies or rejects the submitted "
        "change set; null when it stayed a draft."
    )
