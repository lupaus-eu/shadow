# TASK-069O AI Via MCP QA, Runbook And Production Rollout

## Source Plan

This task is part of the approved plan "AI chat via MCP for generating Schatten
model and timeseries data", accepted on 2026-10-21. See
[TASK-069A](TASK-069A-ai-mcp-architecture.md) and ADR-015.

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
  - that no business data changes before a human apply;
  - prompt injection: business text returned by read tools that tries to make
    the AI act. Writes remain human-gated.
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
  - `MCP_ENABLED` and `MCP_OAUTH_REDIRECT_URIS`;
  - enabling and disabling the feature;
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
       procedure;
    2. revoke affected Users' grants with the admin "Revoke AI connections"
       action (or soft-delete the Users), and let Users revoke their own;
    3. reject suspicious staged change sets in the Metrics tab;
    4. re-enable only with separate human approval;
  - what to check in logs.
- Run the checklist locally and record the evidence.
- Production enablement is a separate, human-approved release. Do not deploy or
  change production settings without that approval.

## Acceptance Criteria

- [ ] The checklist exists, and its local run evidence is recorded.
- [ ] The runbook and deployment docs describe enable, disable, offboarding
      and the incident procedure, and the checklist exercises the incident
      procedure locally.
- [ ] Production checklist items are marked pending until an authorised
      rollout, and are then completed with evidence.
- [ ] The LikeC4 model and PNGs match the implemented system.
- [ ] `AGENTS.md` and `ARCHITECTURE.md` mark the feature as implemented.

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
tasks/TASK-069A-ai-mcp-architecture.md ... tasks/TASK-069N-ai-skills-plugin-bundle.md
```

## Testing

Required:

- [ ] Manual verification (full checklist locally, then production after
      approval)
- [ ] Backend and frontend suites green on the release commit

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

- Branch: `docs/TASK-069O-ai-mcp-qa-rollout`.
- Do not start until TASK-069B through TASK-069N are merged.
- Never perform the production rollout without explicit human approval.
- Save each Step 13 review record under `docs/ai-reviews/TASK-069O/`.
- Report all changed files and every verification command run.
