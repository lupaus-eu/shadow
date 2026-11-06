# TASK-040 Local Authentik Entra Federation Rehearsal

Status: Implemented; manual Entra browser QA pending

## Goal

Allow an explicitly enabled local end-to-end rehearsal where Shadow uses its
normal local Authentik issuer and Authentik delegates user authentication to a
local-only single-tenant Microsoft Entra registration in the same organisation
tenant.

## Requirements

- Keep Authentik as Shadow's issuer; this rehearsal must not masquerade as
  the required limited direct-Entra production smoke.
- Terminate local Authentik TLS at a pinned Caddy service on
  `https://auth.localhost:9443`, bound only to loopback.
- Generate a gitignored local CA and certificate without automatically changing
  host trust. Trust the CA inside the backend container before OIDC startup.
- Keep Entra IDs, client secret and test-user email in a gitignored environment
  file and require the single-tenant overlay explicitly.
- Provision an Entra OAuth source, source login button and verified-email
  mapping without group synchronization or application-role mapping.
- Pre-provision the matching active Shadow user; Shadow's database remains
  the only application-role source.
- Keep all Authentik and local Entra federation services and credentials out of
  production, release and Coolify manifests.

## Acceptance Criteria

- [x] Local Authentik discovery advertises the exact HTTPS issuer.
- [x] The backend trusts only the generated public local CA certificate; Caddy
      cannot read the CA private key.
- [x] The optional Compose overlay fails closed when any Entra credential is
      missing and provisions the source in dependency order from
      version-controlled configuration.
- [x] Setup and verification scripts do not print or track private Entra values.
- [x] Documentation covers CA trust, Entra redirect URI, startup, allowlist
      provisioning, browser testing, negative testing and cleanup.
- [ ] Human-authorized browser login/logout and negative-account QA completed.

## Out Of Scope

- Production Authentik or production Entra changes.
- Replacing the human-approved limited direct-Entra production smoke.
- Entra groups, roles, SCIM, refresh tokens or Graph permissions beyond the
  Authentik Entra source's delegated `User.Read` profile lookup.
