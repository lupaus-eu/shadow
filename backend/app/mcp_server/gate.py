"""The two switches that stop MCP traffic for one Organization (ticket 04).

``mcp_enabled`` belongs to the Organization's Owners and Admins; ``mcp_platform_blocked``
to the operator. MCP works only while the first is on and the second is off. The web
application is not affected by either.
"""

from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.auth import AuthenticatedUser
from app.database import RequestContext, apply_request_context, transaction_session
from app.models import Organization, OrganizationMembership


def require_mcp_enabled(session_factory: sessionmaker[Session], user: AuthenticatedUser, organization_id: UUID) -> None:
    with transaction_session(session_factory, RequestContext(user_account_id=user.account.id)) as session:
        membership = session.scalar(
            select(OrganizationMembership).where(
                OrganizationMembership.organization_id == organization_id,
                OrganizationMembership.user_account_id == user.account.id,
            )
        )
        if membership is None:
            raise HTTPException(status_code=404, detail="Organization not found")
        apply_request_context(session, RequestContext(user_account_id=user.account.id, organization_id=organization_id))
        organization = session.get(Organization, organization_id)
        if organization is None:
            raise HTTPException(status_code=404, detail="Organization not found")
        if organization.mcp_platform_blocked:
            raise HTTPException(status_code=403, detail="MCP access to this Organization is blocked by the operator")
        if not organization.mcp_enabled:
            raise HTTPException(status_code=403, detail="MCP access to this Organization is turned off by its Owners or Admins")
