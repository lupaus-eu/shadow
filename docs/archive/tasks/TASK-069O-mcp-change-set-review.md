# TASK-069O MCP Change-Set Review

## Source Plan

Developer-requested amendment (2026-10-29) to the approved plan "AI chat via
MCP for generating Shadow model and timeseries data" (accepted 2026-10-21,
see [TASK-069A](TASK-069A-ai-mcp-architecture.md) and ADR-015). Users want to
apply or reject the change sets their AI staged from the same MCP client,
Claude Code or Claude Desktop, without switching to the Metrics tab. The
Metrics tab review stays unchanged.

ADR-015 rejected an MCP apply tool. This task amends ADR-015 and implements
the amendment, as TASK-059J did for ADR-013. The former TASK-069O (end-to-end
QA, runbook and production enablement) is renumbered
[TASK-069P](TASK-069P-ai-mcp-qa-rollout.md) and runs after this task.

Decisions recorded with the plan:

- **Placement.** The write server `/api/mcp/write` (scope `shadow.write`)
  gains `apply_change_set` and `reject_change_set`. A new setting
  `MCP_CHANGE_SET_REVIEW_ENABLED` (default `false`) registers them. OAuth,
  scopes, resources and grants are unchanged. A separate review server or
  scope is not added.
- **Who.** An MCP client may apply or reject any submitted change set of the
  organisation, whoever created it, with the same rule as the Metrics tab:
  both roles, the creator included. The grant's User is the reviewer and the
  actor of the created business rows.
- **Human decision.** The human decides through the client's tool approval.
  Both tools are annotated destructive. Apply needs the `review_fingerprint`
  of a fresh review read, as the web apply does. The tool texts and skills
  tell the AI to show the review to the user and act only on the user's
  explicit instruction in the conversation.
- **Audit.** Migration 019 records on the change set whether it was reviewed
  through the web (`web`) or MCP (`mcp`), and for MCP the reviewing client's
  copied `client_id` and self-declared `client_name`. The Metrics tab shows
  the channel.
- **Accepted risk.** An AI steered by injected business text can call apply
  or reject on a submitted change set, including another User's, and a human
  who approves the call without reading it applies it. The mitigations are
  the client's approval, the fingerprint, the audit record and the switch.
- **Deferred.** A server-side confirmation through MCP elicitation (the
  stateless `InputRequiredResult` flow of `mcp` 2.3.0) waits until TASK-069P
  has recorded which real clients support it.
- "Discard" of a submitted change set means reject. `discard_change_set`
  stays for drafts.

| Task | Deliverable | Dependency |
| --- | --- | --- |
| TASK-069O | ADR-015 amendment, migration 019, MCP review tools, UI and docs | `main` (TASK-069B to TASK-069N merged) |
| [TASK-069P](TASK-069P-ai-mcp-qa-rollout.md) | End-to-end QA, runbook and approved production enablement | O merged and separate approval for production |

## Goal

Let an MCP client read a submitted change set's review and apply or reject it
on behalf of its User, behind an operator switch, with the same engine, checks
and audit as the Metrics tab review.

## Requirements

- Amend [ADR-015](../../adr/0015-ai-via-mcp.md) with a dated
  amendment:
  - the status line, the context decision and the task table with TASK-069O
    and the renumbered TASK-069P;
  - a section *MCP Change-Set Review* with the decisions above;
  - the services table, the human-review rule, the incident procedure, data
    leaving Shadow, options considered, consequences, implementation rules
    and follow-up.
- Read server: `get_change_set_review(change_set_key)`, always registered,
  annotated like the other read tools. It returns the change set with each
  operation's `replaces_existing` flag and replacement summary, recomputed
  against current data, and the `review_fingerprint`. It uses the same
  single-statement load and `compute_replacements` as the review API, under
  the change-set statement timeout. Frozen values are summarised, never
  inlined. A lock or statement timeout is a retryable tool error.
- Write server, only with `MCP_CHANGE_SET_REVIEW_ENABLED=true`:
  - `apply_change_set(change_set_key, review_fingerprint)` calls the engine's
    `apply_change_set`. It returns the change set, the per-operation results
    and the `$ref` keys. Each `ChangeSetApplyError` code becomes a tool error
    whose message names the code and what to do: `review_stale` (read the
    review again and confirm with the user), `apply_in_progress` and
    `apply_unavailable` (retry), `not_submitted`, and `apply_failed` (the
    change set is now `failed`; stage a new one).
  - `reject_change_set(change_set_key, note=None)` calls the engine's
    `reject_change_set`, with the review API's note rules (at most 2,000
    characters, no NUL, blank means none).
  - Both are annotated `destructiveHint=True`, `idempotentHint=False` and
    `openWorldHint=False`, and work on any change set of a non-deleted
    organisation.
  - The server instructions and the staging tools' texts describe the in-chat
    review when the switch is on, and keep today's wording when it is off.
- Engine: an explicit review channel (`web`, or `mcp` with the client id and
  name) for apply, reject and the conditional `failed` update. The review API
  passes `web`.
