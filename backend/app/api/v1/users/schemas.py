from typing import Literal

from pydantic import Field, field_validator

from app.core.schemas import StrictBaseModel

UserRole = Literal["consultant", "admin"]


class UserCreateRequest(StrictBaseModel):
    name: str = Field(min_length=1, description="User display name.")
    email: str = Field(min_length=1, description="User email address.")
    role: UserRole = Field(description="Application role.")

    @field_validator("name", "email")
    @classmethod
    def required_text_must_not_be_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Value must not be blank.")
        return stripped


class UserPatchRequest(StrictBaseModel):
    name: str | None = Field(
        default=None,
        min_length=1,
        description="User display name.",
    )
    role: UserRole | None = Field(default=None, description="Application role.")
    email: str | None = Field(default=None, description="User email address.")

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None

        stripped = value.strip()
        if not stripped:
            raise ValueError("User name must not be blank.")
        return stripped

    @field_validator("email")
    @classmethod
    def email_must_not_be_null_or_blank(cls, value: str | None) -> str:
        if value is None:
            raise ValueError("User email must not be null.")

        stripped = value.strip()
        if not stripped:
            raise ValueError("User email must not be blank.")
        return stripped


class UserResponse(StrictBaseModel):
    id: int = Field(description="Internal user identifier.")
    name: str = Field(description="User display name.")
    email: str = Field(description="User email address.")
    role: UserRole = Field(description="Application role.")
