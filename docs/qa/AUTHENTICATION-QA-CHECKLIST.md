# Authentication And Production Ingress QA Checklist

Use this checklist for TASK-039G local evidence and later production deployment
records. Record date, tester, application commit and evidence location. Never
paste codes, tokens, cookies, client secrets, CSRF values, names or personal
email into the record. Preserve valid completed evidence when updating an
in-progress record.

This checklist does not authorize a production deployment, Entra/UpCloud
mutation, tag operation, backup/restore operation or production QA. Those
actions require their own human approval.

Preserved TASK-039G evidence: the checks marked complete below were run for
commit `dc186e5fb566ed094460b7536634f971771c1a9b` on 2026-08-21 by
`@jonatanska`. The recorded CI run is
`https://github.com/reflector-oy/schatten/actions/runs/32473565343`.
No issues were reported.

Architecture amendment: [ADR-013](../decisions/ADR-013-shared-entra-local-https-deployment.md)
selects direct Entra in both environments, UpCloud Ubuntu 26.04 LTS, direct
Caddy TLS and private Docker PostgreSQL 18. Initial release requires daily
encrypted on-server backups with 7-day retention and backup/restore evidence. All checked
TASK-039G/TASK-040 results below are historical, including their platform,
registration and federation assumptions. They do not verify this target.
New simulated-OIDC/Compose and live Entra evidence belongs to B/G/E/F; the
pending production gates below reflect the amended plan and are executed with
[the production runbook](../PRODUCTION-RUNBOOK.md).

## TASK-059B Direct-Entra Local Evidence

- [x] Authorized real-Entra browser verification records login, clean callback,
      guarded first-link, session role, logout and existing-identity login.
      Simulated OIDC tests are not used as this evidence.
- [x] The trusted local application certificate and `wss://app.localhost` HMR
      were verified in a browser after local provider setup.
- [x] Automated and local checks verified the exact Entra issuer,
      missing-email rejection, no
      `email_verified` requirement, pre-provisioned-only linking, existing
      identity login, session/CSRF/logout behavior, header spoof rejection and
      callback-log redaction using the TASK-059B automated and local checks.

