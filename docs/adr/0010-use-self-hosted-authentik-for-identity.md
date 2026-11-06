---
status: accepted
---

# Use self-hosted Authentik for identity

Yearclock uses self-hosted Authentik as its identity provider through OpenID Connect. Authentik owns credentials, passkeys, MFA, recovery, and identity sessions, while Yearclock links identities by stable issuer and subject identifiers and remains authoritative for Organizations, memberships, roles, billing, and product entitlements. This preserves the strong-authentication policy without a per-user hosted-authentication fee, accepting the operational responsibility of running identity infrastructure.

Refined by ADR-0036 (upgrade to Authentik 2026.8).
