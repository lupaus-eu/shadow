import pytest
from pydantic import Field, ValidationError

from app.core.schemas import StrictBaseModel


class ExampleSchema(StrictBaseModel):
    value: str = Field(description="Example value.")


def test_strict_base_model_forbids_extra_fields() -> None:
    with pytest.raises(ValidationError):
        ExampleSchema.model_validate({"value": "ok", "unexpected": "field"})


def test_strict_base_model_populates_by_field_name() -> None:
    model = ExampleSchema(value="ok")

    assert model.value == "ok"
