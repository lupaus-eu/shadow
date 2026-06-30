from datetime import date

from pydantic import Field, field_validator

from app.core.schemas import StrictBaseModel


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
        description="Stable organisation state key that defines the copy boundary.",
    )
    name: str = Field(min_length=1, description="Copied scenario display name.")
    description: str | None = Field(
        default=None,
        description="Copied scenario description.",
    )

    @field_validator("source_scenario_id", "source_org_state_id", "name")
    @classmethod
    def text_fields_must_not_be_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Value must not be blank.")
        return stripped


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
    target_date: date = Field(
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
    target_date: date | None = Field(
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
    target_date: date = Field(
        alias="targetDate",
        description="Organisation state target date.",
    )
