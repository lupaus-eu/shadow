-- ADR-015 amendment (TASK-074): one MCP resource, <origin>/api/mcp, carries
-- both scopes. Every grant holds shadow.read; shadow.write is optional.
-- Grants of the removed /api/mcp/read and /api/mcp/write resources are deleted
-- as lazy cleanup deletes them: their tokens go first, and a change set keeps
-- its copied client_id and client_name as the audit record while its grant_id
-- becomes null. Each User connects the new resource once. Clients stay until
-- stale-client cleanup removes them.

-- Pending requests expire within minutes, so none is carried over.
DELETE FROM mcp_oauth_authorization_requests;

DELETE FROM mcp_oauth_tokens
WHERE grant_id IN (
    SELECT grant_id
    FROM mcp_oauth_grants
    WHERE resource NOT LIKE '%/api/mcp'
);

DELETE FROM mcp_oauth_grants
WHERE resource NOT LIKE '%/api/mcp';

ALTER TABLE mcp_oauth_grants
    DROP CONSTRAINT ck_mcp_oauth_grants_scope_resource,
    DROP CONSTRAINT ck_mcp_oauth_grants_scope;

ALTER TABLE mcp_oauth_grants
    ADD CONSTRAINT ck_mcp_oauth_grants_scope
        CHECK (scopes IN ('shadow.read', 'shadow.read shadow.write')),
    ADD CONSTRAINT ck_mcp_oauth_grants_resource
        CHECK (resource LIKE '%/api/mcp');

ALTER TABLE mcp_oauth_authorization_requests
    DROP CONSTRAINT ck_mcp_oauth_authorization_requests_scope_resource,
    DROP CONSTRAINT ck_mcp_oauth_authorization_requests_scope;

ALTER TABLE mcp_oauth_authorization_requests
    ADD CONSTRAINT ck_mcp_oauth_authorization_requests_scope
        CHECK (scopes IN ('shadow.read', 'shadow.read shadow.write')),
    ADD CONSTRAINT ck_mcp_oauth_authorization_requests_resource
        CHECK (resource LIKE '%/api/mcp');
