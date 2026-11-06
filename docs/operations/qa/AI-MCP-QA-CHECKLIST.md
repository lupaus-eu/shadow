# AI Via MCP QA Checklist

Use this checklist for the TASK-069P local evidence of
[ADR-015](../../adr/0015-ai-via-mcp.md) and for the later production
enablement record. Record the date, tester role, application commit,
environment and evidence location. Never paste tokens, authorization codes,
pending request ids, PKCE verifiers, cookies, CSRF values, client secrets,
names or personal email into the record. Preserve valid completed evidence when
updating an in-progress record.

This checklist does not authorize a production deployment, a change of
production settings or production QA. Production enablement is a separate,
human-approved release that follows
[the production runbook](../../runbooks/production.md#14-ai-via-mcp-enable-disable-offboarding-and-incidents).

Labels: `[x]` checked with the evidence below, locally or, where marked with
its date, in production; `[ ]` **pending**, **partly** checked or **not
recorded**, with the reason and what is still open. Production items stay
pending until an authorised rollout records them.


## Authentik MCP provider (ADR-0023, ticket `authentik-sign-in/02`)

Run on 2026-11-06 by `scripts/verify-authentik-local.py` against the local stack (Authentik
2026.8.5), simulating a pre-registered client:

- [x] The provider "Shadow MCP" is confidential, `hashed_user_id`, `per_provider`, allows only the
  authorization code and refresh token grants, and has exactly the declared redirect URIs (two
  strict, one loopback pattern); dynamic registration is not offered.
- [x] PKCE with S256 is enforced by a policy: authorization without a challenge, or with `plain`,
  is refused; a code is refused without the verifier and with a wrong one.
- [x] Consent is asked every time (own authorization flow, `always_require`).
- [x] Discovery, the RFC 8414 metadata and the JWKS are served at the MCP issuer, which differs
  from the web issuer.
- [x] Authorization asks for explicit consent and a code is delivered to a loopback callback; the
  token endpoint accepts the client id, secret and PKCE verifier and issues an access token
  whose `aud` is the MCP client id and `iss` the MCP issuer, plus a refresh token; the refresh
  grant works and rotates the refresh token (the old one is refused); a code cannot be used twice;
  a wrong secret is refused (`invalid_client`). Web-provider tokens do not carry the MCP audience.
- [x] Ten unregistered redirect URIs (other host, extra path or query, trailing slash, other port
  text, https, look-alike host, userinfo trick) are refused with HTTP 400 and no redirect; the
  registered loopback URI is accepted.
- [ ] A real client signs in (Claude Code with `--client-id/--client-secret/--callback-port`, MCP
  Inspector): not run, it needs an interactive browser and the CLI is not on the automation
  host. To do before step 3b begins.
- [ ] The claude.ai custom connector and the `claude.com` callback: not testable locally; the
  `claude.com` callback is kept from Yearclock's production-tested blueprint.

## Local Run Record (2026-10-30)

| Field | Value |
| --- | --- |
| Date | 2026-10-30, 12:15 to 13:15 UTC |
| Tester | Developer (browser steps in Chromium, real Entra sign-in) and the AI agent (Claude Code, scripted probes and MCP calls) |
| Application | `main` at `84ca37d` on branch `docs/TASK-069P-ai-mcp-qa-rollout`; from 13:05 UTC with the trimmed redirect URI default of this task |
| Environment | Local `https://app.localhost` (loopback Caddy, direct Entra), `MCP_ENABLED=true`, `MCP_CHANGE_SET_REVIEW_ENABLED=true` unless a step says otherwise |
| Real client | Claude Code 2.1.314 in the Claude desktop app, connected to `shadow-read` and `shadow-write` |
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
- [x] `npx -y likec4@1.60.0 validate docs/architecture/diagrams/likec4/shadow-ai-mcp`
      passes and `python3 scripts/ai_review_records.py validate` passes.

## 2. Discovery, Registration And Client Metadata

- [x] `GET /.well-known/oauth-authorization-server` returns 200,
      `Cache-Control: no-store`, issuer `https://app.localhost`, grant types
      `authorization_code` and `refresh_token`, `S256` only, scopes
      `shadow.read` and `shadow.write`, token endpoint auth `none` and
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
      Claude Code registers `Claude Code (shadow-read)` and
      `Claude Code (shadow-write)` (the configured server name in
      parentheses). OpenCode 1.2.25 declares `OpenCode` (read from its
      installed bundle, not exercised).
- [x] Production (2026-11-03): the Claude Code plugin, in the CLI and in the
      Claude desktop app's Code tab, registers
      `Claude Code (plugin:shadow:shadow-read)` and
      `Claude Code (plugin:shadow:shadow-write)`, which fit
      ([enablement record](#production-enablement-record-2026-11-03)).
- [x] Production (2026-11-03 and 2026-11-04): the claude.ai and Claude
      Desktop connectors register as `Claude`, which fits; the consent page
      labels it self-declared (developer, 2026-11-04).
- [x] A client can register a known client's name: the scripted probe
      registered `Claude Code (shadow-write)`. This is ADR-015's accepted
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
- [x] Production (2026-11-03): the Claude Code plugin registered its
      `http://localhost:<port>/callback` loopback URI, which the trimmed
      allowlist accepts (developer).
- [x] Production (2026-11-03 and 2026-11-04): the claude.ai and Claude
      Desktop connectors return to `https://claude.ai/api/mcp/auth_callback`.
      The only vendor authorize request on 2026-11-03 (11:33 UTC, read
      server) used it (Caddy log), and on 2026-11-04 the consent page showed
      "Returns to `claude.ai`" for each connector (developer). Only the read
      connector was checked
      ([enablement record](#production-checks-copy)). No observed client used
      `https://claude.com/api/mcp/auth_callback`. Both stay in the allowlist:
      registration is refused if any URI a client registers is not
      allowlisted, and the URIs the connectors register were not inspected.
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
- [x] The Metrics tab shows "via Claude Code (shadow-write) (MCP)" on the
      MCP-reviewed change sets (developer), and the database records
      `reviewed_via=mcp` with `review_client_id` and `review_client_name` for
      A to F and `reviewed_via=web` without client for G and B2.
- [x] Claude Code and the human decision: in this session (Claude desktop
      app, auto mode, Shadow tools allowed) Claude Code ran every
      `apply_change_set` and `reject_change_set` **without a permission
      prompt**; the developer had authorized applying and rejecting the QA
      change sets in the chat beforehand. This is the "always allow" case: the
      remaining gate is the user's instruction in the conversation and the
      server's fingerprint. Recorded in the runbook.
- [x] Claude Code in a permission mode that asks (2026-11-03, CLI 2.1.314 in
      **manual** mode, which replaces the unnamed default mode in its
      Shift+Tab cycle): it prompted before each Shadow call, including
      `reject_change_set`
      ([re-run](#release-commit-re-run-2026-11-03)). The options of its
      "don't ask again" choice were not recorded.
- [x] Production (2026-11-03): Claude Code with the plugin in the Claude
      desktop app (bundled 2.1.309) asked before `apply_change_set` and
      `reject_change_set` (developer); its permission mode was not recorded.
      The reject call was on the change set adding `Test event2` to scenario
      `Reality` in `Testiorganisaatio`
      ([enablement record](#production-checks-copy)).
- [x] Production (2026-11-03): the Claude Code CLI 2.1.314 with the plugin
      asked before `apply_change_set` and `reject_change_set` (developer), on
      change sets in `Testiorganisaatio` whose titles were not recorded.
- [x] Production (2026-11-03): with "always allow" chosen in the desktop
      app's Code tab, applying and rejecting change sets ran without asking,
      as expected (developer).
- [ ] **Partly:** claude.ai and Claude Desktop (2026-11-04, read connector
      only): with the tool set to ask, each asked before `whoami`
      (developer). Whether they ask before `apply_change_set` and
      `reject_change_set`, and what their "always allow" does, is pending
      until the write connector is added.
- [x] Elicitation support, Claude Code 2.1.314 and (2026-11-03) the desktop
      app's bundled 2.1.309: each installed bundle contains
      the `elicitation: {form: {}}` client capability, `elicitation/create`
      handling and `InputRequired` handling. Static evidence only; Shadow
      sends no elicitation (ADR-015, deferred).
- [ ] **Not recorded:** elicitation and `InputRequiredResult` support of
      Claude Desktop and claude.ai. They connected in production on
      2026-11-03 and 2026-11-04, but they run in the vendor cloud and
      Shadow logs no client capabilities, so production shows no evidence
      either way.

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
- [x] Production (2026-11-03), after the enablement connects: no unredacted
      query parameter in the Caddy or backend log, `Authorization`,
      `X-Csrf-Token` and `Location` only as `REDACTED`, and "Bearer" only in
      `WWW-Authenticate` challenges
      ([enablement record](#production-enablement-record-2026-11-03)).

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
      `register` bucket fit real vendor-cloud traffic. At the 2026-11-03
      enablement Claude Code and a vendor read connection connected without a
      reported problem (developer), and the log scan after them and the
      product owner's testing counted six registrations and no 429.
- [ ] **Pending (production):** the `register`, `token` and `revoke` buckets
      with real vendor-cloud traffic from shared egress addresses, and the
      `authorize` bucket. Load and rate-limit testing is prohibited in
      production, so record observed traffic only.
- [ ] **Pending (production):** concurrency limiter, statement timeout and
      memory headroom on the production-sized host with the prediction worker
      busy. Locally the worker was not running; not observed at the
      2026-11-03 enablement.

## 13. Concurrent Sessions And Shared Registrations

- [x] Re-authorizing the same client and resource reused the User's active
      grant and revoked its earlier tokens: the first session's access token
      got 401 and the new one worked (ADR-015 accepted consequence).
- [x] Claude Code keeps one registration per configured server (one
      `client_id` for `shadow-read`, one for `shadow-write`) and reused it
      on reconnect, so its sessions on one workstation use one registration
      per User and resource.
- [ ] **Pending:** two concurrent Claude Code sessions, re-authenticating in
      one: whether the other keeps working (shared stored tokens) or is signed
      out until it reconnects.
- [x] Authorize and token latency with one shared client, 10 concurrent
      calls each: authorize 56 to 92 ms, token 55 to 101 ms.
- [x] Production (2026-11-03): the Claude Code CLI and the desktop app's
      Code tab each registered their own clients; the Code tab did not reuse
      the CLI's registration.
- [ ] **Not recorded (production):** whether the claude.ai and Claude
      Desktop connectors share one `client_id` across Users; vendor
      connections of two Users were not compared. Authorize and token latency
      under concurrent vendor connects was not observed; concurrency tests
      are prohibited in production.

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
      schemas the same way. The connectors connected at the 2026-11-03
      enablement, but no tool result schema has changed since; check after
      the next release that changes one.

## Clients

| Client | Where | Status |
| --- | --- | --- |
| Claude Code 2.1.314 (Claude desktop app) | Local `https://app.localhost` | Verified 2026-10-30: connect, consent, read and write tools, apply and reject, reconnect. Re-verified 2026-11-03 on `df98a2e` with the 2.1.314 CLI ([re-run](#release-commit-re-run-2026-11-03)) |
| Claude Code with the Shadow plugin (CLI 2.1.314 and the Claude desktop app's Code tab, bundled 2.1.309) | Production `https://shadow.lupaus.eu` | Verified 2026-11-03: connect, consent, `whoami`, stage, review, apply and reject in the chat ([enablement record](#production-enablement-record-2026-11-03)) |
| claude.ai custom connector | Production only (vendor cloud cannot reach localhost) | Read server verified 2026-11-04 (developer): connect, consent and `whoami`. Write server pending: the product owner has only enabled the read connector yet ([enablement record](#production-enablement-record-2026-11-03)) |
| Claude Desktop custom connector | Production only (brokered by the vendor cloud) | Read server verified 2026-11-04 (developer): connect, consent and `whoami`. Write server pending as for claude.ai ([enablement record](#production-enablement-record-2026-11-03)) |
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
   [TASK-071](../../archive/tasks/TASK-071-api-trailing-slash-redirect.md)**
   (`bb82b07`): FastAPI no longer redirects trailing slashes, so such a path
   answers `404` without `Location`. Confirmed locally on `df98a2e`
   ([re-run](#release-commit-re-run-2026-11-03)) and in production on
   2026-11-03 (`POST /api/mcp/read/` answers 404).
2. **Entra `session_state` is not redacted** in the Caddy log of the login
   callback (`/api/v1/auth/callback`). It is a session identifier, not a
   credential, and belongs to the ADR-004 login logging. **Resolved on `main`
   by [TASK-070](../../archive/tasks/TASK-070-session-state-log-redaction.md)**
   (`ee4be6a`): both Caddyfiles and the backend log filter replace it with
   `REDACTED`. Confirmed locally on `df98a2e`
   ([re-run](#release-commit-re-run-2026-11-03)) and in the production log on
   2026-11-03 (three `session_state=REDACTED` in the first scan and six in
   the rerun, none unredacted).
3. The review fingerprint covers the replacement flags, summaries and
   checksums only, as ADR-015 specifies; change sets without replacements
   with the same shape share it (E and F did). The client's tool approval and
   the user's instruction remain the gate.
4. OAuth 429 responses have no `Retry-After` header.
5. The Claude desktop app's built-in browser pane does not trust the local
   Caddy CA; browser steps ran in the developer's Chromium.
6. On 2026-11-03 the Claude desktop app's bundled Claude Code 2.1.309 could
   not connect to the local servers:
   `ERR_TLS_CERT_ALTNAME_INVALID fetching "https://app.localhost"`. Caddy
   serves the `app.localhost` certificate (SAN `DNS:app.localhost`) on
   `127.0.0.1` with and without SNI, `::1` refuses the connection, and Node
   24.22.2 and the Claude Code 2.1.314 CLI connect. Local only, because
   production has a publicly trusted certificate; not investigated further.
   The re-run's MCP calls therefore ran in the CLI.

## Release-Commit Re-Run (2026-11-03)

A focused local run on the release commit for the first item of the
[enablement gate](#production-enablement-gate). It repeats the core flow and
covers what changed on `main` after the 2026-10-30 run: TASK-070
(`session_state` redaction), TASK-071 (no trailing-slash redirect), TASK-072
(closable alerts on the consent page and in the AI panel), TASK-073 (refreshed
CA trust in the images) and the merged TASK-069P. Sections 1 to 16 keep the
2026-10-30 evidence; items not listed here were not re-run.

| Field | Value |
| --- | --- |
| Date | 2026-11-03, 08:09 to 08:40 UTC |
| Tester | Developer (Entra sign-out and sign-in in Brave; consent pages in Firefox, the default browser that Claude Code opened; Metrics tab) and the AI agent (Claude Code in the Claude desktop app: scripted probes, database and log checks) |
| Application | `main` at `df98a2e`; backend image rebuilt from it; `make dev-up` reported no pending migrations |
| Environment | Local `https://app.localhost` (loopback Caddy, direct Entra), `MCP_ENABLED=true`, `MCP_CHANGE_SET_REVIEW_ENABLED=true` |
| Real client | Claude Code 2.1.314 CLI in a terminal, connected to `shadow-read` and `shadow-write` |
| QA data | Organisation `tmp-dummy-organisation`, scenario `tmp-scenario-1`; change sets `QA df98a2e A` and `QA df98a2e B` |
| Evidence | This record. Raw Caddy and backend logs were inspected in place and are not committed |

- [x] Automated: CI passed on `df98a2e` (reported by the developer);
      `npx -y likec4@1.60.0 validate docs/architecture/diagrams/likec4/shadow-ai-mcp`
      is valid (4 files) and `python3 scripts/ai_review_records.py validate`
      validated 154 records.
- [x] Discovery answers 200 with `no-store`, issuer `https://app.localhost`,
      `S256` only, both scopes, token endpoint auth `none` and
      `authorization_response_iss_parameter_supported: true`; both
      protected-resource documents name their resource and their one scope.
- [x] Unauthenticated `POST /api/mcp/read` and `/write` answer 401 with their
      `resource_metadata`.
- [x] Finding 1 (TASK-071): `POST /api/mcp/read/`, `GET /api/mcp/write/` and
      `GET /api/v1/auth/session/` answer 404 without `Location`.
- [x] Finding 2 (TASK-070): three Entra sign-in callbacks; Caddy logged
      `session_state=REDACTED` each time, and neither the Caddy nor the
      backend log holds an unredacted value.
- [x] Revoking both Claude Code connections in the connections list logged
      two `MCP OAuth grant revoked` entries with `reason=user_revoke`.
- [x] Reconnect: Claude Code reused its two client registrations (no
      `register` call) and got new read and write grants through two
      authorizes, the consent API and four token calls. The developer
      confirmed that both consent pages looked correct.
- [x] `whoami` on the read server returned `admin`; the write server has no
      `whoami`, as specified (section 6).
- [x] Staging: Claude Code created, validated and submitted A and B (one
      `create_event` each). The business tables changed only through A's
      apply: `events` went from 242 to 243 and every other business table
      count stayed the same; B created no event.
- [x] The developer applied A in the Metrics tab: `applied`,
      `reviewed_via=web`, no review client.
- [x] Claude Code in manual mode asked before both calls of the MCP reject,
      `get_change_set_review` and `reject_change_set`; neither the user nor
      the project settings hold a permission rule for Shadow tools. B is
      `rejected` with `reviewed_via=mcp`, review client
      `Claude Code (shadow-write)` and the note. The Metrics tab shows
      "via Claude Code (shadow-write) (MCP)" on B and no MCP label on A
      (developer).
- [x] Log redaction over the whole run: no unredacted `request`,
      `return_to`, `code`, `state`, `session_state` or token query parameter
      in the Caddy or backend log; `Authorization` (24 authenticated MCP
      requests), `X-Csrf-Token` (6) and `Location` (8) are logged as
      `REDACTED`; "Bearer" appears only in `WWW-Authenticate` response
      challenges; the audit entries carry no token.

## Production Enablement Gate

Complete a new copy before the enablement release and before every later
change of `MCP_ENABLED` or `MCP_CHANGE_SET_REVIEW_ENABLED`. The first copy is
in the [enablement record](#production-enablement-record-2026-11-03).

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

## Production Checks

Complete a copy with each enablement; the first is in the
[enablement record](#production-enablement-record-2026-11-03). Use only
designated pre-provisioned accounts and an isolated test organisation. Load,
rate-limit, concurrency and security attack tests are prohibited in
production.

- [ ] Discovery 200 and an unauthenticated MCP request 401 with
      `resource_metadata` on `https://shadow.lupaus.eu`.
- [ ] claude.ai connector: add `https://shadow.lupaus.eu/api/mcp` (before
      TASK-074 `/api/mcp/read` and `/api/mcp/write`), consent, `whoami`;
      record client name, redirect URI and whether the client is per user or
      shared.
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

## Production Enablement Record (2026-11-03)

The first enablement of MCP and its change-set review in production. The main
developer ran the host commands, the browser checks, the Claude Code CLI
checks, the claude.ai and Claude Desktop connector checks of 2026-11-04 and
the claims marked "developer"; the AI agent (Claude Code in the Claude
desktop app's Code tab with the Shadow plugin) made the Code tab's MCP
calls. The product owner also tested in production before the
log scan was rerun. No issue was observed during the deployment or the MCP
checks (developer); in the narrow smoke, the first logout stopped on
Microsoft's sign-out page and a repeated one passed (see [Release](#release)).
The record holds no identities, tokens or client ids; raw logs were inspected
on the host and are not committed.

### Release

| Field | Value |
| --- | --- |
| Approvals | Release `CHG-11-03-2026-shadow-release` and MCP enablement `CHG-11-03-2026-shadow-mcp-enable`, both by the main developer on 2026-11-03 |
| Approved commit, CI | `df98a2e7c05a2920c869bd9a1f331673217d412e`; CI run <https://github.com/reflector-oy/schatten/actions/runs/41597239404> passed |
| Source delivery | "Deploy to production" run <https://github.com/reflector-oy/schatten/actions/runs/41606482111>: commit, branch `main` and result checked; `SOURCE_MANIFEST_SHA256=78801c15f5cfd0a4054117cfc36546f2a525f6993534d5bd32bb4f8e899a05d4`. `shadow-receive` accepted 726 files for the commit, and the installed `upload-gate` and `shadow-receive` both match the received manifest |
| Build | `$M check` passed. `RELEASE_ID=20261103T090415Z-df98a2e7c05a`, `SOURCE_RUN_ID=41606482111`, backend `sha256:77e16b95b9367a2c887aa5c2b1da9914fad6179710cac46b6960a3a57e3d008e`, frontend `sha256:143d4af1ba82028c1a790abc1e85561a9a6e69c08ea3e52cb47298b596af1ad4`, build duration 143 s. `release.env`: Docker Engine 29.8.1, Compose 5.5.1, Buildx v0.37.1, kernel `7.0.0-34-generic`, `BUILD_MEMORY_AVAILABLE_BEFORE_BYTES=1043079168`. Memory and load during the build were not watched (not performed) |
| Restore evidence | 2026-11-03T09:31:16Z, newest completed backup `shadow-20261103T003001Z-scheduled-1a5b84`, `STATUS=success` |
| Deployment | `$M deploy` with both approval references. Pre-change backup `shadow-20261103T093722Z-pre-release-b60a02`; current release `20261103T090415Z-df98a2e7c05a`, previous `20261002T085353Z-0db661289165`. `$M status` shows the deployed `MCP_ENABLED=true`, `MCP_CHANGE_SET_REVIEW_ENABLED=true` and `MCP_OAUTH_MAX_CLIENTS=10000` equal to the env file's, so the release read the env file. Deployment record `20261103T093719Z-20261103T090415Z-df98a2e7c05a.env`: `MODE=release`, `PREVIOUS_RELEASE=20261002T085353Z-0db661289165`, `MCP_OAUTH_MAX_CLIENTS=10000`, `MCP_APPROVAL=CHG-11-03-2026-shadow-mcp-enable`, `MIGRATION_EXIT_CODE=0`, `SCHEDULER=active`, `STATUS=succeeded`, from 09:37:19Z to 09:38:07Z; no `FAILURE` or `QA_COMPOSE_OVERRIDE` (`deploy-release` writes `SERVICES_REPLACED` only on failure). `initialize status` afterwards: `schema_version=19` |
| Migrations and rollback | Migrations 016 to 019 reached production with this release. 017 and 018 create tables, 019 adds columns to a table of 018, and 016 widens the `prediction_model_results.result_kind` check to allow `prophet`; nothing is dropped or narrowed. `v0.1.0` can therefore run against schema 19. A rollback to it follows runbook section 6 with that release's own tooling: `$B_old/deploy-release 20261002T085353Z-0db661289165 --approval <ref> --rollback --confirm-schema-compatible`, with `B_old=/opt/apps/shadow-releases/20261002T085353Z-0db661289165/source/deploy/bin`. It checks that `v0.1.0`'s 15 migrations are an exact prefix of the applied history and never runs migrations. MCP is then off, the new tables stay unused and `v0.1.0` shows Prophet results under their kind name. Every prediction request queued under this release stores a `modelKinds` key that `v0.1.0`'s snapshot model forbids, so its worker stops on each such request, restarts and marks it failed as interrupted; stop new submissions and let the queue drain before rolling back, and resubmit any that failed. Reviewed from the repository after the deployment (AI agent, 2026-11-03), not before it as runbook section 5 step 1 requires |
| Scheduler | Before the deployment Ofelia logged `postgres-backup` on 2026-11-02 and 2026-11-03 with `failed: false`. Afterwards `$M status` listed no scheduler entries and no "Ofelia is not running" line, because the deployment recreated Ofelia's container. On 2026-11-04 `$M status` (main developer) listed `shadow-20261104T003001Z-scheduled-b713cc` among the completed backups, the first scheduled backup after the deployment (00:30:01Z, 02:30 Helsinki time), and Ofelia logged `postgres-backup` 2026-11-04 02:30:01 (+02:00) `failed: false, skipped: false, error: none`, so the recreated Ofelia runs the nightly backup. Latest restore evidence unchanged (2026-11-03T09:31:16Z, `STATUS=success`) |
| Smoke (runbook section 7) | Main developer, 2026-11-03, on this release. 1: `/health` `OK`; certificate `issuer=C=US, O=Let's Encrypt, CN=YE1`, `notAfter=Dec 31 08:58:30 2026 GMT` (afternoon). 2: designated admin at about 16:03 Helsinki time: login, clean callback, session on reload and Users administration pass, but logout stopped on Microsoft's sign-out page (`https://login.microsoftonline.com/<tenant-id>/oauth2/logoutredirect`) instead of returning to `/login`. Shadow's logout code is unchanged since `v0.1.0`, whose logout returned to `/login` on 2026-10-02, and an AI investigation of the repository found no Shadow-side cause. A repeated logout in the Brave browser between 16:00 and 17:00 Helsinki time returned to `/login`, pass. After another logout at about 18:00 Helsinki time, `GET /api/v1/auth/session` returned `401`, pass. 3: designated consultant around noon, shortly after the deployment: no Users administration, and logout returned to `/login`, pass. 4: not run, because no suitable account (a designated tenant account without a matching Shadow User) is available; accepted risk stated by the main developer. 5: one prediction on `Testiorganisaatio`, queued 11:43 and completed 11:44 (UI time, Helsinki), with exactly one prediction worker in `$M ps`, pass |
| Stable tag | Prior: `v0.1.0` on `0db6612`, backend `sha256:6ac5da49ccd05f2969a569571f28283f804da15cef692d8993227abf90e13441`, frontend `sha256:0d8930318f36ba0e8f591da04d672aea7fb19e221fb042de4fbffd37bd84e192` ([F record](FIRST-PRODUCTION-ROLLOUT.md#9-release-record-11)). This release: `v0.2.0`, annotated (tag object `caf9dfc600e18af5d4a949f0296117aece96e3e1`), on commit `df98a2e7c05a2920c869bd9a1f331673217d412e`; backend `sha256:77e16b95b9367a2c887aa5c2b1da9914fad6179710cac46b6960a3a57e3d008e`, frontend `sha256:143d4af1ba82028c1a790abc1e85561a9a6e69c08ea3e52cb47298b596af1ad4`. Created 2026-11-03 at 12:22 UTC (14:22 Helsinki time) by the main developer, who accepted the release on the checks completed by then, among them smoke items 3 and 5 and the plugin's MCP checks; `origin` resolves it to the release commit. **Accepted deviation** (main developer): smoke item 2 and its logout re-checks ran after the tag, from about 16:03 Helsinki time, and whether smoke item 1 (afternoon) ran before the tag was not recorded, although runbook section 11 creates stable tags only after acceptance |

### Enablement Gate (Copy)

- [x] The local run is green at the target commit: the
      [release-commit re-run](#release-commit-re-run-2026-11-03) on
      `df98a2e`.
- [x] Explicit human approval for enabling both switches:
      `CHG-11-03-2026-shadow-mcp-enable`, main developer, 2026-11-03.
- [x] The normal release gate passes: CI on `df98a2e`, real local Entra
      sign-in in the re-run, successful restore evidence of the newest
      backup, a pre-change backup and a frozen release.
- [x] Users were told that write grants can apply and reject change sets,
      and to reconnect clients after the release (developer).
- [x] The release is built from `df98a2e`, which includes TASK-069P.
- [x] The env file sets both switches: `$M check` showed
      `MCP_ENABLED=true MCP_CHANGE_SET_REVIEW_ENABLED=true
      MCP_OAUTH_MAX_CLIENTS=10000`, the deployed values equal them, so the
      release did not ignore the env file, and the deployment ran with
      `MCP_APPROVAL=CHG-11-03-2026-shadow-mcp-enable`.

### Production Checks (Copy)

The deployment took its pre-change backup at 09:37 UTC. The MCP checks ran
from around noon into the afternoon of 2026-11-03, Helsinki time (UTC+2): the
plugin checks first, in the Claude Code CLI from 09:50 UTC and in the Claude
desktop app's Code tab from 10:19 UTC (apply at 10:23:01 UTC), with the first
log scan, then a vendor connection to the read server and the product owner's
testing with the second scan. The claude.ai and Claude Desktop connector
checks ran on 2026-11-04.

Corrected on 2026-11-04: this record first named the CLI checks "claude.ai"
and the Code tab checks "Claude Desktop"; the user agents in the Caddy log,
confirmed by the developer, show where they ran. The product owner has only
enabled the read connector yet, so the claude.ai and Claude Desktop connectors
were checked with the read server only.

- [x] Discovery returns issuer `https://shadow.lupaus.eu`; an
      unauthenticated `POST /api/mcp/read` gets 401 with
      `WWW-Authenticate: Bearer resource_metadata=...`; `POST /api/mcp/read/`
      gets 404 (finding 1).
- [ ] **Partly:** claude.ai connector, read server only
      (`https://shadow.lupaus.eu/api/mcp/read`). On 2026-11-03 a vendor
      connection (client `Claude`) authorized the read server at 11:33 UTC
      with the claude.ai callback and made only read calls (Caddy log). On
      2026-11-04 the developer removed the connector and added it again: the
      consent page showed client `Claude` (self-declared) returning to
      `claude.ai`, and with the tool set to ask, claude.ai asked before
      `whoami`. Staging, review, apply and reject through the write server
      are pending until the write connector is added.
- [ ] **Partly:** Claude Desktop custom connector (the chat app's
      connectors, brokered by the vendor cloud), read server only,
      2026-11-04 (developer): the consent page showed client `Claude`
      (self-declared) returning to `claude.ai`, and with the tool set to
      ask, Claude Desktop asked before `whoami`. The write server is pending
      as for claude.ai.
- [x] Claude Code against production with the plugin, in the Claude Code
      CLI 2.1.314 and in the Claude desktop app's Code tab (bundled Claude
      Code 2.1.309): each registered
      `Claude Code (plugin:shadow:shadow-read)` and
      `Claude Code (plugin:shadow:shadow-write)` with the expected
      loopback redirect URI, a registration of its own per server and
      installation (not shared across Users), and `whoami` returned the
      designated admin.
- [x] Stage, review and apply on the isolated test organisation
      `Testiorganisaatio`, scenario `Reality`: the change set
      `Test event claude desktop` (one `create_event` on 2026-12-22) was
      staged, validated without replacements and submitted, shown in the chat
      with `get_change_set_review` and applied with `apply_change_set` on the
      developer's instruction at 10:23:01 UTC. Shadow recorded
      `reviewed_via=mcp` with the plugin's write client. The client asked
      before `apply_change_set` and `reject_change_set` (developer); its
      permission mode and the options of its prompt were not recorded. The
      change set adding `Test event2` to scenario `Reality` was rejected with
      `reject_change_set` after the client asked (developer). The Claude Code
      CLI also asked before both, on change sets in `Testiorganisaatio` whose
      titles were not recorded (developer). With "always allow" chosen in the
      Code tab, applying and rejecting ran without asking, as expected
      (developer).
- [x] Elicitation, Claude Code: the bundled Claude Code 2.1.309 declares
      the `elicitation` (form) client capability and handles
      `elicitation/create` and `InputRequiredResult` (static evidence, as in
      section 9). For claude.ai and Claude Desktop it is not recorded:
      Shadow logs no client capabilities.
- [ ] **Pending:** whether vendor connectors cache tool output schemas; this
      needs a later release that changes a tool result.
- [x] Log inspection (section 11) of the production Caddy and backend logs
      since the deployment, first after the plugin checks and again after the
      vendor read connection and the product owner's own testing (developer):
      - Caddy: no unredacted `request`, `return_to`, `code`, `state`,
        `session_state`, `error`, `error_description` or token query
        parameter and no unredacted `Authorization`, `X-Csrf-Token` or
        `Location` header. The rerun counted 74 `Authorization`,
        18 `Location`, 6 `code`, 11 `request`, 6 `return_to`,
        6 `session_state` and 11 `state` values logged as `REDACTED` (the
        first scan 22, 9, 3, 4, 3, 3 and 5) (finding 2).
      - Backend: no unredacted query parameter; neither log has "Bearer"
        outside `WWW-Authenticate` challenges.
      - Audit: six `client registered` entries in the rerun. The first scan
        reported two, both the plugin's, although the log has four Claude
        Code registrations by 10:19:56 UTC, so that scan either ran before
        10:19 UTC or undercounted. Four are Claude Code's, one per server from
        the CLI (09:50 UTC) and from the Code tab (10:19 UTC); two are the
        vendor client `Claude` (11:32 and 11:33 UTC), for the read server,
        and only the second authorized (Caddy log, 2026-11-04). No
        registration refusal, revocation or apply failure in the backend
        log. Caddy shows a `400` on the Code tab's first registration of each
        server, each followed at once by a successful one; Shadow does not
        log the reason.
- [ ] **Partly:** observed limits and resources. No 429 on `/api/oauth/*` or
      `/api/mcp/*` in either scan, and 6 of the 10,000 allowed client
      registrations; sustained real vendor-cloud traffic, latency and memory
      were not observed yet.
- [x] The result, commit, tester roles, times and image IDs are recorded
      above, without identities, tokens or client ids.

Production QA data: in `Testiorganisaatio` / `Reality`, the applied change set
`Test event claude desktop` and its event on 2026-12-22 and the rejected change
set adding `Test event2`; an earlier event `Test event` on 2026-12-24 is also
there. The Claude Code CLI checks also used `Testiorganisaatio`; their change
set titles were not recorded. The claude.ai and Claude Desktop checks of
2026-11-04 only read.

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
after 30 days. The 2026-11-03 re-run adds the applied change set
`QA df98a2e A` with its event `QA df98a2e A event` and the rejected
`QA df98a2e B`.

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
| `npx -y likec4@1.60.0 validate docs/architecture/diagrams/likec4/shadow-ai-mcp` | Valid (4 files) |
| `python3 scripts/ai_review_records.py validate` | 135 records valid |
| `.github/scripts/verify-production-compose.sh` | Pass (both MCP switches still `false`) |

Repeat them on the final release commit before the enablement release.

## TASK-074 Single MCP Connector

Local end-to-end checks for the 2026-11-03 amendment of ADR-015
([TASK-074](../../archive/tasks/TASK-074-single-mcp-connector.md)): one MCP endpoint
`/api/mcp` with per-tool scope checks in place of `/api/mcp/read` and
`/api/mcp/write`. The records above stay as they are; they describe the two
servers of that time. The read-only role is covered by the automated tests
with a stubbed `ROLE_SCOPES`; no role is limited in code. The production
release of TASK-074 is separate and needs its own approval
([runbook 14.10](../../runbooks/production.md#1410-switching-to-the-single-mcp-connector-task-074)).

| Field | Value |
| --- | --- |
| Date | Pending |
| Tester | Pending |
| Application | Pending: branch `feature/TASK-074-single-mcp-connector` at the commit tested |
| Environment | Local `https://app.localhost`, migrated to 020, `MCP_ENABLED=true`, `MCP_CHANGE_SET_REVIEW_ENABLED=true` |
| Real client | Pending: Claude Code version |
| Evidence | Pending |

- [ ] Automated: the backend, frontend, PostgreSQL integration, LikeC4 and
      review-record checks of the task's Testing section pass.
- [ ] An unauthenticated `curl -X POST https://app.localhost/api/mcp` gives
      401 with
      `resource_metadata=.../.well-known/oauth-protected-resource/api/mcp`.
      `/api/mcp/read` gives 404.
- [ ] `claude mcp add --transport http shadow https://app.localhost/api/mcp`,
      then `/mcp` → authenticate **once**. The consent page shows read and
      write access, and one connection appears in the Metrics tab.
- [ ] The client lists all 21 tools and both prompts. `whoami` works, and a
      change set can be staged, submitted and applied from the chat.
- [ ] Revoking the connection in the Metrics tab cuts off both reading and
      writing.
- [ ] The plugin, reinstalled from the repository marketplace, shows one
      `shadow` server.
