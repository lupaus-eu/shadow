"""Cookie-session connections API for MCP grants.

It stays registered with `MCP_ENABLED=false`, so users and administrators can
revoke grants while MCP is disabled (ADR-015 incident procedure).
"""

from fastapi import APIRouter, Depends, Response, status

from app.api.v1.auth.dependencies import (
    AuthHttpError,
    BusinessSessionDependency,
    SessionDependency,
    UnsafeRequestDependency,
    require_business_admin,
)
from app.api.v1.mcp_oauth.schemas import (
    ConnectionResponse,
    UserConnectionsRevokeResponse,
)
from app.api.v1.mcp_oauth.token_service import (
    ConnectionNotFound,
    UserNotFound,
    list_connections,
    revoke_connection,
    revoke_user_connections,
)

router = APIRouter(prefix="/ai", tags=["ai"])


@router.get("/connections", response_model=list[ConnectionResponse])
def get_connections(
    session: SessionDependency,
    active: BusinessSessionDependency,
) -> list[ConnectionResponse]:
    return [
        ConnectionResponse(
            grantKey=connection.grant_key,
            clientId=connection.client_id,
            clientName=connection.client_name,
            scope=connection.scope,
            resource=connection.resource,
            createdTime=connection.created_time,
            lastUsedTime=connection.last_used_time,
            expiresTime=connection.expires_time,
        )
        for connection in list_connections(
            session, user_id=active.user.user_id, role=active.user.role
        )
    ]


@router.delete("/connections/{grant_key}", status_code=status.HTTP_204_NO_CONTENT)
def delete_connection(
    grant_key: str,
    session: SessionDependency,
    active: UnsafeRequestDependency,
) -> Response:
    try:
        revoke_connection(session, grant_key, user_id=active.user.user_id)
    except ConnectionNotFound as exc:
        raise AuthHttpError(
            404, "CONNECTION_NOT_FOUND", "Connection not found"
        ) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/users/{user_id}/connections/revoke",
    response_model=UserConnectionsRevokeResponse,
    dependencies=[Depends(require_business_admin)],
)
def revoke_all_user_connections(
    user_id: int,
    session: SessionDependency,
    active: UnsafeRequestDependency,
) -> UserConnectionsRevokeResponse:
    try:
        revoked = revoke_user_connections(
            session, user_id, admin_user_id=active.user.user_id
        )
    except UserNotFound as exc:
        raise AuthHttpError(404, "USER_NOT_FOUND", "User not found") from exc
    return UserConnectionsRevokeResponse(revokedCount=revoked)
