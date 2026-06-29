from pydantic import Field, field_validator

from app.core.schemas import StrictBaseModel


class OrganisationCreateRequest(StrictBaseModel):
    name: str = Field(min_length=1, description="Organisation display name.")

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Organisation name must not be blank.")
        return stripped


class OrganisationPatchRequest(StrictBaseModel):
    name: str | None = Field(
        default=None,
        min_length=1,
        description="Organisation display name.",
    )

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None

        stripped = value.strip()
        if not stripped:
            raise ValueError("Organisation name must not be blank.")
        return stripped


class OrganisationResponse(StrictBaseModel):
    id: str = Field(description="Stable organisation key.")
    name: str = Field(description="Organisation display name.")
