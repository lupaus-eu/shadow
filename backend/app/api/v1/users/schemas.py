from typing import Literal

from pydantic import Field, field_validator

from app.core.schemas import StrictBaseModel

UserRole = Literal["consultant", "admin"]


class UserCreateRequest(StrictBaseModel):
    name: str = Field(min_length=1, description="User display name.")
    role: UserRole = Field(description="Application role.")

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("User name must not be blank.")
        return stripped


class UserPatchRequest(StrictBaseModel):
    name: str | None = Field(
        default=None,
        min_length=1,
        description="User display name.",
    )
    role: UserRole | None = Field(default=None, description="Application role.")

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None

        stripped = value.strip()
        if not stripped:
            raise ValueError("User name must not be blank.")
        return stripped


class UserResponse(StrictBaseModel):
    id: int = Field(description="Internal user identifier.")
    name: str = Field(description="User display name.")
    role: UserRole = Field(description="Application role.")
