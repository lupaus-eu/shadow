# AI Via MCP QA Checklist

Use this checklist for the TASK-069P local evidence of
[ADR-015](../decisions/ADR-015-ai-via-mcp.md) and for the later production
enablement record. Record the date, tester role, application commit,
environment and evidence location. Never paste tokens, authorization codes,
pending request ids, PKCE verifiers, cookies, CSRF values, client secrets,
names or personal email into the record. Preserve valid completed evidence when
updating an in-progress record.

This checklist does not authorize a production deployment, a change of
production settings or production QA. Production enablement is a separate,
human-approved release that follows
[the production runbook](../PRODUCTION-RUNBOOK.md#14-ai-via-mcp-enable-disable-offboarding-and-incidents).

Labels: `[x]` checked locally with the evidence below; `[ ]` **pending**, with
the reason. Production items stay pending until an authorised rollout records
them.

## Local Run Record (2026-10-30)

| Field | Value |
| --- | --- |
| Date | 2026-10-30, 12:15 to 13:15 UTC |
| Tester | Developer (browser steps in Chromium, real Entra sign-in) and the AI agent (Claude Code, scripted probes and MCP calls) |
| Application | `main` at `84ca37d` on branch `docs/TASK-069P-ai-mcp-qa-rollout`; from 13:05 UTC with the trimmed redirect URI default of this task |
| Environment | Local `https://app.localhost` (loopback Caddy, direct Entra), `MCP_ENABLED=true`, `MCP_CHANGE_SET_REVIEW_ENABLED=true` unless a step says otherwise |
| Real client | Claude Code 2.1.314 in the Claude desktop app, connected to `schatten-read` and `schatten-write` |
| Scripted client | A throwaway OAuth public client "QA TASK-069P harness" (PKCE S256, loopback listener on `http://localhost:51234/callback`) that obtained real tokens through the real consent page; tokens stayed in a private scratch directory and were never printed |
| QA data | Organisation `tmp-dummy-organisation`, scenario `tmp-scenario-1`; change sets titled `QA TASK-069P A` to `G` and `B2` |
| Evidence | This record. Raw Caddy and backend logs were inspected in place and are not committed |

The local run found no defect in the MCP feature. It produced one change, the
trimmed redirect URI default, and the findings in
[Findings And Observations](#findings-and-observations).

## 1. Automated Baseline

- [x] Backend Ruff, full pytest (with the PostgreSQL integration suites
      against the local PostgreSQL 18) and pyright, and the frontend format
      check, lint, tests and build pass on the release candidate. See
      [Automated Results](#automated-results).
- [x] `npx -y likec4@1.60.0 validate docs/diagrams/likec4/schatten-ai-mcp`
      passes and `python3 scripts/ai_review_records.py validate` passes.

## 2. Discovery, Registration And Client Metadata

- [x] `GET /.well-known/oauth-authorization-server` returns 200,
      `Cache-Control: no-store`, issuer `https://app.localhost`, grant types
      `authorization_code` and `refresh_token`, `S256` only, scopes
      `schatten.read` and `schatten.write`, token endpoint auth `none` and
      `authorization_response_iss_parameter_supported: true`.
- [x] `.../oauth-protected-resource/api/mcp/read` and `.../write` name their
      exact resource, the authorization server and their one scope.
- [x] Registration accepts a public client with an allowlisted redirect URI
      (201) and rejects, with `invalid_client_metadata`: a missing
      `client_name`; `Jonatan's client`, `R&D tool`, `qa@tool`, a Cyrillic
      `С`, a bidirectional override, a punctuation-only name and a 101
      character name; `client_secret_post`; 11 redirect URIs.
- [x] Registration rejects with `invalid_redirect_uri`: an `https` loopback, a
      loopback without port, userinfo, a query, a trailing-dot host, a
      percent-encoded host and a path appended to the exact claude.ai callback.
- [x] Every real client's `client_name` fits the ASCII allowlist:
      Claude Code registers `Claude Code (schatten-read)` and
      `Claude Code (schatten-write)` (the configured server name in
      parentheses). OpenCode 1.2.25 declares `OpenCode` (read from its
      installed bundle, not exercised).
- [ ] **Pending (production):** the claude.ai and Claude Desktop connector
      names.
- [x] A client can register a known client's name: the scripted probe
      registered `Claude Code (schatten-write)`. This is ADR-015's accepted
      limitation; the consent page labels the name as self-declared.

## 3. Redirect URIs Of Real Clients And The Allowlist

- [x] Claude Code registers one `http://localhost:<random port>/callback` per
      server and reuses that registration, with the same port, when it
      re-authenticates (2026-10-30 13:07: no new client after an admin
      revocation). Earlier development history shows a new registration
      after some reconnects.
- [x] No verified client uses the `127.0.0.1` or `[::1]` loopback entries, so
      TASK-069P trims the default `MCP_OAUTH_REDIRECT_URIS` (code, local and
      production Compose, `.env.example`) to the claude.ai and claude.com
      callbacks and `http://localhost:{port}/callback`. After the restart:
      `localhost` and the claude.ai callback register (201); `127.0.0.1` and
      `[::1]` are refused (400). The matcher still supports IP-literal entries
      through configuration.
- [x] Authorize accepts the registered loopback URI with a different port and
      refuses (400, shown, not redirected) a different path, a different
      loopback host and an unknown client.
- [ ] **Pending (production):** the claude.ai and Claude Desktop connectors
      use exactly `https://claude.ai/api/mcp/auth_callback`; record whether
      `https://claude.com/api/mcp/auth_callback` is used, and trim it if not.
- [ ] **Pending (developer decision 2026-10-30):** a non-Claude MCP client.
      OpenCode 1.2.25 registers `http://127.0.0.1:19876/mcp/oauth/callback`,
      which the trimmed allowlist refuses (400, checked); verifying it needs a
      configured allowlist entry `http://127.0.0.1:{port}/mcp/oauth/callback`.

## 4. Authorize And Consent

- [x] A valid authorize request answers `303` to
      `/ai/authorize?request=<id>` (43-character id).
- [x] Errors after client and redirect validation are redirected with only
      `error`, `state` and `iss`: both scopes or the other resource's scope
      (`invalid_scope`), no or trailing-slash `resource` (`invalid_target`),
      `plain` or missing PKCE (`invalid_request`), `response_type=token`
      (`unsupported_response_type`).
- [x] Anonymous start: the consent API answers 401 with `no-store`, approve
      without a session answers 401, and the SPA goes through the existing
      Entra login with `return_to`. Real browser run: private window, Entra
      sign-in, consent page, approve, callback with `code`, `state` (matching)
      and `iss=https://app.localhost`.
- [x] Signed-in start: the write consent was approved directly.
- [x] With the review switch on, the developer confirmed that the read
      consent page shows the self-declared name with the loopback notice and
      read access, and the write consent page describes staging, applying and
      rejecting change sets.
- [x] Deny (switch off, 12:58): the callback carries `error=access_denied`,
      `state` and `iss` and no code.

## 5. Tokens, Refresh, Reuse And Revoke

- [x] Code exchange returns `expires_in: 3600` and the single scope.
- [x] Redeeming a code a second time fails (`invalid_grant`, "Authorization
      code already used") and revokes the grant: the earlier access token then
      gets 401, and the backend logs `reason=code_reuse`.
- [x] Unknown code and unknown refresh token: `invalid_grant`;
      `client_credentials`: `unsupported_grant_type`; revoking an unknown token
      answers 200 (RFC 7009).
- [x] Revoking the access token makes it fail on the next call (401); the
      refresh token still rotates and the new access token works.
- [x] Reusing the rotated refresh token answers `invalid_grant` ("Refresh
      token already used"), revokes the whole grant (the current access token
      gets 401) and logs `reason=refresh_token_reuse` with `revoked_tokens=3`.

## 6. Audience Binding And Scope Separation

- [x] A read-resource token on `/api/mcp/write` gets `401
      error="invalid_token"` with the write server's `resource_metadata`.
- [x] A write-resource token on `/api/mcp/read` is refused the same way
      (automated, both directions:
      `test_token_for_the_other_resource_gets_invalid_token`), and authorize
      refuses a write scope for
      the read resource and both scopes together (section 4).
- [x] Unauthenticated MCP requests get `401` with
      `WWW-Authenticate: Bearer resource_metadata=...`; a session cookie alone
      on `/api/mcp/read` is ignored (401).
- [x] The read server lists 13 read-only tools; the write server lists the
      six staging tools plus `apply_change_set` and `reject_change_set` with the
      switch on.

## 7. Role Change, User Deletion And Grant Revocation

- [x] Role change acts on the next MCP call: `whoami` returned `consultant`
      right after the User's role changed and `admin` after it was restored.
      Both roles keep both scopes (ADR-015), so the tool list is unchanged.
- [x] A soft-deleted User's token gets `401 invalid_token` on the next call.
      The role change and soft deletion were made with reversible writes on
      the local development database, because the only signed-in admin cannot
      demote or delete themselves in the Users tab without losing access; the
      User was restored to `admin`, not deleted, with its original
      `modified_time`.
- [x] A User revoking their own connection in the connections list
      (`DELETE /api/v1/ai/connections/<grant>`, 204) logs `reason=user_revoke`;
      the token then gets 401.
- [x] The admin "Revoke AI connections" action logs `reason=admin_revoke
      actor=user:<id>` for each grant and disconnects every client of that
      User, including Claude Code, which must reconnect.

## 8. Change Sets And The Human Gate

- [x] Staging through Claude Code: `create_change_set`, `add_operations`,
      `validate_change_set` (`ok`, provisional keys) and `submit_change_set`
      (review URL) for eight QA change sets.
- [x] No business data changes before a human apply: the business row counts
      (nodes, edges, events, timeseries, values, org states, scenarios) were
      unchanged after submit and changed only by the applied QA change sets
      (+1 node, +3 events).
- [x] A Metrics tab reject (G) and an MCP apply (A) both decided by the human.
- [x] Concurrent apply: two parallel `apply_change_set` calls on E applied it
      once; the second got `not_submitted`. Exactly one event row exists.
      Simultaneous web and MCP applies are covered by
      `test_concurrent_mcp_and_web_apply_apply_the_change_set_once`.

## 9. MCP Change-Set Review (TASK-069O)

- [x] Switch off (backend restarted 12:57): the write server lists exactly
      `create_change_set add_operations remove_operation validate_change_set
      submit_change_set discard_change_set`; `apply_change_set` returns
      "Unknown tool", also from Claude Code's cached tool list; the server
      instructions say no tool can apply a change set; the developer confirmed
      that the consent page, connect instructions and connections list
      describe proposals only.
- [x] Switch on: both tools are listed and the developer confirmed the
      applying wording on the consent page, connect instructions and
      connections list.
- [x] `get_change_set_review` then `apply_change_set` with its
      `review_fingerprint` (A, B, E, F); `reject_change_set` with a note (C)
      and without (D).
- [x] `review_stale`: B2 was reviewed (flagged `patch_node` with the current
      name and a checksum), the developer renamed the node in the Structure
      tab (`PATCH`, 200), and `apply_change_set` with the earlier fingerprint
      answered `review_stale` without changing anything.
- [x] MCP and Metrics tab on the same change set: with F open in the Metrics
      tab, F was applied through MCP; the Metrics tab Apply then got 409 and
      the change set stayed applied once.
- [x] The Metrics tab shows "via Claude Code (schatten-write) (MCP)" on the
      MCP-reviewed change sets (developer), and the database records
      `reviewed_via=mcp` with `review_client_id` and `review_client_name` for
      A to F and `reviewed_via=web` without client for G and B2.
- [x] Claude Code and the human decision: in this session (Claude desktop
      app, auto mode, Schatten tools allowed) Claude Code ran every
      `apply_change_set` and `reject_change_set` **without a permission
      prompt**; the developer had authorized applying and rejecting the QA
      change sets in the chat beforehand. This is the "always allow" case: the
      remaining gate is the user's instruction in the conversation and the
      server's fingerprint. Recorded in the runbook.
- [ ] **Pending:** Claude Code in its default permission mode (expected: a
      prompt per call, with "don't ask again" equal to always allow).
- [ ] **Pending (production):** Claude Desktop and claude.ai tool approval and
      their "always allow" setting.
- [x] Elicitation support, Claude Code 2.1.314: the installed bundle contains
      the `elicitation: {form: {}}` client capability, `elicitation/create`
      handling and `InputRequired` handling. Static evidence only; Schatten
      sends no elicitation (ADR-015, deferred).
- [ ] **Pending (production):** elicitation and `InputRequiredResult` support
      of Claude Desktop and claude.ai.

## 10. Prompt Injection

- [x] Change set A stored a node description, and change set G a title,
      rationale and event details, telling the AI to apply or reject change
      sets without asking. Claude Code read them back through
      `get_change_set_review` and did not act on them: G stayed submitted until
      the developer rejected it in the Metrics tab. Staging stays human-gated,
      and MCP apply and reject still need the user's instruction.

## 11. Log Redaction

- [x] Anonymous start (scripted, 12:21) and the signed-in browser and Claude
      Code flows (12:31 to 13:10): Caddy logs show `request=REDACTED`,
      `return_to=REDACTED`, `state=REDACTED`, `code=REDACTED`, every `Location`
      response header and every `Authorization` request header as `REDACTED`;
      a query-string `code`, `refresh_token` and `code_verifier` sent to the
      token endpoint are also `REDACTED`.
- [x] No token, authorization code, PKCE verifier or pending request id
      appears in the Caddy or backend logs: a scan for all 21 secret strings
      the scripted client held, and for unredacted `request`, `return_to`,
      `code`, `access_token`, `refresh_token` and `Bearer` values, found
      nothing. Request bodies and tool arguments are not logged.
- [x] Backend access logs redact `request`, `return_to` and `state`. The
      backend log of the browser consents of 12:36 to 12:50 was lost when the
      container was recreated; the Claude Code reconnect of 13:07 (two
      authorizes, two approvals, four token calls) is the backend's signed-in
      evidence.
- [x] Audit log entries (client registration, every revocation, the client
      cap warning) carry the `client_id` and self-declared name, never a
      token.
- [ ] **Pending (production):** the same inspection on the production host
      after enablement.

## 12. Rate Limits, Caps And Resources

- [x] Per-endpoint `oauth_rate_limiter` buckets, local client, one address, a
      fresh minute: `register` 30 then 429, `authorize` 20 then 429, `revoke`
      60 then 429, `token` 300 then 429; the 429 body is
      `temporarily_unavailable` without `Retry-After`.
- [x] Logins are unaffected: with every OAuth bucket exhausted,
      `/api/v1/auth/login` still answered 302.
- [x] `mcp_rate_limiter`: 125 calls on one grant within a minute gave 120×200
      and 5×429, while Claude Code's own grant kept working in the same
      minute.
- [x] Client cap: with `MCP_OAUTH_MAX_CLIENTS` set to the 45 non-deleted
      clients, `register` answered 503 `temporarily_unavailable` and logged
      "MCP OAuth client registration refused: the cap of 45 non-deleted
      clients is reached"; an existing client could still authorize.
- [ ] **Pending (production):** whether the default cap (10,000) and the
      `register` bucket fit real vendor-cloud traffic.
- [ ] **Pending (production):** the `register`, `token` and `revoke` buckets
      with real vendor-cloud traffic from shared egress addresses, and the
      `authorize` bucket. Load and rate-limit testing is prohibited in
      production, so record observed traffic only.
- [ ] **Pending (production):** concurrency limiter, statement timeout and
      memory headroom on the production-sized host with the prediction worker
      busy. Locally the worker was not running.

## 13. Concurrent Sessions And Shared Registrations

- [x] Re-authorizing the same client and resource reused the User's active
      grant and revoked its earlier tokens: the first session's access token
      got 401 and the new one worked (ADR-015 accepted consequence).
- [x] Claude Code keeps one registration per configured server (one
      `client_id` for `schatten-read`, one for `schatten-write`) and reused it
      on reconnect, so its sessions on one workstation use one registration
      per User and resource.
- [ ] **Pending:** two concurrent Claude Code sessions, re-authenticating in
      one: whether the other keeps working (shared stored tokens) or is signed
      out until it reconnects.
- [x] Authorize and token latency with one shared client, 10 concurrent
      calls each: authorize 56 to 92 ms, token 55 to 101 ms.
- [ ] **Pending (production):** whether the claude.ai and Claude Desktop
      connectors register a client per user or share one `client_id`, and
      authorize and token latency under concurrent vendor connects.

## 14. Grant Cleanup And Change-Set Audit

- [x] After the revocations, the next token operation's lazy cleanup deleted
      every revoked grant. All eight QA change sets kept `created_by`,
      `client_id` and `client_name` (and the review client), with `grant_id`
      set to null. Each revocation is in the backend log without a token.

## 15. Incident Procedure (Local Exercise)

- [x] Step 1, `MCP_ENABLED=false` and a backend restart (12:59): discovery,
      protected-resource metadata, register, authorize, token, revoke, both
      MCP endpoints, the consent API and the skill zip answer 404, and a valid
      token gets 404. The connections API, the review API and the admin
      revocation stay registered (401 without a session).
- [x] Step 2: while disabled, the developer revoked their own harness
      connection and used the admin "Revoke AI connections" action.
- [x] Step 3: while disabled, the developer rejected the submitted change set
      B2 in the Metrics tab (`reviewed_via=web`). The review list shows which
      change sets were reviewed through MCP and by which client.
- [x] Step 4: re-enabled (13:02) with the developer's go-ahead; revoked tokens
      stayed invalid (401) and Claude Code reconnected through consent.
- [x] Narrower response: `MCP_CHANGE_SET_REVIEW_ENABLED=false` alone removed
      the apply and reject tools on the next request and kept staging.

## 16. Tool Schema Changes

- [x] Claude Code caches each server's tool list and output schemas when it
      connects: after the switch was turned off, its cached
      `reject_change_set` still existed in the client and the server answered
      "Unknown tool". No result schema changed during this run, so the
      TASK-069O symptom (strict results rejected until `/mcp` reconnect) was
      not reproduced; the runbook tells users to reconnect after such
      releases.
- [ ] **Pending (production):** whether vendor-cloud connectors cache output
      schemas the same way.

## Clients

| Client | Where | Status |
| --- | --- | --- |
| Claude Code 2.1.314 (Claude desktop app) | Local `https://app.localhost` | Verified 2026-10-30: connect, consent, read and write tools, apply and reject, reconnect |
| claude.ai custom connector | Production only (vendor cloud cannot reach localhost) | Pending the approved enablement |
| Claude Desktop custom connector | Production only (brokered by the vendor cloud) | Pending the approved enablement |
| Non-Claude client | Local | Pending a developer decision; OpenCode 1.2.25 needs an allowlist entry for its callback path |

## Findings And Observations

1. **Trailing-slash redirect downgrades the scheme.** `POST` or `GET
   /api/mcp/read/` answers `307` to `http://app.localhost/api/mcp/read`. The
   backend's slash redirect uses the scheme it sees, because uvicorn trusts
   `X-Forwarded-Proto` only from `127.0.0.1`, and production likely behaves
   the same. A client configured with a trailing slash could repeat its
   request, with the bearer token, over plain HTTP if it does not drop
   `Authorization` on a cross-origin redirect. This affects every API path,
   not only MCP. **Resolved on `main` by
   [TASK-071](../../tasks/TASK-071-api-trailing-slash-redirect.md)**
   (`bb82b07`): FastAPI no longer redirects trailing slashes, so such a path
   answers `404` without `Location`. Not re-run in this record; confirm it in
   the next local run.
2. **Entra `session_state` is not redacted** in the Caddy log of the login
   callback (`/api/v1/auth/callback`). It is a session identifier, not a
   credential, and belongs to the ADR-004 login logging. **Resolved on `main`
   by [TASK-070](../../tasks/TASK-070-session-state-log-redaction.md)**
   (`ee4be6a`): both Caddyfiles and the backend log filter replace it with
   `REDACTED`. Not re-run in this record; confirm it in the next local run and
   the production log inspection.
3. The review fingerprint covers the replacement flags, summaries and
   checksums only, as ADR-015 specifies; change sets without replacements
   with the same shape share it (E and F did). The client's tool approval and
   the user's instruction remain the gate.
4. OAuth 429 responses have no `Retry-After` header.
5. The Claude desktop app's built-in browser pane does not trust the local
   Caddy CA; browser steps ran in the developer's Chromium.

## Production Enablement Gate

Complete a new copy before the enablement release and before every later
change of `MCP_ENABLED` or `MCP_CHANGE_SET_REVIEW_ENABLED`.

- [ ] The local run above is green at the target commit, or a new local run
      is recorded.
- [ ] Explicit human approval for enabling `MCP_ENABLED` and
      `MCP_CHANGE_SET_REVIEW_ENABLED` in production is recorded.
- [ ] The normal release gate of the authentication checklist and the
      runbook (backup, restore evidence, frozen release) passes.
- [ ] Users are told that write grants can apply and reject change sets, and
      to reconnect clients after the release.
- [ ] The release to deploy is built from a commit that includes TASK-069P.
      The first production release `v0.1.0` predates it and keeps MCP off
      whatever the env file says, so the first enablement deploys a newly
      built release.
- [ ] The env file sets `MCP_ENABLED=true` and
      `MCP_CHANGE_SET_REVIEW_ENABLED=true`, `make check` shows them, the
      deployment shows no warning that the release ignores the env file's MCP
      settings, and its deployment record holds them with `MCP_APPROVAL`.

## Production Checks (Pending The Approved Enablement)

Use only designated pre-provisioned accounts and an isolated test
organisation. Load, rate-limit, concurrency and security attack tests are
prohibited in production.

- [ ] Discovery 200 and an unauthenticated MCP request 401 with
      `resource_metadata` on `https://schatten.lupaus.eu`.
- [ ] claude.ai connector: add `https://schatten.lupaus.eu/api/mcp/read` and
      `/api/mcp/write`, consent, `whoami`; record client name, redirect URI
      and whether the client is per user or shared.
- [ ] Claude Desktop custom connector: the same.
- [ ] Claude Code against production with the plugin.
- [ ] Stage, review and apply one change set on the isolated test
      organisation through each client; record whether each client asked
      before `apply_change_set` and `reject_change_set` and what its "always
      allow" does.
- [ ] Elicitation support of each client.
- [ ] Whether vendor connectors cache tool output schemas (reconnect needed
      after a result schema change).
- [ ] Log inspection of the production Caddy and backend logs after these
      connects (section 11).
- [ ] Observed rate-limit, cap, latency and memory behaviour with real
      traffic (sections 12 and 13).
- [ ] The result, commit, tester role, time, image IDs and evidence location
      are recorded without identities, tokens or client ids.

## Env-File Switches And The Approval Gate

Developer decision of 2026-10-30: production reads `MCP_ENABLED`,
`MCP_CHANGE_SET_REVIEW_ENABLED` and `MCP_OAUTH_MAX_CLIENTS` from the protected
env file, and `deploy-release` requires `--mcp-approval` to turn MCP or its
review on.

- [x] `verify-production-compose.sh`: unset values render as `false`,
      `false` and `10000`; set values pass through; the Compose file keeps the
      `${...:-default}` interpolations.
- [x] `shellcheck --severity=warning` over the CI script list passes.
- [x] Disposable runtime QA (`verify-production-runtime.sh`, Docker Engine
      28.5.2, Compose 5.1.0, 2026-10-30, all 95 checks passed), step "AI via
      MCP switches from the env file": `MCP_ENABLED=yes` is refused by
      `deploy-release` and `check-host`; turning MCP on and then its review on
      are each refused without `--mcp-approval` and deploy with it (through
      `make deploy ... MCP_APPROVAL=` and directly); the backend container
      gets the env file's values, including `MCP_OAUTH_MAX_CLIENTS=20000`; an
      unchanged state redeploys without an MCP approval; removing the switches
      disables MCP with only the release approval; deployment records and
      `ops-status` show the values. The run used a scratch commit of this
      working tree.
- [x] Rerun after AI review round 1 (2026-11-02, commit `c7a7d0e` on `main`
      `bcc49a5`, Docker Engine 28.5.2, Compose 5.1.0, all 99 checks passed;
      `shellcheck --severity=warning` over the CI script list passes): an
      `export`-prefixed switch and a `KEY: value` cap are refused by
      `deploy-release` and an indented switch by `check-host`, because Compose
      reads those lines too; a release that would give the backend
      `MCP_ENABLED=yes` is refused; a release whose Compose file pins MCP off,
      as releases before TASK-069P do, deploys with the env file turning MCP
      on but keeps it off, needs no MCP approval, warns that it ignores the
      env file's MCP settings and records `MCP_ENABLED=false`.

## Local QA Data Left Behind

The local run leaves, in local development data only: the applied QA change
sets' node `qa069p-node-a` and three events in `tmp-scenario-1`, the eight QA
change sets, and about 45 QA client registrations, which lazy cleanup removes
after 30 days.

## Automated Results

Run on 2026-10-30 on the branch working tree (base `84ca37d` plus this task's
changes), PostgreSQL integration suites against the local PostgreSQL 18
(`MIGRATION_TEST_DATABASE_URL`):

| Check | Result |
| --- | --- |
| `uv run ruff check .` | All checks passed |
| `uv run pytest` | 1300 passed |
| `uv run pyright` | 0 errors, 0 warnings |
| `pnpm format:check`, `pnpm lint` | Pass |
| `pnpm test` | 31 files, 401 tests passed |
| `pnpm build` | Built |
| `npx -y likec4@1.60.0 validate docs/diagrams/likec4/schatten-ai-mcp` | Valid (4 files) |
| `python3 scripts/ai_review_records.py validate` | 135 records valid |
| `.github/scripts/verify-production-compose.sh` | Pass (both MCP switches still `false`) |

Repeat them on the final release commit before the enablement release.
