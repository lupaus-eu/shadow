from datetime import date

from pydantic import Field

from app.core.schemas import StrictBaseModel


class ScenarioResponse(StrictBaseModel):
    id: str = Field(description="Stable scenario key.")
    name: str = Field(description="Scenario display name.")
    description: str = Field(description="Scenario description.")
    protected: bool = Field(description="Whether the scenario is protected.")


class OrgStateResponse(StrictBaseModel):
    id: str = Field(description="Stable organisation state key.")
    name: str = Field(description="Organisation state display name.")
    description: str = Field(description="Organisation state description.")
    target_date: date | None = Field(
        default=None,
        alias="targetDate",
        description="Organisation state target date.",
    )
