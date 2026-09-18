# ADR-006: Local Authentik TLS And Optional Entra Federation

Status: Accepted

Date: 2026-08-20

Amended: 2026-08-24 to align with ADR-005's production-only environment model.

Superseded target: amended
[ADR-013](ADR-013-shared-entra-local-https-deployment.md) replaces local Authentik
and federation with direct Entra at `https://app.localhost`, sharing the existing
registration with production using separate secrets. The decisions below remain
historical and describe the still-implemented runtime until TASK-059B. B preserves
existing data, old volumes and identity rows and reuses valid CA material where
possible. Tenant callback/Graph permission cleanup belongs to authorized F setup
only after remaining-consumer checks. Historical federation QA does not verify
the direct-Entra design.

## Context

ADR-004 keeps repository-managed Authentik as Schatten's daily local OIDC
provider. ADR-005 removes staging, integration/pre-production and the dedicated
Entra development tenant: Schatten has only local development/testing and
production, and direct Entra/Coolify compatibility is first validated by a
limited production smoke. A separate local experiment is useful for proving
that Authentik can delegate credential verification to a local-only
single-tenant Entra registration in the same organisation tenant. Microsoft
Entra permits plain HTTP redirect URIs only for bare `localhost`, while Schatten
deliberately uses the cookie-isolated `auth.localhost` host.

## Decision

Local Authentik is exposed only through a pinned Caddy TLS proxy at
`https://auth.localhost:9443`. A repository-generated, gitignored development CA
signs that endpoint; developers explicitly trust its public certificate on the
host, and the backend container installs it before OIDC initialization. The CA
private key is never mounted into a container.

An opt-in Compose overlay provisions a tenant-specific Entra OAuth source in
Authentik through a deterministic one-shot configurator. The backend waits for
that configurator to complete, and the Entra secret is not exposed to the
long-running Authentik worker. The source uses the exact callback
`https://auth.localhost:9443/source/oauth/callback/schatten-auth/`, delegated
`openid`/`User.Read` behavior supplied by Authentik, the Graph `/me` profile
endpoint, source-specific identity matching and no group synchronization. A
source mapping marks a non-empty single-tenant Entra email as verified for the
existing local Schatten claim contract. This is the same limited email trust
accepted by ADR-004; missing email still fails first link.

Schatten continues to see Authentik as its issuer and continues to derive roles
only from its own pre-provisioned Users table. Entra credentials and test-user
email stay in a separate gitignored file. Authentik, the TLS proxy and this
overlay remain absent from release and Coolify manifests.

## Consequences

- The normal local Authentik endpoint is HTTPS and requires one explicit host
  CA-trust step.
- The optional chain proves Authentik-to-Entra federation and Schatten's
  provider-neutral contract, but not Schatten's direct Entra compatibility;
  ADR-005's human-approved limited production smoke remains mandatory.
- Authentik calls Microsoft Graph `/me` with delegated `User.Read` only during
  this optional source flow. No Graph token reaches Schatten or React.
- Authentik logout does not guarantee termination of the upstream Entra browser
  session; repeated login can reuse Entra SSO.

## Related

- `docs/decisions/ADR-004-authentication.md`
- `docs/decisions/ADR-005-production-only-environments.md`
- `tasks/TASK-040-local-authentik-entra-federation.md`
