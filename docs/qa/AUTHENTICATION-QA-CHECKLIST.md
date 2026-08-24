# Authentication And Production Ingress QA Checklist

Use this checklist for TASK-039G local evidence and later production deployment
records. Record date, tester, application commit and evidence location. Never
paste codes, tokens, cookies, client secrets, CSRF values, names or personal
email into the record. Preserve valid completed evidence when updating an
in-progress record.

This checklist does not authorize a production deployment, Entra/Coolify
mutation, tag operation, backup/restore operation or production QA. Those
actions require their own human approval.

Preserved TASK-039G evidence: the checks marked complete below were run for
commit `dc186e5fb566ed094460b7536634f971771c1a9b` on 2026-08-21 by
`@jonatanska`. The recorded CI run is
`https://github.com/reflector-oy/schatten/actions/runs/32473565343`.
No issues were reported.

## Local Automated Baseline

- [x] Backend Ruff, full pytest and pyright pass.
- [x] Frontend lint, full tests and production build pass.
- [x] Backend and frontend production images build from the documented contexts.
- [x] `.github/scripts/verify-production-compose.sh` passes and missing required
      auth/proxy variables make Compose configuration fail.
- [x] `.github/scripts/verify-production-frontend.sh` passes.
- [x] The release-migration failure test proves that backend does not start.
- [x] Both authentication PlantUML sources render to committed SVGs.

## Broad Local Authentik QA

Run this section against repository-managed local Authentik and disposable local
data. It is the comprehensive security baseline; do not repeat it against
production.

- [x] Consultant login, clean callback `303`, session restoration and logout pass.
- [x] Admin login, clean callback `303`, session restoration and logout pass.
- [x] The database role—not provider groups or claims—controls Users access.
- [x] An unprovisioned/missing-email first link fails generically and creates no
      User, identity or session.
- [x] After first link, changed provider email does not change the permanent
      exact `(issuer, subject)` binding.
- [x] Wrong issuer/tenant metadata fails closed before session creation.
- [x] Login callback replay, swapped browser binding and expired transaction fail.
- [x] More than five live transactions for one browser binding returns `429`.
- [x] Login and callback address rate limits return `429` before provider work.
- [x] No access, refresh or ID token appears in URL fragments, localStorage,
      sessionStorage, cookies, application API responses or frontend state.
- [x] The pre-auth cookie is HttpOnly, short-lived, host-only and consumed on the
      first valid callback; the application session uses a fresh unrelated value.
- [x] The production session cookie policy is `__Host-schatten-session`, Secure,
      HttpOnly, SameSite=Strict, host-only and `Path=/`.
- [x] Every authenticated unsafe method, including logout and session
      revocation, rejects missing/wrong CSRF and missing or mismatched Origin.
- [x] Every `/api/v1/auth` response has `Cache-Control: no-store`.
- [x] Success and failure callbacks use a clean local `303`; provider query data
      is absent from redirect history and rendered content.
- [x] External, protocol-relative, backslash, fragment and malformed `return_to`
      values are rejected; logout cannot be redirected by browser input.
- [x] Anonymous business API access returns `401`; consultant Users access
      returns `403`; both roles retain intentional all-organisation access.
- [x] Admin session revocation and soft-deleted User denial take effect on the
      next request.
- [x] Idle and absolute application-session expiry behavior passes locally.

The preserved local run reported no issues, no issues found in manual browser tersting.

## Local Production-Boundary QA

- [x] Only frontend/Caddy has the public application domain; backend, migration
      and database have no public port or domain.
- [x] A Host other than the exact configured application Host is rejected by
      Caddy and by direct FastAPI inspection.
- [x] Browser-supplied forwarded/client-IP headers cannot spoof FastAPI input.
- [x] Only configured edge/Caddy peer CIDRs influence trusted proxy data.
- [x] Caddy logs retain ordinary request metadata while every `code`, `state`,
      `error` and `error_description` value is exactly `REDACTED`.
