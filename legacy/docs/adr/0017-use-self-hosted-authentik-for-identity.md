---
status: accepted
---

# Use self-hosted Authentik for identity and remove Microsoft Entra

Shadow signs people in through its own, self-hosted Authentik instance, the same
identity platform as Yearclock, and drops the direct Microsoft Entra sign-in. It
amends [ADR-004](0004-authentication.md) and
[ADR-013](0013-shared-entra-local-https-deployment.md) (the Entra parts), and
[ADR-006](0006-local-authentik-entra-federation.md) becomes historical. The
authentication of MCP clients is decided separately in
[ADR-0023](0023-authorize-mcp-clients-with-a-dedicated-authentik-provider.md).

## Context

Shadow is turning into a multi-tenant service (ADR-016). Customers are other
companies, so the single-tenant Entra registration of the company that runs
Shadow cannot be the identity provider: it admits only that company's staff, and
it offers no registration, invitation or recovery flow for outsiders. Yearclock,
maintained by the same team, already solved this with Authentik (Yearclock
ADR-0004, 0010, 0034, 0036). Shadow's own OIDC code is provider-neutral, and its
session and CSRF core stays; only the identity provider and the account model
around it change.

## Decision

1. **Own Authentik instance.** Shadow runs its own Authentik (pinned to the
   Yearclock-tested version, 2026.8.x) at its own identity host:
   `https://id.shadow.lupaus.eu` in production and `https://id.app.localhost`
   locally. It is a separate instance from Yearclock's, with its own users and
   configuration; one person who uses both products has two accounts. A shared
   instance would need its own decision and host.
2. **Authentik owns credentials, Shadow owns authority.** Authentik handles
   registration, email verification, passkeys, MFA, recovery and identity
   sessions. Shadow links an identity by issuer and subject, keeps its own
   sessions, and decides what a person may do from tenant memberships (ADR-016).
   Authentik groups and claims grant nothing.
3. **Strong authentication for everyone.** Password sign-in always requires a
   second factor (TOTP or a passkey); passkeys are preferred; a user without a
   factor must set one up before sign-in completes. Recovery needs email plus a
   factor.
4. **Closed enrollment (invitation beta).** Authentik enrollment needs an
   invitation (`AUTHENTIK_ENROLLMENT_OPEN=false`) in production; locally it is
   open. The operator issues invitations; tenant invitations (ticket 083A) come
   later and are separate.
5. **Verified email.** Enrollment verifies the email address and records that in
   a user attribute that the `email` scope exposes as `email_verified`; Shadow
   requires `email_verified` (`OIDC_REQUIRE_VERIFIED_EMAIL=true`). This replaces
   Entra's no-`email_verified` rule.
6. **Web client.** One confidential OIDC client, authorization code with PKCE,
   exact redirect and logout URIs, `sub_mode: hashed_user_id`, issuer mode
   `per_provider`. The backend discovers the provider through an internal base
   URL (`OIDC_INTERNAL_BASE_URL`) while the public issuer stays the one the
   browser sees, and logs out with `id_token_hint`.
7. **Entra is removed completely**: the allow-list of `login.microsoftonline.com`,
   the setup scripts, the documentation and the tests. Existing Users keep
   working: on their first Authentik sign-in the guarded linking by verified
   email attaches the new identity to their existing account, so their data and
   history are kept. The Entra app registration is deleted only after the
   production cutover has been approved (step 087B of the SaaS plan).
8. **Infrastructure.** Authentik server, worker and a one-shot configuration job
   run beside the application; Authentik uses its own logical database `authentik`
   in the same PostgreSQL container, with its own role and credentials
   (Yearclock ADR-0011). Its mail goes through the same transport as the
   application's: Mailpit locally, Scaleway Transactional Email in production.
   Configuration is applied from blueprints stored in the repository.
9. **Authentik runs as an operated service.** The version is pinned, upgrades
   follow a runbook, and both the Authentik database and the production env file
   are part of the backups (ADR-021, step 086B).

## Consequences

- Shadow takes on running identity infrastructure (upgrades, backups, the
  invitation workflow) in exchange for tenant-ready sign-in, MFA and recovery
  without a per-user hosted-authentication fee.
- A new person can sign in only after an invitation and a verified email; a
  person known to Shadow by email is linked on first sign-in, so the sign-in of
  existing Users survives the switch if their Authentik email matches.
- The local stack grows by three Authentik containers and a local identity host;
  Caddy and its certificate gain `id.app.localhost`.
- The dev Users come from an Authentik blueprint that exists only in the local
  Compose project.
- Production still requires its own steps (identity host DNS, Authentik in the
  production Compose, backups); they belong to steps 086A to 087B.
- **No production release between the backend switch and the cutover.** From ticket
  `authentik-sign-in/03` the backend accepts only Authentik issuers and requires a verified
  email, so a release built from `main` fails to start with today's Entra configuration.
  Production stays on the last Entra release (`v0.2.0` line) until Authentik runs in
  production (steps 086A to 087B); the human does not tag a release from `main` before
  then.
- The ID token of a sign-in is kept with its session for `id_token_hint` and is deleted with
  it. Authentik logs the request line of the sign-out, which carries that token (email,
  name); a POST-based sign-out would avoid it and is a recorded follow-up.
- Rejected: keeping Entra next to Authentik (two identity providers to link and
  test, no gain), a shared Authentik with Yearclock (couples the two products'
  upgrades, outages and invitation policy), and a hosted identity service (a
  per-user fee and no passkey control).

Amends ADR-004 and ADR-013 (Entra parts); ADR-006 is historical.
