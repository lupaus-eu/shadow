-- Destructive for every pending request, grant and token of the single
-- <origin>/api/mcp resource: they cannot satisfy migration 017's one scope per
-- resource. A change set keeps its client_id and client_name, and its grant_id
-- becomes null. Clients stay; Users connect the read and write resources again.
DELETE FROM mcp_oauth_authorization_requests;

DELETE FROM mcp_oauth_tokens
WHERE grant_id IN (
    SELECT grant_id
    FROM mcp_oauth_grants
    WHERE resource LIKE '%/api/mcp'
);

DELETE FROM mcp_oauth_grants
WHERE resource LIKE '%/api/mcp';

ALTER TABLE mcp_oauth_authorization_requests
    DROP CONSTRAINT ck_mcp_oauth_authorization_requests_resource,
    DROP CONSTRAINT ck_mcp_oauth_authorization_requests_scope;

ALTER TABLE mcp_oauth_authorization_requests
    ADD CONSTRAINT ck_mcp_oauth_authorization_requests_scope
        CHECK (scopes IN ('schatten.read', 'schatten.write')),
    ADD CONSTRAINT ck_mcp_oauth_authorization_requests_scope_resource
        CHECK (
            (scopes = 'schatten.read' AND resource LIKE '%/api/mcp/read')
            OR (scopes = 'schatten.write' AND resource LIKE '%/api/mcp/write')
        );

ALTER TABLE mcp_oauth_grants
    DROP CONSTRAINT ck_mcp_oauth_grants_resource,
    DROP CONSTRAINT ck_mcp_oauth_grants_scope;

ALTER TABLE mcp_oauth_grants
    ADD CONSTRAINT ck_mcp_oauth_grants_scope
        CHECK (scopes IN ('schatten.read', 'schatten.write')),
    ADD CONSTRAINT ck_mcp_oauth_grants_scope_resource
        CHECK (
            (scopes = 'schatten.read' AND resource LIKE '%/api/mcp/read')
            OR (scopes = 'schatten.write' AND resource LIKE '%/api/mcp/write')
        );