- [x] Caddy/FastAPI logs contain no provider codes/tokens, secrets, cookies,
      CSRF values or personal email.
- [x] HSTS, Referrer-Policy, nosniff, frame denial and the enforced CSP match the
      repository policy and the built UI works without violations.

The preserved local Caddy ingress evidence reported that all proxy, log and
header checks passed.

## Conditional Local Entra Federation

Complete this section before the first production rollout and for
authentication, provider or OIDC configuration changes after TASK-040 is
available. Use only designated test accounts.

- [ ] Human authorization to access the organisation Entra tenant is recorded.
- [ ] Local Authentik uses its separate local-federation app registration.
- [ ] Login, callback, first identity link, Schatten session, database role
      enforcement and logout pass through Authentik-to-Entra federation.
- [ ] A designated unmatched account fails generically and creates no Schatten
      User, identity or session.
- [ ] Browser storage/network and credential-safe logs expose no provider token,
      secret, code or personal email.
- [ ] Evidence states that this path does not validate Schatten's direct
      production Entra client, callback, secret, issuer or Coolify boundary.

## Production Deployment Gate

Complete a new copy of this section before every production deployment.

- [ ] Local baseline required for this release is green at the target commit.
- [ ] Conditional local federation is green when required by release scope.
- [ ] Release candidate is frozen.
- [ ] Completed production backup identifier is recorded.
- [ ] Latest successful restore-verification evidence location is recorded.
- [ ] Target commit SHA and matching backend/frontend image references are recorded.
- [ ] Current stable annotated SemVer rollback tag, commit and matching image
      references are recorded, or the first-rollout no-previous-release case
      and stop/escalate action are explicit.
- [ ] Explicit human approval for this deployment is recorded.

## Limited Production Entra Smoke

After every approved deployment, use only designated pre-provisioned admin and
consultant accounts and isolated test records.

- [ ] Admin and consultant login, clean callback, session restoration and logout pass.
- [ ] The Schatten database role—not Entra groups/claims—enforces Users access.
- [ ] For the first rollout or an authentication/provider change, a designated
      unmatched account fails generically without creating a session.
- [ ] The smoke result, commit, tester, time, backup identifier and evidence
      location are recorded without identity or credential data.
- [ ] A failure stops the release and invokes the documented application
      rollback decision.

The following are prohibited in production:

- destructive tests or ordinary production-record mutation
- migration failure injection or database rollback experiments
- load, concurrency, rate-limit or denial-of-service testing
- waiting for idle/absolute expiry or broad session lifecycle suites
- broad automated browser/API suites
- intentional Host/proxy spoofing, log-secret injection or other security
  attacks that belong in local QA

## Rollback Evidence

- [ ] The selected stable tag resolves to the recorded commit.
- [ ] Backend and frontend are both mapped to that commit's Coolify image references.
- [ ] Compatibility with already-applied forward migrations is confirmed before
      deploying the older application.
- [ ] No automatic down migration or database restoration is part of application
      rollback.
- [ ] Any database restoration has separate explicit human authorization and
      impact review.

## TASK-039G Sign-Off

- [x] Local Authentik result records date, commit, tester and pass/fail only.
- [x] Documentation and diagrams show local Authentik, optional local Entra
      federation and direct-Entra production only.
- [x] No production deployment, tenant mutation, tag, backup/restore operation,
      production data access or production QA occurred during TASK-039G.

## Accepted Limitations

- There is no staging environment; direct Entra/Coolify compatibility is first
  validated through the limited production smoke.
- Local federation cannot prove the direct production OIDC client.
- There is no organisation membership authorization; all active internal users
  intentionally access all organisations.
- Guarded Entra email matching is accepted only for first linking within the
  small-company, single-tenant administrator trust model.
- There is no back-channel logout, immediate provider revocation, production
  Graph access, refresh token, provider group mapping or SCIM provisioning.
- The in-memory auth rate limiter supports one backend replica in this baseline.
