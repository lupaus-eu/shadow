# ADR-005: Production-Only Deployment Environments

Status: Accepted

Date: 2026-08-21

---

# Context

ADR-003 selected a common Coolify deployment topology for staging and
production. ADR-004 then assigned a dedicated Entra development tenant to
integration/pre-production verification and a separate Entra registration to
production. Before a staging deployment or production release was created, the
team decided that maintaining staging would cost more than it would reduce risk
for Schatten's small product team and user base.

A staging environment can drift from production configuration, identity policy
and data shape, creating misleading confidence. It also adds hosting cost,
credential rotation, backup, monitoring and maintenance work and delays small
releases. Local testing is reproducible and comprehensive, but it cannot prove
the final direct Schatten-to-Entra production integration.

# Decision

Schatten has exactly two application environments:

| Environment | Runtime and identity provider | Purpose |
| --- | --- | --- |
| Local development/testing | Repository-managed Authentik; optionally Authentik federated to Entra by TASK-040 | Daily development, CI-adjacent checks and supplemental provider rehearsal without production application data |
| Production | Coolify release topology with Schatten connecting directly to single-tenant Microsoft Entra ID | Real users and the only deployed application environment |

There is no Schatten staging deployment, pre-production application environment
or dedicated Entra development tenant. Authentik remains absent from every
release manifest.

Local federation and production use separate confidential Web app registrations
in the same organisation Entra tenant. The local registration has only its
local Authentik callback/secret and is restricted to designated test accounts
where tenant policy supports assignment. The production registration has only
the Schatten production callback/logout URIs and production secret. Secrets and
callback sets are not shared. Production Schatten continues to request only
`openid profile email`; any Graph permission required by Authentik's local
source belongs only to the local registration and TASK-040.

Local Authentik-to-Entra federation does not exercise production's direct OIDC
client, issuer, callback, secret or Coolify boundary. It is required before the
first production rollout and after authentication, provider or OIDC
configuration changes, but it is supplemental evidence rather than a substitute
for production validation.

Every production deployment follows the human-controlled workflow in
`docs/DEPLOYMENT.md`:

1. pass CI, image/Compose, migration-gate, ingress/security and local Authentik
   checks
2. run the local federated Entra smoke when the release scope requires it
3. freeze the release and record a completed production backup identifier plus
   the latest successful restore-verification evidence
4. record target and rollback artifacts and obtain explicit human approval
5. deploy the matching commit-specific frontend/backend images
6. run only the limited direct-Entra production smoke with designated accounts
   and isolated test records
7. record credential- and identity-safe evidence

Destructive tests, failure injection, load/rate-limit tests, broad automated
suites, session-expiry waiting and ordinary production-data testing are
prohibited in production.

Stable releases may be marked manually with immutable annotated SemVer tags.
Each rollback reference records its commit SHA and matching commit-specific
frontend/backend images. Application rollback moves both images together and
leaves successful forward migrations in place. An incompatible older
application is not deployed over the forward schema. Database restoration is a
separately authorized human operation and is never automatic.
For the first rollout, absence of an older stable application release is
recorded explicitly; failure stops the application and escalates without an
automatic database restore.

# Partial Supersession

This ADR partially supersedes:

- ADR-003 only where it defines staging alongside production; its Coolify,
  immutable-image, one-shot migration and forward-only rollback decisions remain
  accepted.
- ADR-004 only where it defines integration/pre-production through a dedicated
  Entra development tenant; its OIDC, identity, session, authorization and
  production Entra decisions remain accepted.

Their historical decision text is retained. Active documentation follows this
ADR.

# Consequences

Benefits:

- one deployed application environment to operate, secure, back up and monitor
- no staging drift presented as production-equivalent evidence
- less cost, credential maintenance and release delay
- reproducible local Authentik testing remains available for broad QA

Accepted risks and constraints:

- the direct Entra/Coolify path is first validated by a narrow production smoke
- defects escaping local checks can affect real availability, users or data
- local federation cannot prove direct production client compatibility
- every release needs explicit backup evidence, approval and rollback mapping
- production smoke must stay narrow because production data cannot be used as a
  general QA environment

# Options Considered

## Keep Staging And A Dedicated Entra Development Tenant

Rejected because its operational cost and drift risk outweigh its value for the
current team and user base.

## Share One Entra App Registration

Rejected because local callbacks, credentials and permissions would become
coupled to the production client and increase its configuration and secret blast
radius.

## Skip Direct Production Smoke

Rejected because local Authentik federation does not validate Schatten's direct
production OIDC client and deployment boundary.

# Implementation Rules

- Do not add staging services, domains or credentials to release manifests.
- Do not add Authentik to production manifests.
- Do not automate production deployment, tag creation, database restoration or
  destructive production QA as part of TASK-039G.
- Preserve commit-specific frontend/backend images and the release migration
  failure gate.
- Keep completed historical task decisions unchanged.
- TASK-040 remains a separate task and must use ADR-006 after rebasing onto the
  TASK-039G result.

# References

- `docs/decisions/ADR-003-coolify-deployment.md`
- `docs/decisions/ADR-004-authentication.md`
- `docs/DEPLOYMENT.md`
- `docs/qa/AUTHENTICATION-QA-CHECKLIST.md`
- `tasks/TASK-039G-production-auth-deployment-qa.md`
- `tasks/TASK-040-local-authentik-entra-federation.md` (separate branch)
