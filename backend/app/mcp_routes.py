"""Connecting an agent: the information page and the Organization switch (ADR-0037, ADR-0038).

Owners and Admins see how to connect an agent (server address, client id, and, on request,
the shared client secret) and can turn MCP off for their Organization. The operator can
block MCP for an Organization from the Platform area; the Organization cannot lift that.
"""

from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session, sessionmaker

from app.access import is_manager
from app.audit import AuditEventDraft, record_audit_event
from app.auth import AuthenticatedUser
from app.auth_routes import AuthenticatedUserDependency
from app.mcp_server.settings import McpSettings
from app.models import Organization
from app.organization_context_routes import _organization_session


class McpConnectionResponse(BaseModel):
    interface_available: bool
    enabled: bool
    platform_blocked: bool
    server_url: str
    client_id: str
    secret_configured: bool


class McpSwitchRequest(BaseModel):
    enabled: bool


class McpSecretResponse(BaseModel):
    client_secret: str


def _request_id(request: Request) -> str:
    return (request.headers.get("X-Request-ID") or str(uuid4()))[:120]


def create_mcp_router(*, session_factory: sessionmaker[Session], authenticated_user_dependency: AuthenticatedUserDependency, settings: McpSettings) -> APIRouter:
    router = APIRouter(prefix="/api/v1/organizations", tags=["MCP"])

    def managed(session: Session, membership, organization_id: UUID) -> Organization:
        if not is_manager(membership):
            raise HTTPException(status_code=403, detail="Owner or Admin required")
        organization = session.get(Organization, organization_id)
        if organization is None:
            raise HTTPException(status_code=404, detail="organization not found")
        return organization

    def response_for(organization: Organization) -> McpConnectionResponse:
        return McpConnectionResponse(
            interface_available=settings.enabled,
            enabled=organization.mcp_enabled,
            platform_blocked=organization.mcp_platform_blocked,
            server_url=settings.resource_url,
            client_id=settings.client_id,
            secret_configured=bool(settings.client_secret),
        )

    @router.get("/{organization_id}/mcp", response_model=McpConnectionResponse)
    def connection(organization_id: UUID, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> McpConnectionResponse:
        with _organization_session(session_factory, organization_id=organization_id, authenticated_user=user) as (session, membership):
            return response_for(managed(session, membership, organization_id))

    @router.patch("/{organization_id}/mcp", response_model=McpConnectionResponse)
    def switch(organization_id: UUID, body: McpSwitchRequest, request: Request, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> McpConnectionResponse:
        """Turn MCP on or off for the Organization; allowed in every subscription state, since turning it off must always work."""
        with _organization_session(session_factory, organization_id=organization_id, authenticated_user=user) as (session, membership):
            organization = managed(session, membership, organization_id)
            if organization.mcp_enabled != body.enabled:
                organization.mcp_enabled = body.enabled
                record_audit_event(session, AuditEventDraft(action="mcp.enabled" if body.enabled else "mcp.disabled", target_type="organization", target_id=organization_id, request_id=_request_id(request), change_summary={}))
            return response_for(organization)

    @router.post("/{organization_id}/mcp/secret", response_model=McpSecretResponse)
    def reveal_secret(organization_id: UUID, request: Request, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> McpSecretResponse:
        """Show the shared client secret to an Owner or Admin; every reveal is audited and the secret is never logged."""
        with _organization_session(session_factory, organization_id=organization_id, authenticated_user=user) as (session, membership):
            managed(session, membership, organization_id)
            if not settings.client_secret:
                raise HTTPException(status_code=404, detail="the MCP client secret is not configured")
            record_audit_event(session, AuditEventDraft(action="mcp.secret_revealed", target_type="organization", target_id=organization_id, request_id=_request_id(request), change_summary={}))
            return McpSecretResponse(client_secret=settings.client_secret)

    return router
