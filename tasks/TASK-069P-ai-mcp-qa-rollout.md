# TASK-069P AI Via MCP QA, Runbook And Production Rollout

## Source Plan

This task is part of the approved plan "AI chat via MCP for generating Schatten
model and timeseries data", accepted on 2026-10-21. See
[TASK-069A](TASK-069A-ai-mcp-architecture.md) and ADR-015.

This task was TASK-069O until 2026-10-29, when the developer-requested
[TASK-069O](TASK-069O-mcp-change-set-review.md) (applying and rejecting change
sets from MCP clients, ADR-015 amendment) was inserted before it.

## Goal

Verify the whole feature end to end and document how to operate it. Then
enable it in production, but only after separate human approval.

## Requirements

- Create `docs/qa/AI-MCP-QA-CHECKLIST.md`, following
  `docs/qa/AUTHENTICATION-QA-CHECKLIST.md`. Cover:
  - OAuth discovery, registration (allowlist), authorize, consent, token,
    refresh rotation, reuse detection and revoke;
  - redirect URI matching: the exact redirect URIs that each real client
    registers. Trim the default `MCP_OAUTH_REDIRECT_URIS` loopback entries,
    for example `localhost`, to those actually used;
  - audience binding: a read-resource token is rejected on `/api/mcp/write`,
    and vice versa;
  - role change, user deletion and grant revocation taking effect on the next
    MCP call;
  - read and write scope separation;
  - change-set staging, validate, submit, review, apply and reject, and
    concurrent apply;
  - that no business data changes before a human apply, either in the Metrics
    tab or through an MCP `apply_change_set` call the human approved in the
    client;
  - MCP change-set review (TASK-069O):
    - with `MCP_CHANGE_SET_REVIEW_ENABLED=false` the write server lists only
      the six staging tools and the consent page says "proposals only";
    - with it `true` the write server also lists `apply_change_set` and
      `reject_change_set`, and the consent page, connect instructions and
      connections list describe applying;
    - `get_change_set_review`, then `apply_change_set` with its
      `review_fingerprint`, and `reject_change_set` with and without a note;
    - `review_stale` after a REST edit of a flagged target between review and
      apply;
    - concurrent MCP and Metrics tab apply of the same change set: it applies
      once;
    - the Metrics tab shows "via <client> (MCP)" for MCP reviews and the
      database records `reviewed_via`, `review_client_id` and
      `review_client_name`;
    - each real client asks the human before calling `apply_change_set` and
      `reject_change_set` (Claude Code permission prompt, Claude Desktop and
      claude.ai tool approval), and what an "always allow" setting does.
      Record the observed behaviour in the runbook;
    - whether each real client supports MCP elicitation, including the
      stateless `InputRequiredResult` flow, as input for a later server-side
      confirmation decision (ADR-015, deferred);
  - prompt injection: business text returned by read tools that tries to make
    the AI act, including text that asks it to apply or reject a change set.
    Staging stays human-gated, and an MCP apply or reject still needs the
    human's approval in the client.
  - Log redaction: after a full connect flow, both an anonymous and a
    signed-in start, inspect the Caddy and backend access logs, locally and in
    production once enabled. Confirm that:
    - no bearer token, refresh token, authorization code or tool argument
      appears;
    - no pending request id appears in a URL path, in the `request` or
      `return_to` query parameters, or in a `Location` response header; all
      show `REDACTED`.
  - Resource behaviour on the production-sized host: concurrency limiter,
    statement timeout and memory headroom with the prediction worker busy.
  - Client cap: verify that the default cap (10,000 non-deleted clients)
    and the registration rate limit fit real use, and that hitting the cap
    logs a warning.
  - Rate-limit defaults:
    - the per-endpoint `oauth_rate_limiter` buckets with real vendor-cloud
      traffic, which shares vendor egress addresses: the higher `register`,
      `token` and `revoke` buckets and the low `authorize` bucket;
    - the same buckets with local clients;
    - the per-grant `mcp_rate_limiter`;
    - logins unaffected by OAuth or MCP load.
  - Concurrent sessions: whether a real client uses one registration for
    several concurrent sessions of the same User and resource. Re-authorizing
    in one session signs the others out (ADR-015 accepted consequence).
    Record the observed effect in the runbook. Also record whether each
    vendor connector registers a separate client per user or shares one
    `client_id` across users. A shared client serialises its authorize calls
    on the client row lock, and its token exchanges' throttled client
    `last_used_time` update can wait briefly behind an authorize, so check
    authorize and token latency under concurrent connects.
  - Grant cleanup: after a grant used to stage change sets is revoked and
    cleaned up, the change sets keep their creator, `client_id` and client
    name, and the
    revocation appears in the application log without any token.
  - Client registration metadata: confirm that every real client sends a
    `client_name` that passes ADR-015's ASCII allowlist (required, 1 to 100
    characters after trimming spaces, only ASCII letters, digits, spaces and
    `. - _ ( ) : / +`, at least one letter or digit). Names with non-ASCII
    characters or other ASCII punctuation such as `'`, `&` or `@` are
    rejected. Record any client that does not fit, and do not relax the rule
    without a separate decision.
  - Clients:
    - Claude Code locally (`https://app.localhost`, `NODE_EXTRA_CA_CERTS`);
    - claude.ai and Claude Desktop custom connectors against production
      (vendor-cloud connectors cannot reach localhost);
    - at least one non-Claude MCP client, for provider neutrality.
