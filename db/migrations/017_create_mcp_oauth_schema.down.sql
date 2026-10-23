-- Destructive for every MCP client registration, grant and token.
-- MCP clients must register and authorize again after a later up migration.
DROP TABLE mcp_oauth_tokens;
DROP TABLE mcp_oauth_authorization_requests;
DROP TABLE mcp_oauth_grants;
DROP TABLE mcp_oauth_clients;
