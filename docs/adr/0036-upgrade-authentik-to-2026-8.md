---
status: accepted
---

# Upgrade Authentik to 2026.8

## Context

Authentik is pinned (ADR-0010, "pinned versions and tested upgrades"). The stack ran
2026.5.6. Release 2026.8 is the first line that includes OAuth 2.0 Dynamic Client
Registration in the open-source edition and token exchange with on-behalf-of
delegation; both are needed for future agent connectors (MCP) to Yearclock and to
sibling applications that share this Authentik. Nothing in the product uses them yet.
2026.8 also changes behavior Yearclock relies on:

- Authentik honours `X-Forwarded-Proto`, `X-Forwarded-Host`, and `X-Forwarded-For`
  only from addresses listed in `AUTHENTIK_LISTEN__TRUSTED_PROXY_CIDRS`. The backend
  sends `X-Forwarded-Proto` over the Compose network so that discovery reports the
  HTTPS issuer (`docs/architecture/authentication.md`), and Caddy sends the forwarded
  headers in production.
- A Base URL setting (`AUTHENTIK_WEB__BASE_URL`) is introduced. It is unused in
  2026.8 and required from 2026.11.
- Authentik does not support downgrades, and upgrades must not skip a release line.

## Decision

- Pin `AUTHENTIK_VERSION` to **2026.8.5** (the latest 2026.8 patch on 2026-11-05) in
  `docker-compose.yml`, `docker-compose.prod.yml`, `.env.example`, and
  `.env.production.example`. 2026.5 to 2026.8 is one release line, so no
  intermediate version is needed; the 2026.5 instance should be on its latest patch
  first.
- Set `AUTHENTIK_LISTEN__TRUSTED_PROXY_CIDRS` explicitly from
  `AUTHENTIK_TRUSTED_PROXY_CIDRS`, defaulting to Authentik's own default (all private
  ranges). The Compose network, which holds `backend` and `caddy`, falls inside it.
  Narrowing it is an operator choice when Docker uses a custom address pool.
- Set `AUTHENTIK_WEB__BASE_URL` from `AUTHENTIK_BASE_URL` now, so the 2026.11 upgrade
  needs no configuration change. Production sets it to the public identity origin.
- Keep the blueprint-driven configuration and the identity-only boundary unchanged.
  Dynamic Client Registration, token exchange, and any MCP authorization remain
  unused and need their own decision and verification (RFC 8707 audience binding and
  Client ID Metadata Documents are not confirmed in Authentik's documentation).
- Follow `docs/runbooks/authentik-upgrade.md` for every Authentik upgrade: back up,
  upgrade, verify, and roll back only by restoring the backup.

## Consequences

- The Authentik database schema is migrated forward on first start and cannot be
  downgraded; the rollback is the pre-upgrade dump plus the previous image tag.
- A misconfigured trusted-proxy list would make Authentik treat HTTPS requests as
  HTTP and break the issuer check; the runbook has a verification step for it.
- 2026.8 adds a required Base URL from 2026.11, which is already configured.
- Refines ADR-0010. Does not change ADR-0011 or ADR-0035.