- Update `docs/PRODUCTION-RUNBOOK.md` and `docs/DEPLOYMENT.md`:
  - `MCP_ENABLED`, `MCP_CHANGE_SET_REVIEW_ENABLED` and
    `MCP_OAUTH_REDIRECT_URIS`;
  - enabling and disabling the feature, and enabling MCP change-set review
    before or together with production enablement (turning it on later gives
    existing write grants the apply and reject tools, although their consent
    said "proposals only"; tell users when doing so);
  - offboarding: soft-delete the Schatten User or revoke the User's grants;
    disabling the Entra account alone does not end MCP access (ADR-015
    accepted trade-off);
  - the client cap: what a full cap means (new registrations blocked, existing
    clients and grants unaffected), the warning log entry, and the immediate
    remedy of raising the cap through configuration. Lowering the
    registration rate limit only slows refilling and does not unblock a full
    cap;
  - the incident procedure, with no manual database change:
    1. set `MCP_ENABLED=false` and restart through the approved deployment
       procedure; when only MCP applies are suspicious, setting
       `MCP_CHANGE_SET_REVIEW_ENABLED=false` instead removes the apply and
       reject tools and keeps staging;
    2. revoke affected Users' grants with the admin "Revoke AI connections"
       action (or soft-delete the Users), and let Users revoke their own;
    3. reject suspicious staged change sets in the Metrics tab, and find
       change sets applied through MCP by their review channel and client;
    4. re-enable only with separate human approval;
  - what to check in logs;
  - tool schema changes: tool results are strict (`additionalProperties:
    false`), and Claude Code validates them against the output schema it
    cached when it connected. After a release that adds a field to a tool
    result (TASK-069O added the review channel to every change-set summary),
    already-connected clients reject those results until they reconnect
    (`/mcp` in Claude Code, reconnecting the connector elsewhere). Tell users
    to reconnect after such releases, and check whether vendor-cloud
    connectors behave the same way.
- Run the checklist locally and record the evidence.
- Production enablement is a separate, human-approved release. Do not deploy or
  change production settings without that approval.

### Scope Note (2026-10-30)