Recorded on 2026-09-24 by `@jonatanska` against the local
`https://app.localhost` environment with Chromium `135`. Steps 1-8 tested
application commit `bc082576d414def6bb4dff9db50ed6c47ddcdca4`. Step 9 exposed a
CSRF-header logging defect; the corrected log boundary was verified at fix
commit `3d6ffb45e3ce7f05464626a37db728cb7988ae50`. The associated CI evidence is
[run 35362139899](https://github.com/reflector-oy/schatten/actions/runs/35362139899).

### Step 1 — Test baseline

**Result: PASS.** The clean baseline was recorded at
`bc082576d414def6bb4dff9db50ed6c47ddcdca4` on
2026-09-24 at 09:44:42 EEST on branch
`feature/TASK-059B-local-https-direct-entra`. The tester, browser and CI evidence
are identified above.

### Step 2 — Local TLS initialization and trust

**Result: PASS.** `make dev-init` completed without exposing private values.
Both `.env.entra.local` and the application leaf private key had mode `600`.
The reused Schatten development CA was trusted by the host and browser; only
the public CA certificate was imported.

### Step 3 — Stack startup and configuration

**Result: PASS.** `make dev-up` completed, the local direct-Entra verifier
passed, the database/backend/frontend services were running, the prediction
worker was healthy, and `https://app.localhost/health` returned `OK` through
local Caddy.

### Step 4 — Designated administrator provisioning

**Result: PASS.** Interactive local-only provisioning created or verified the
designated active administrator without recording personal input. The database
role was `admin`, and no direct-Entra identity existed before the first-link
browser run.

### Step 5 — Browser TLS, headers and HMR

**Result: PASS.** The browser trusted the `app.localhost` certificate without a
warning. HSTS, Referrer-Policy, nosniff, frame denial and the enforced CSP were
present with no CSP console errors. The Vite client connected over
`wss://app.localhost` on port 443 with status `101`, and a temporary visible
source edit updated through HMR without a full reload. The edit was reverted.

### Step 6 — Real Entra first link and callback

**Result: PASS.** The designated account reached the expected tenant, completed
authentication, returned through a clean `303` callback and landed on a clean
Schatten URL without provider query data. The application rendered normally,
showed the database-backed Admin role and exposed the authorized Users
navigation.

### Step 7 — Session and guarded-link persistence

**Result: PASS.** Reload restored the session and the session endpoint returned
`200`. The `__Host-schatten-session` cookie was Secure, HttpOnly,
SameSite=Strict, host-only and scoped to `Path=/`; the pre-authentication cookie
was consumed. Browser URLs and storage exposed no provider tokens. The database
contained exactly one direct-Entra identity for the designated User after the
first link, with existing Authentik identities and unrelated Users unchanged.

### Step 8 — Logout and existing-identity login

**Result: PASS.** Authenticated logout carried Origin and CSRF headers,
removed the application session cookie and caused the session endpoint to
return `401`. Entra returned the browser to `/login`; Chromium displayed a harmless
empty trailing fragment (`#`). A second login used the existing identity,
restored the Admin role and left the direct-Entra identity count at exactly one.
The second logout also succeeded.

### Step 9 — Credential-safe logs

**Result: PASS after fix.** The initial run found that local Caddy logged the
CSRF request-header value; no sensitive value is reproduced in this record.
Commit `3d6ffb45e3ce7f05464626a37db728cb7988ae50` added local and production
Caddy redaction plus regression coverage. After reload, a credential-safe live
probe found zero exposures of its dummy value and one correctly redacted logout
entry. Callback query values were redacted by Caddy, backend callback access
logs contained no callback query, and the inspected logs contained no provider
tokens, secrets, cookies, CSRF values or personal email.

This verification performed no production operation, schema change, volume
deletion, manual identity rewrite, callback cleanup, Graph permission removal
or other Entra/UpCloud mutation. The normal guarded first-link write and local
administrator provisioning were the only identity/User changes in scope.

## TASK-059E Integrated Evidence

TASK-059E did not repeat the live browser run above; that TASK-059B record
remains the separately recorded real local direct-Entra evidence. Before each
production release F confirms that it still covers the release's
authentication scope, or records a new authorized run. Local success does not
establish production DNS, TLS or client-secret correctness, and the production
gate and smoke below remain pending F.

On 2026-09-28 E reran the automated/simulated boundary with no tenant secrets
(details in [UPCLOUD-RUNBOOK-QA.md](UPCLOUD-RUNBOOK-QA.md)):

- [x] Full backend suite, including the PostgreSQL auth, reference-seed parity
      and bootstrap integration suites, against disposable PostgreSQL 18.
- [x] Local direct-Entra Compose check with synthetic configuration and against
      the private local files; read-only probes of the running local stack:
      HTTPS `/health`, enforced security headers, `401` session without a
      cookie and the Vite HMR WebSocket upgrade (`101`) through local Caddy.
- [x] Production ingress through the disposable runtime: only Caddy 80/443,
      TLS, redirect, headers, SPA fallback, forwarded-header sanitizing and
      exact Caddy-peer trust with a simulated Entra discovery endpoint.
- [x] Integrated migrations -> reference seed -> empty-table administrator
      bootstrap without development Users, identities or sessions; repeated
      bootstrap refused without change.

TASK-059B does not authorize provider writes, callback cleanup, Graph permission
removal, tenant changes or production verification. Historical Authentik results
below are preserved evidence only; they are not checks for the current runtime.

## Historical Local Automated Baseline

- [x] Backend Ruff, full pytest and pyright pass.
- [x] Frontend lint, full tests and production build pass.
- [x] Backend and frontend production images build from the documented contexts.
- [x] `.github/scripts/verify-production-compose.sh` passes and missing required
      auth/proxy variables make Compose configuration fail.
- [x] `.github/scripts/verify-production-frontend.sh` passes.
- [x] The release-migration failure test proves that backend does not start.
- [x] Both authentication PlantUML sources render to committed SVGs.

## Historical Broad Local Authentik QA

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

## Historical Local Production-Boundary QA

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

## Historical Conditional Local Entra Federation

Historical TASK-040 procedure, retained with its completed evidence. It is no
longer an initial-release requirement; B/E/F use direct Entra instead.

- [x] Human authorization to access the organisation Entra tenant is recorded.
- [x] Local Authentik uses its separate local-federation app registration.
- [x] Login, callback, first identity link, Schatten session, database role
      enforcement and logout pass through Authentik-to-Entra federation.
- [x] A designated unmatched account fails generically and creates no Schatten
      User, identity or session.
- [x] Browser storage/network and credential-safe logs expose no provider token,
      secret, code or personal email.
- [x] Evidence states that this path does not validate Schatten's direct
      production Entra client, callback, secret, issuer or Coolify boundary.

Preserved TASK-040 evidence: the checks marked complete above were run for
commit `c9bb10a8d54564e5d5b9937be3ddc561bf6b97b5` on 2026-08-24 by
`@jonatanska`. The recorded CI run is
`https://github.com/reflector-oy/schatten/actions/runs/32713910091`.
No issues were reported.

This check used the local-only schatten-authentik Entra registration and local Authentik issuer. It validates the Authentik-to-Entra federation path only; it does not validate Schatten’s direct production Entra client, production callback, production secret, production issuer, or Coolify/TLS deployment boundary.

## Production Deployment Gate

Complete a new copy of this section before every production deployment.

- [ ] Local baseline required for this release is green at the target commit.
- [ ] Real local direct-Entra browser checks are separately recorded after
      authorized setup; simulated tests and historical federation are insufficient.
- [ ] Release candidate is frozen.
- [ ] Daily encrypted on-server backups in `/opt/postgres-backups` and 7-day
      retention are verified; the same-host/disk-loss limitation is recorded.
- [ ] Completed pre-change backup identifier and latest successful isolated
      restore-rehearsal evidence are recorded; missing evidence blocks release.
- [ ] First installation additionally records backup and isolated restore of the
      migrated/seeded/bootstrap database before release acceptance.
- [ ] Direct Caddy TLS, private Docker PostgreSQL 18 and service readiness are
      verified on the UpCloud Ubuntu 26.04 LTS host.
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
- [ ] The smoke result, commit, tester, time, image references, backup identifier and evidence
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

Complete only when a compatible previous stable release exists. For the first
rollout, record that no such target exists and use the stop/escalate path.

- [ ] The selected stable tag resolves to the recorded commit.
- [ ] Backend and frontend are both mapped to that commit's frozen image references.
- [ ] Compatibility with already-applied forward migrations is confirmed before
      deploying the older application.
- [ ] No automatic down migration or database restoration is part of application
      rollback.
- [ ] No volume deletion or database reset occurs; application rollback does
      not recover lost database contents. Production restoration needs separate
      explicit human authorization and impact review.

## Historical TASK-039G Sign-Off

- [x] Local Authentik result records date, commit, tester and pass/fail only.
- [x] Documentation and diagrams show local Authentik, optional local Entra
      federation and direct-Entra production only.
- [x] No production deployment, tenant mutation, tag, backup/restore operation,
      production data access or production QA occurred during TASK-039G.

## Accepted Limitations

- There is no staging. Local direct-Entra checks cannot prove production
  DNS/TLS, credentials or ingress; limited production smoke remains required.
- Required backups do not make application rollback a database recovery action.
  A future managed-service migration must preserve or explicitly revise backup
  and restore policy; it is separate from initial backup implementation.
- There is no organisation membership authorization; all active internal users
  intentionally access all organisations.
- Guarded Entra email matching is accepted only for first linking within the
  small-company, single-tenant administrator trust model.
- There is no back-channel logout, immediate provider revocation, production
  Graph access, refresh token, provider group mapping or SCIM provisioning.
- The in-memory auth rate limiter supports one backend replica in this baseline.
