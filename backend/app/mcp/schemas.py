"""Result envelopes of the MCP read tools that bound or summarise data.

They wrap the existing domain response schemas with the truncation and
summary fields an AI client needs. Field names are what FastMCP serialises.
"""

from datetime import date as dt_date

from pydantic import Field

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
