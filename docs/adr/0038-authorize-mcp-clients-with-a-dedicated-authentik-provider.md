---
status: accepted
---

# Authorize MCP clients with a dedicated Authentik provider

## Context

ADR-0037 makes the MCP interface an OAuth resource server whose access tokens come
from Authentik and whose audience must be the MCP resource. The MCP authorization
specification expects clients to send the RFC 8707 `resource` parameter and to
register through Client ID Metadata Documents or dynamic client registration. The
authorization model was tested on the local Authentik 2026.8.5 (ticket 01 of
`tech-mcp-interface`), by calls to a throwaway provider and by reading the server
source. Results:

- **`resource` (RFC 8707) is not implemented.** The authorization and token endpoints
  ignore it (the token's `aud` is unchanged); token exchange refuses it with
  `invalid_target`. The access token is a JWT whose `aud` is the **client id of the
  provider that issued it**, and whose `iss` is that provider's issuer.
- **Client ID Metadata Documents are not supported** (no code, no metadata flag).
- **Dynamic client registration works but is not anonymous.** Once enabled on a
  provider, discovery advertises `registration_endpoint`, but registering needs a
  Bearer access token carrying the `goauthentik.io/oidc/dcr` scope from a user who
  passes the application's policies; an anonymous request gets `401`. Every
  registration creates a new Provider and Application, each with its own issuer
  (`/application/o/<slug>/`).
- **Discovery:** each provider serves OIDC discovery at its issuer and the
  RFC 8414 path-insertion form (`/.well-known/oauth-authorization-server/application/o/<slug>/`);
  nothing is served at `/.well-known/oauth-authorization-server`.
- **Identity:** with `sub_mode: hashed_user_id`, `sub` is derived from the user, not the
  provider, so it is the same in every provider on the instance. The issuer differs
  per provider, and Yearclock links a User Account by issuer **and** subject
  (ADR-0010).
- Claude's custom connector has OAuth client ID and client secret fields, so a
  pre-registered client can be configured by hand (confirmed by the owner). Not tested:
  a complete authorization-code sign-in by a real MCP client.

## Decision

- **One dedicated provider and application for MCP**, created by an Authentik blueprint
  next to the Yearclock one: a **confidential** client (client id and secret, entered into the MCP client's
  connector settings) with PKCE, authorization-code and refresh-token grants, strict redirect URIs for the supported MCP clients (and a
  loopback pattern for local clients), `sub_mode: hashed_user_id`, `issuer_mode:
  per_provider`, and the same authorization and invalidation flows as the web
  provider, so MFA policy applies unchanged.
- **The audience is that provider's client id.** The MCP verifier requires `aud` to
  equal the configured MCP client id (`MCP_OIDC_CLIENT_ID`) and `iss` to equal the MCP
  provider's issuer (`MCP_OIDC_ISSUER`), and verifies signature through that
  provider's JWKS. Tokens issued to the web provider, or to any other client, are
  refused. This replaces the RFC 8707 audience check, which Authentik cannot do.
- **Clients are pre-registered, never self-registered.** The client id and secret are
  given to the person connecting, and signing in always needs an existing Yearclock
  account (Authentik enrollment by invitation, ADR-0034). Dynamic client registration
  is not enabled: it needs a token a client does not have, creates a provider per
  client, and each of those has a different issuer. The secret is stored as a
  secret, never in the repository; a public client is used only if an MCP client
  cannot hold a secret, and is then a new decision.
- **Issuer alias in Yearclock.** The MCP token's `iss` differs from the web provider's,
  so the user lookup resolves a token from the configured MCP issuer to the account
  stored under the canonical `OIDC_ISSUER` with the same `sub`. Only the one
  configured MCP issuer is aliased, and only the audience-checked token reaches the
  lookup; an unknown subject still gets no account and no access.
- **The client secret is shared and held in configuration.** It lives in
  `MCP_OIDC_CLIENT_SECRET` (and the blueprint), not in the database. Owners and Admins
  see the connection details in the application (ticket 04 of `tech-mcp-interface`);
  before that, the operator hands them out. Because one secret serves every
  Organization, it does not separate customers; isolation comes from the signed-in
  user's membership, the explicit Organization argument, and the Organization-level
  kill switch. A client per Organization is a later decision if customers need it.
- **No OAuth gateway or facade.** A layer that advertises anonymous registration and
  the missing metadata is needed only by clients that cannot be configured by hand;
  none is in scope. It would be a separate decision.
- Token exchange, DPoP, and the `goauthentik.io/oidc/dcr` scope stay unused.

## Consequences

- The MCP interface works with clients that accept a pre-registered client id and
  secret, such as Claude's custom connector; clients that only support anonymous
  registration cannot connect. Ticket 02 tests MCP Inspector and the Claude connector.
- A second provider means a second client id, issuer, and redirect list to maintain in
  `authentik/blueprints/`, and two new settings in `.env.example` and
  `.env.production.example`.
- The issuer alias is the only change to the identity link; it is one explicit
  setting, covered by a test that an MCP token and a web login for the same Authentik
  user reach the same User Account, and that neither a web token nor an unlisted issuer
  is accepted by the MCP verifier.
- The protected-resource metadata names the MCP provider's issuer as the authorization
  server.
- Should Authentik later add RFC 8707 or Client ID Metadata Documents, this ADR is
  revisited; the verifier keeps its audience check either way.
- Refines ADR-0037 and ADR-0010. Does not change ADR-0036.
