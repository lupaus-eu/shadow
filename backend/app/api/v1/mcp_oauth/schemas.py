from datetime import datetime
from typing import Literal

from pydantic import Field

from app.core.schemas import StrictBaseModel


class OAuthErrorResponse(StrictBaseModel):
    error: str
    error_description: str | None = None


class AuthorizationServerMetadata(StrictBaseModel):
    """RFC 8414 authorization server metadata."""

    issuer: str
    authorization_endpoint: str
    token_endpoint: str
    registration_endpoint: str
    revocation_endpoint: str
    scopes_supported: list[str]
    response_types_supported: list[str]
    response_modes_supported: list[str]
    grant_types_supported: list[str]
    token_endpoint_auth_methods_supported: list[str]
    revocation_endpoint_auth_methods_supported: list[str]
    code_challenge_methods_supported: list[str]
    authorization_response_iss_parameter_supported: bool


class ProtectedResourceMetadata(StrictBaseModel):
    """RFC 9728 protected resource metadata."""

    resource: str
    authorization_servers: list[str]
    scopes_supported: list[str]
    bearer_methods_supported: list[str]


class ClientRegistrationResponse(StrictBaseModel):
    """RFC 7591 client information response for a public client."""

    client_id: str
    client_id_issued_at: int
    client_name: str
    redirect_uris: list[str]
    grant_types: list[str]
    response_types: list[str]
    token_endpoint_auth_method: Literal["none"]


class ConsentRequestResponse(StrictBaseModel):
    clientName: str
    clientNameSelfDeclared: Literal[True] = True
    redirectIsLoopback: bool
    redirectHost: str
    scope: str
    resource: str
    expiresTime: datetime


class ConsentDecisionRequest(StrictBaseModel):
    request: str = Field(min_length=1, max_length=128)


class ConsentDecisionResponse(StrictBaseModel):
    redirectUrl: str