During implementation the developer decided that production reads
`MCP_ENABLED`, `MCP_CHANGE_SET_REVIEW_ENABLED` and `MCP_OAUTH_MAX_CLIENTS` from
the protected env file instead of fixed Compose values, so that disabling MCP
and raising the client cap are a redeploy of the current release. This task
therefore also changes `docker-compose.production.yml`,
`.github/scripts/verify-production-compose.sh`,
`.github/scripts/verify-production-runtime.sh`, `deploy/bin/check-host`,
`deploy/bin/deploy-release` (a required `--mcp-approval` reference when a
deployment turns MCP or its change-set review on, and the values in every
deployment record), `deploy/bin/ops-status`, `deploy/lib/common.sh` and
`deploy/Makefile` (`MCP_APPROVAL=`).

## Acceptance Criteria

- [x] The checklist exists, and its local run evidence is recorded.
- [x] The runbook and deployment docs describe enable, disable, offboarding
      and the incident procedure, and the checklist exercises the incident
      procedure locally.
- [ ] Production checklist items are marked pending until an authorised
      rollout, and are then completed with evidence. The 2026-11-03
      enablement recorded Claude Code with the plugin (CLI and the desktop
      app's Code tab) and a log inspection, and the checks of 2026-11-04
      recorded the claude.ai and Claude Desktop connectors with the read
      server. Still open in the checklist: the claude.ai and Claude Desktop
      connectors with the write server, whose prompts before apply and
      reject wait for the write connector to be added (enablement record and
      section 9), whether they share a registration across Users (section
      13), vendor schema caching after the next result-schema change
      (section 16 and the enablement record), the client cap and rate-limit
      buckets under real vendor-cloud traffic and the concurrency limiter,
      statement timeout and memory headroom (section 12 and the enablement
      record) and the claude.ai and Claude Desktop elicitation support
      (section 9).
- [x] The LikeC4 model and PNGs match the implemented system.
- [x] `AGENTS.md` and `ARCHITECTURE.md` mark the feature as implemented.

## Out Of Scope

- New features, CIMD support, or an in-app LLM chat.

## Implementation Notes

Read before implementation:

```text
AGENTS.md
ARCHITECTURE.md
docs/decisions/ADR-013-shared-entra-local-https-deployment.md
docs/decisions/ADR-015-ai-via-mcp.md
docs/domains/AI.md
docs/PRODUCTION-RUNBOOK.md
docs/DEPLOYMENT.md
docs/qa/AUTHENTICATION-QA-CHECKLIST.md
tasks/TASK-069A-ai-mcp-architecture.md ... tasks/TASK-069O-mcp-change-set-review.md
```

## Testing

Required:

- [ ] Manual verification (full checklist locally, then production after
      approval): local runs of 2026-10-30 and 2026-11-03 and the production
      enablement of 2026-11-03 with the claude.ai and Claude Desktop read
      connector checks of 2026-11-04, done; the items above still open
- [x] Backend and frontend suites green on the release commit (green on the
      2026-10-30 working tree, see the checklist; CI green on `df98a2e`, the
      2026-11-03 release commit)

```bash
cd backend && uv run ruff check . && uv run pytest && uv run pyright
cd ../frontend && pnpm format:check && pnpm lint && pnpm test && pnpm build
npx -y likec4@1.60.0 validate ../docs/diagrams/likec4/schatten-ai-mcp
python3 ../scripts/ai_review_records.py validate
```

## Documentation

Create `docs/qa/AI-MCP-QA-CHECKLIST.md`. Update `docs/PRODUCTION-RUNBOOK.md`,
`docs/DEPLOYMENT.md`, `ARCHITECTURE.md`, `AGENTS.md`, `README.md`, and the
LikeC4 model with its PNGs.

## Notes For AI Agent

- Branch: `docs/TASK-069P-ai-mcp-qa-rollout`.
- Do not start until TASK-069B through TASK-069O are merged.
- Never perform the production rollout without explicit human approval.
- Save each Step 13 review record under `docs/ai-reviews/TASK-069P/`.
- Report all changed files and every verification command run.
