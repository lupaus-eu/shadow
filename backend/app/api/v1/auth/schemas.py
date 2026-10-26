from typing import Literal

from app.api.v1.users.schemas import UserResponse
from app.core.schemas import StrictBaseModel


class SessionFeatures(StrictBaseModel):
    mcp: bool


class SessionResponse(StrictBaseModel):
    user: UserResponse
    csrfToken: str
    features: SessionFeatures


class LogoutResponse(StrictBaseModel):
    logoutUrl: str | None


class ErrorBody(StrictBaseModel):
    code: str
    message: str


class ErrorResponse(StrictBaseModel):
    error: ErrorBody


class AuthStatus(StrictBaseModel):
    status: Literal["ok"] = "ok"
