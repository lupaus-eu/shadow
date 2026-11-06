import re
from datetime import datetime
from typing import Literal

from pydantic import Field, field_validator

from app.core.schemas import StrictBaseModel

CustomerStatus = Literal["active", "archived"]

_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_COUNTRY_CODE_PATTERN = re.compile(r"^[A-Za-z]{2}$")


def _required_text(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("Value must be a string.")
    stripped = value.strip()
    if not stripped:
        raise ValueError("Value must not be blank.")
    return stripped


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("Value must be a string or null.")
    return value.strip() or None


def _optional_email(value: object) -> str | None:
    normalized = _optional_text(value)
    if normalized is None:
        return None
    if len(normalized) > 254 or _EMAIL_PATTERN.fullmatch(normalized) is None:
        raise ValueError("Email must have a valid basic email address shape.")
    return normalized


class CustomerCreateRequest(StrictBaseModel):
    name: str = Field(min_length=1, description="Customer display name.")
    email: str | None = Field(default=None, max_length=254)

    @field_validator("name", mode="before")
    @classmethod
    def normalize_name(cls, value: object) -> str:
        return _required_text(value)

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: object) -> str | None:
        return _optional_email(value)


class CustomerReplaceRequest(CustomerCreateRequest):
    status: CustomerStatus = Field(description="Customer lifecycle status.")


class ContactWriteRequest(StrictBaseModel):
    name: str = Field(min_length=1, description="Contact display name.")
    email: str | None = Field(default=None, max_length=254)
    phone: str | None = Field(default=None)
    job_title: str | None = Field(default=None, alias="jobTitle")

    @field_validator("name", mode="before")
    @classmethod
    def normalize_name(cls, value: object) -> str:
        return _required_text(value)

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: object) -> str | None:
        return _optional_email(value)

    @field_validator("phone", "job_title", mode="before")
    @classmethod
    def normalize_optional_text(cls, value: object) -> str | None:
        return _optional_text(value)


class AddressWriteRequest(StrictBaseModel):
    label: str = Field(min_length=1, description="Address label.")
    address_line_1: str = Field(min_length=1, alias="addressLine1")
    address_line_2: str | None = Field(default=None, alias="addressLine2")
    postal_code: str | None = Field(default=None, alias="postalCode")
    city: str | None = Field(default=None)
    region: str | None = Field(default=None)
    country_code: str = Field(min_length=2, max_length=2, alias="countryCode")

    @field_validator("label", "address_line_1", mode="before")
    @classmethod
    def normalize_required_text(cls, value: object) -> str:
        return _required_text(value)

    @field_validator(
        "address_line_2",
        "postal_code",
        "city",
        "region",
        mode="before",
    )
    @classmethod
    def normalize_optional_text(cls, value: object) -> str | None:
        return _optional_text(value)

    @field_validator("country_code", mode="before")
    @classmethod
    def normalize_country_code(cls, value: object) -> str:
        normalized = _required_text(value)
        if _COUNTRY_CODE_PATTERN.fullmatch(normalized) is None:
            raise ValueError("Country code must contain exactly two ASCII letters.")
        return normalized.upper()


class CustomerResponse(StrictBaseModel):
    id: int
    name: str
    email: str | None
    status: CustomerStatus
    created_at: datetime = Field(serialization_alias="createdAt")
    updated_at: datetime = Field(serialization_alias="updatedAt")


class ContactResponse(StrictBaseModel):
    id: int
    name: str
    email: str | None
    phone: str | None
    job_title: str | None = Field(serialization_alias="jobTitle")
    created_at: datetime = Field(serialization_alias="createdAt")
    updated_at: datetime = Field(serialization_alias="updatedAt")


class AddressResponse(StrictBaseModel):
    id: int
    label: str
    address_line_1: str = Field(serialization_alias="addressLine1")
    address_line_2: str | None = Field(serialization_alias="addressLine2")
    postal_code: str | None = Field(serialization_alias="postalCode")
    city: str | None
    region: str | None
    country_code: str = Field(serialization_alias="countryCode")
    created_at: datetime = Field(serialization_alias="createdAt")
    updated_at: datetime = Field(serialization_alias="updatedAt")
