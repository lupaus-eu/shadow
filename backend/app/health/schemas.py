from pydantic import Field

from app.core.schemas import StrictBaseModel


class HealthResponse(StrictBaseModel):
    status: str = Field(default="ok", description="Service health status.")
