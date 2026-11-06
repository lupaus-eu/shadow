---
status: accepted
---

# Authorize MCP clients with a dedicated Authentik provider

Shadow's MCP endpoint (`/api/mcp`) stops being its own OAuth authorization
server and becomes an OAuth resource server that accepts access tokens issued by
a dedicated Authentik provider. It replaces the OAuth server part of
[ADR-015](0015-ai-via-mcp.md); the MCP server, its tools, prompts, skills and the
human-applied change sets are unchanged. It follows Yearclock ADR-0037 and
ADR-0038.

## Context

ADR-015 made Shadow its own OAuth 2.1 authorization server on top of the Entra
cookie session: dynamic client registration, consent, token issue and revoke,
four `mcp_oauth_*` tables. That server cannot outlive the move to Authentik and
tenants (ADR-016, ADR-017): it would re-implement an identity provider's job and
would need tenant binding of its own. Yearclock tested Authentik 2026.8.5 for
exactly this (its ADR-0038):

- the `resource` parameter (RFC 8707) is ignored; a token's `aud` is the client id
  of the provider that issued it, and `iss` is that provider's issuer;
- Client ID Metadata Documents are not supported;
- dynamic client registration works only with a token a client does not have;
- with `sub_mode: hashed_user_id` the `sub` is the same in every provider of the
  instance, while the issuer differs per provider;
- Claude's custom connector has OAuth client id and client secret fields, so a
  pre-registered client can be configured by hand.

## Decision

1. **One dedicated provider and application for MCP** (blueprint
   `shadow-mcp-application`): a confidential client with PKCE, authorization code
   and refresh token grants, explicit user consent, scopes `openid profile
   offline_access`, `sub_mode: hashed_user_id`, issuer mode `per_provider`, and
   the same authentication flows as the web provider, so the MFA policy applies
   unchanged.
2. **The audience is the provider's client id.** The MCP verifier requires `aud`
   equal to `MCP_OIDC_CLIENT_ID` and `iss` equal to `MCP_OIDC_ISSUER`, and checks
   the signature with that provider's JWKS. Tokens of the web provider or of any
   other client are refused.
3. **Clients are pre-registered, never self-registered.** The client id and secret
   are handed to the person connecting (claude.ai custom connector, Claude Code,
   Claude Desktop). Redirect URIs are strict: the claude.ai and claude.com
   callbacks, plus the loopback callbacks of local clients such as Claude Code
   (`http://localhost:<port>/callback`, matched as a pattern; the port can be
   pinned with `--callback-port`). Dynamic registration stays off. A public client or an OAuth facade is a
   separate decision, needed only if a supported client cannot hold a secret.
4. **Identity.** A token from the configured MCP issuer is resolved to the
   existing `customer` account stored under the canonical web issuer
   (`OIDC_ISSUER`) with the same `sub`. An account is never created from a token;
   an unknown subject gets no access.
5. **Authority comes from tenants, not scopes.** What a token may do is decided
   from the person's tenant membership and the tenant's MCP switches (ADR-016),
   with an explicit tenant argument on every tool. The `shadow.read` and
   `shadow.write` scopes and `ROLE_SCOPES` of ADR-015 are retired.
6. **One shared secret.** The client secret lives in configuration
   (`MCP_OIDC_CLIENT_SECRET`), not in the database. It does not separate tenants;
   isolation comes from membership, the tenant argument and the tenant's switch.
   Revoking one connection means removing the membership or blocking the
   Authentik user; an issued token works until it expires.
7. **Sequence.** The provider and its blueprint arrive with the Authentik setup
   (ticket `authentik-sign-in/02`), because they are Authentik configuration.
   The token verification, the tenant binding and the removal of the old OAuth
   server follow in steps 080I to 080K of the SaaS plan; until then the old
   server keeps working.

## Consequences

- Every existing MCP connection breaks at cutover: each user connects again with
  the client id and secret. Instructions and an announcement go out before the
  cutover (step 087A tests the reconnection).
- A second provider means a second issuer, client id and redirect list to
  maintain next to the web provider; two settings pairs go to `.env.example` and
  the production env contract.
- Clients that only support anonymous registration cannot connect. Claude Code
  documents pre-registered clients (`claude mcp add --client-id --client-secret
  --callback-port`) and the claude.ai custom connector takes a client id and
  secret. Ticket `authentik-sign-in/02` verified the provider with a scripted
  pre-registered client on 2026-11-06 (consent, loopback code with PKCE, audience and
  issuer, refresh, refused redirect URIs); a session with the real clients is still to
  be done before the verifier work starts. The documentation
  confirms the claude.ai callback `https://claude.ai/api/mcp/auth_callback` only;
  the claude.com callback is kept from Yearclock's production-tested blueprint. A
  failing client means a new decision (public client or facade).
- The `mcp_oauth_*` tables, `/api/oauth/*` endpoints, the consent page and the
  connections UI are removed in step 080K.
- Should Authentik later implement RFC 8707 or Client ID Metadata Documents, this
  ADR is revisited; the audience check stays either way.

Replaces the OAuth server part of ADR-015.