- Migration `019_add_ai_change_set_review_channel.sql` and its `.down.sql`:
  - nullable `reviewed_via` (`web` or `mcp`), `review_client_id` and
    `review_client_name`;
  - backfill `web` for already reviewed change sets;
  - checks: `reviewed_via` is set exactly when `reviewed_time` is set; the
    client columns are set exactly when `reviewed_via` is `mcp`; the client id
    is not blank and the client name is 1 to 100 characters;
  - an updated table comment. Migration 018 is not edited.
- The review API's list and detail, and the MCP change-set summaries, return
  the review channel and the reviewing client's name.
- Settings and session: `MCP_CHANGE_SET_REVIEW_ENABLED` (default `false`) and
  the session feature `mcpChangeSetReview`, true only when MCP and the switch
  are both enabled. `docker-compose.production.yml` sets the switch to
  `"false"` and the compose verification asserts it; enabling it in
  production belongs to TASK-069P.
- SPA: when `mcpChangeSetReview` is true, the consent page, the connect
  instructions and the connections list describe write access as staging,
  applying and rejecting. The Metrics AI panel shows "via <client> (MCP)" for
  change sets reviewed through MCP.
- Skills and plugin: both skills describe reviewing in chat when the apply
  tools are listed and the review URL otherwise. The plugin description is
  updated and its version raised.

## Acceptance Criteria

- [ ] ADR-015 records the amendment, and no current document still states
      that no MCP tool can apply or reject a change set.
- [ ] With the switch off the write server lists exactly today's six tools.
      With it on, it also lists `apply_change_set` and `reject_change_set`
      with destructive annotations.
- [ ] MCP apply changes business data only for a submitted change set with
      the current fingerprint, and records `mcp` and the client. A stale
      fingerprint, a non-submitted change set and a failing operation behave
      as for the review API.
- [ ] A change set created by another User can be applied and rejected through
      MCP.
- [ ] Migration 019 applies, backfills and rolls back, and its constraints
      hold on PostgreSQL.
- [ ] The Metrics AI panel and the consent page show the new wording and
      channel.
- [ ] The LikeC4 model, the state diagram and the physical schema diagram
      match the implementation.

## Out Of Scope

- A separate MCP review server or scope, MCP elicitation, new operation types
  or undoing an applied change set.
- QA with real vendor clients and production enablement (TASK-069P).

## Implementation Notes

Read before implementation:

```text
AGENTS.md
docs/architecture/overview.md
docs/adr/0015-ai-via-mcp.md
docs/architecture/domains/AI.md
docs/architecture/concepts/AI_CHANGE_SET.md
docs/architecture/data/DATA-MODEL.md
docs/architecture/data/DATABASE.md
db/migrations/README.md
docs/operations/testing.md
docs/archive/tasks/TASK-069I-ai-change-set-engine.md
docs/archive/tasks/TASK-069J-mcp-write-server.md
docs/archive/tasks/TASK-069K-change-set-review-api.md
```

Branch: `feature/TASK-069O-mcp-change-set-review` from `main`. Merging it is
the human approval of the amendment.

## Testing

Required:

- [ ] Backend tests (`test_mcp_write_tools.py`, `test_mcp_tools.py`,
      `test_mcp_auth.py`, `test_ai_change_set_engine.py`,
      `test_ai_change_sets_api.py`, the auth session test)
- [ ] PostgreSQL integration tests (migration 019, constraints, concurrent MCP
      and web apply)
- [ ] Frontend tests (consent page, connect instructions, connections list,
      AI panel)
- [ ] Lint, format and typecheck

```bash
cd backend && uv run ruff check . && uv run pytest && uv run pyright
cd ../frontend && pnpm format:check && pnpm lint && pnpm test && pnpm build
npx -y likec4@1.60.0 validate ../docs/diagrams/likec4/shadow-ai-mcp
python3 ../scripts/ai_review_records.py validate
```

## Documentation

Update ADR-015, `AGENTS.md`, `docs/architecture/overview.md`, `README.md`,
`docs/architecture/domains/AI.md`, `docs/architecture/domains/DOMAIN.md`,
`docs/architecture/concepts/AI_CHANGE_SET.md`, `docs/architecture/data/DATA-MODEL.md`,
`docs/architecture/data/DATABASE.md`, `docs/architecture/deployment.md`, `docs/operations/local-development.md`,
`docs/operations/testing.md`, `docs/architecture/diagrams/state-ai-change-set.puml`,
`docs/architecture/diagrams/db-physical-schema.puml` with their SVGs, and the LikeC4 model
with its PNGs. Rename the former TASK-069O references to TASK-069P. Completed
tasks TASK-069B to TASK-069N and the review records stay unchanged as history.

## Notes For AI Agent

- Do not start until TASK-069B through TASK-069N are merged.
- Never enable MCP or the switch in production; that is TASK-069P.
- Save each Step 13 review record under `docs/ai-reviews/TASK-069O/`.
- Report all changed files and every verification command run.
