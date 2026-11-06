# AI Change Set Concept

Status: accepted design in ADR-015; schema (migration 018) and engine
implemented by TASK-069I (see [Engine](#engine-task-069i)); MCP write and
change-set read tools implemented by TASK-069J and the cookie-session review
API by TASK-069K, the Metrics tab review UI by TASK-069M and the MCP
change-set review with the review channel (migration 019) by TASK-069O (see
`docs/architecture/domains/AI.md`)

## Purpose

AI Change Set tarkoittaa AI-klientin MCP:n kautta valmistelemaa, tyypitettyjen
operaatioiden joukkoa, jonka ihminen tarkistaa ja joko soveltaa tai hylkää
Shadowissa tai hyväksymällä MCP-klientin kutsun.

An AI Change Set is a proposal, not business data. Nothing in it affects
scenarios, graphs or timeseries until a human applies it, in the Metrics tab
or by approving an MCP client's `apply_change_set` call.
It is not a prediction, a forecast or an audit log of REST edits.

---

# Owner

Owning Domain:

- AI Domain

Related Domain Document:

- `docs/architecture/domains/AI.md`

Related Decision:

- `docs/adr/0015-ai-via-mcp.md`

---

# Definition

```text
An AI Change Set is an organisation-scoped, ordered list of typed operations
staged by an MCP client on behalf of one User. It is validated by a dry-run
that always rolls back, frozen on submit, and applied atomically through the
owning domains' services only when a human approves it, in Shadow or in the
MCP client.
```

---

# Key Fields

Change set (`ai_change_sets`):

- `change_set_key`: stable public key
- organisation
- `scenario_key`: optional scenario reference, derived from the operations
  (see below), never supplied by the client
- `title`, `rationale`
- `status`: `draft|submitted|applied|rejected|failed|discarded`
- grant, `client_id` and `client_name`: the MCP grant and client that staged
  it. `client_id` is copied as a plain value. `client_name` is a label the
  client declared itself. The grant reference becomes null when lazy cleanup
  deletes a revoked or expired grant, or when migration 020 deleted a grant on
  the former read or write MCP resource (TASK-074) (`ON DELETE SET NULL`);
  `created_by`, `client_id` and `client_name` stay as the audit record
- `validation_result`: per-operation result of the latest dry-run (`ok`, an
  error or `not_run`). The `replaces_existing` flags shown for review are not
  taken from it; they are recomputed against current data (see Domain Rules)
- `applied_result`: per-operation result and the `$ref` to real key map
- `reviewed_by`, `reviewed_time`, `review_note`
- `reviewed_via` (migration 019): `web` for the Metrics tab or `mcp` for an
  approved MCP client call, set exactly when `reviewed_time` is; for `mcp`
  also `review_client_id` (copied plain value) and the self-declared
  `review_client_name` of the reviewing grant's client
- `created_by` (the grant's User), `created_time`, `modified_by`,
  `modified_time`

Operation (`ai_change_set_operations`):

- `position`: order within the change set
- `ref`: optional `$ref` symbol for the key this operation creates
- `op_type`: one of the operation types below
- `payload`: the typed operation payload
- `frozen_values`: concrete generated values and generator version, set on
  submit
- `error`: the operation's latest validation or apply error

---

# Operation Types

Payloads reuse the existing REST request schemas of the owning domain.

| `op_type` | Owning domain | Effect when applied |
| --- | --- | --- |
| `create_scenario` | Organisation States | Create a scenario |
| `copy_scenario` | Organisation States | Copy a scenario |
| `create_org_state` | Organisation States | Create an organisation state |
| `create_event` | Organisation States | Create an event |
| `create_timeserie` | Organisation States | Create a timeserie definition |
| `set_timeserie_values` | Organisation States | Replace a timeserie's values with given values |
| `generate_timeserie_values` | Organisation States | Replace a timeserie's values with values generated from a `TimeserieGenerationSpec` |
| `create_derived_metric` | Organisation States | Create a derived metric equation and materialize it |
| `create_node` | Organisation Twin Structure | Create a graph node |
| `patch_node` | Organisation Twin Structure | Patch a graph node |
| `create_edge` | Organisation Twin Structure | Create a graph edge |

`$ref` covers only keys the server generates: created or copied scenarios,
organisation states, events and derived metrics. An operation creating one may
declare a `ref`, and later operations use the `"$ref"` symbol, for example a
node in an organisation state the change set creates. Graph nodes, graph edges
and timeseries take client-supplied keys (`id`), as in REST, so an edge between
two new nodes refers to their keys verbatim. A client-supplied key starting
with `$`, and a `$` symbol no earlier operation declares, are rejected.

An operation is a JSON object tagged by `type`. The REST request body is its
`payload` (camelCase keys as in REST; `generate_timeserie_values` has a `spec`
instead), and snake_case fields address the target:

```json
{"type": "create_scenario", "ref": "$plan", "payload": {"name": "AI plan"}}
{"type": "create_org_state", "ref": "$start", "scenario_key": "$plan",
 "payload": {"name": "Plan start", "targetDate": "2026-01-01"}}
{"type": "create_node", "scenario_key": "$plan", "org_state_key": "$start",
 "payload": {"id": "team_a", "name": "Team A", "nodeTypeId": "nt_person"}}
{"type": "create_edge", "scenario_key": "$plan", "org_state_key": "$start",
 "payload": {"id": "a_to_b", "name": "Reports to", "edgeTypeId": "et_reports_to",
             "sourceNodeId": "team_a", "targetNodeId": "team_b"}}
{"type": "generate_timeserie_values", "scenario_key": "$plan",
 "timeserie_key": "headcount", "spec": {"startDate": "2026-01-01", "...": "..."}}
{"type": "patch_node", "scenario_key": "reality", "org_state_key": "initial_state",
 "node_key": "hq", "payload": {"timeserieId": "$cost_per_head"}}
```

| Field | Takes | `$ref` kinds |
| --- | --- | --- |
| `scenario_key` (every operation except `create_scenario` and `copy_scenario`) | existing scenario key or ref | scenario |
| `org_state_key` (`create_node`, `create_edge`, `patch_node`) | existing org state key or ref | organisation state of the same scenario |
| `copy_scenario` `payload.sourceScenarioId`, `payload.sourceOrgStateId` | existing key or ref | scenario; organisation state of that scenario |
| `patch_node` `payload.timeserieId`, `payload.timeserieSecondaryId` | timeserie key or ref | derived metric of the same scenario |
| `node_key`, `timeserie_key`, node, edge and timeserie `id`, edge `sourceNodeId` and `targetNodeId` | client-supplied key, never `$` | none |

A `ref` matches `$` followed by a letter and up to 63 letters, digits or
underscores. A `$` symbol is rejected when no earlier operation declares it,
when it names another kind of key, when it belongs to another scenario and when
an operation redeclares it; the error names the operation position, the field
and the symbol.

---

# Scenario Reference

`scenario_key` lets the Metrics tab show the change sets of the selected
scenario. The engine recomputes it whenever operations change:

- it is set when every operation targets the same existing scenario, directly
  or through an organisation state, node, edge, timeserie or event in it;
- it is null when the change set creates or copies a scenario, or touches
  several scenarios.

The review list filters by it and can include change sets without a scenario
reference.

---

# Engine (TASK-069I)

Code: `backend/app/api/v1/ai_change_sets/` (`models.py`, `schemas.py`,
`engine.py`). TASK-069J's MCP write tools, TASK-069K's review API
(`router.py`) and TASK-069O's MCP apply and reject tools call the engine; it
adds no tool, route or UI itself.

- **Staging.** `create_change_set` starts a draft. `add_operations`,
  `remove_operation` and `discard_change_set` (added by TASK-069J) change only
  `draft` change sets and lock the change-set row, so concurrent edits of one
  draft serialise. Adding appends at the next position; removing keeps the
  other positions unchanged and is refused (`409`) while a later operation
  uses the removed operation's `ref`. Every edit of the operations enforces
  the limits, checks all references, recomputes the scenario reference and
  clears the stored validation result. Discarding sets `discarded` and keeps
  the operations. The caller commits.
- **Execution.** `execute_operations(session, organisation, ops,
  actor_user_id)` resolves refs in order, calls the owning domains'
  `*_in_transaction` cores and returns an `ExecutionResult`: per operation
  `ok` (with the scenario key and the key it created or changed), `error` or
  `not_run`, and the `$ref` to real key map. It stops at the first failing
  operation. Domain `HTTPException`s become `domain_error` with their status
  and message; reference problems `invalid_reference`; generator overflow
  `generation_error`; a request-schema validation error `invalid_operation`
  (field locations and messages, never the inputs); a database integrity
  error `conflict`; PostgreSQL's lock-not-available (`55P03`) `lock_timeout`
  and query-cancelled (`57014`) `statement_timeout`. Database messages are
  never repeated, because they can contain SQL parameters. Any other
  exception propagates.
- **Dry-run.** `dry_run` (used by `validate_change_set` and
  `submit_change_set`) runs in a fresh session with a raising `before_commit`
  guard under the change-set `statement_timeout`, then always rolls back and
  `expunge_all()`s before returning. `validate_change_set` stores the result
  in `validation_result` and each operation's error in its `error`. Because
  the dry-run uses its own connection, `validate_change_set` and
  `submit_change_set` refuse (`RuntimeError`) a session whose transaction has
  written or locked rows (on PostgreSQL, has a transaction id) or holds
  unflushed changes: the dry-run would otherwise wait, until the statement
  timeout, for a lock the caller holds, such as the key-share lock a
  change-set edit holds on its scenario row. Callers commit change-set edits
  first and check ownership without row locks. The server-generated keys in a
  dry-run result (`refs` and each operation's `key`) are provisional: those
  rows were rolled back, and apply generates new keys.
- **Submit.** `submit_change_set` locks the draft, generates every
  `generate_timeserie_values` operation once, dry-runs with exactly those
  values and, only when every operation is `ok`, stores them as
  `frozen_values` `{"generatorVersion": 1, "values": [{"date", "value"}]}` and
  sets `submitted`. Otherwise the change set stays a draft with the result.
- **Replacement flags.** `compute_replacements(session, change_set)` returns
  each operation's `replaces_existing` and summary and the
  `review_fingerprint`, a SHA-256 over all of them. Flagged are `patch_node`
  on a node, and `set_timeserie_values` or `generate_timeserie_values` on a
  timeserie with values, that existed before the change set. Summaries are
  `{"kind": "node", "scenario_key", "org_state_key", "node_key", "fields",
  "checksum"}` with the patched fields' current values, and `{"kind":
  "timeserie", "scenario_key", "timeserie_key", "value_count", "first_date",
  "last_date", "checksum"}`. A checksum is a SHA-256 over canonical JSON: the
  fields ordered by name, or all `[date, value]` pairs ordered by date. A
  missing target is flagged with `"missing": true` and the domain message. A
  node in an organisation state the change set creates is read at that state's
  target date (`get_graph_node_visible_at`).
- **Apply.** `apply_change_set(session, organisation_key, change_set_key,
  review_fingerprint, actor_user_id, *, channel)` runs the steps `lock`, `status`,
  `fingerprint`, `revalidate` (stored operations, frozen values, limits and
  references), `execute` and `commit` in one transaction under the
  `lock_timeout` and `statement_timeout`. Its `ChangeSetApplyError` carries
  the step, a code and the status afterwards:

  | Code | Step | HTTP status (TASK-069K) | Status change |
  | --- | --- | --- | --- |
  | `apply_in_progress` | `lock`, lock not available | 409, retryable | none |
  | `apply_unavailable` | any other error in `lock`, `status` or `fingerprint` | 503, retryable | none |
  | `not_submitted` | `status` | 409 | none |
  | `review_stale` | `fingerprint` | 409, reload and confirm | none |
  | `apply_failed` | `revalidate`, `execute`, `commit` | 409 | `failed`, only if still `submitted` |

  An unknown organisation or change set is a `404` `HTTPException`. A
  successful apply stores `applied_result` `{"status": "applied",
  "operations", "refs"}`; a failed one `{"status": "failed", "step", "error",
  "operations", "refs": {}}` without created keys, and the failing operation's
  `error`. A failure outside an operation that matches no other code is
  `unexpected_error`.
- **Reject.** `reject_change_set(session, organisation_key, change_set_key,
  note, actor_user_id, *, channel)` locks the change set under the same timeouts,
  requires `submitted` and records `rejected` with the reviewer, time and
  note; the caller commits. It raises only `not_submitted`,
  `apply_in_progress` and `apply_unavailable`, and does not parse the stored
  operations. TASK-069K's review API returns these codes as for apply, and
  TASK-069O's MCP tools name them in their tool errors.
- **Review channel.** `ReviewChannel.web()` or
  `ReviewChannel.mcp(client_id, client_name)` is passed explicitly to apply
  and reject, and apply passes it on to the conditional `failed` update, so
  every review records `reviewed_via` and, for MCP, the reviewing client.
- **Settings.** `AI_CHANGE_SET_STATEMENT_TIMEOUT_MS` (default 30,000) bounds
  each statement of dry-run, apply and `compute_replacements`, not their total
  duration; `AI_CHANGE_SET_LOCK_TIMEOUT_MS`
  (default 5,000) bounds apply's lock waits. Startup rejects a statement
  timeout that is not longer than the lock timeout. Both are set with
  `SET LOCAL` semantics (`set_config(..., true)`) on PostgreSQL only.

The lifecycle is drawn in
[AI change-set lifecycle](../diagrams/generated/state-ai-change-set.svg)
(`docs/architecture/diagrams/state-ai-change-set.puml`).

---

# Invariants

- A change set belongs to exactly one organisation and one creating User. It
  references its staging grant until lazy cleanup, or for a grant on the
  former read or write MCP resource migration 020, deletes that grant. After
  that, `created_by`, the copied `client_id` and `client_name` remain the audit
  record.
- Operations are ordered by unique `position`; a `ref` is unique within the
  change set and refers only to an earlier operation.
- Only a `draft` change set can be edited, and only through a grant of its
  creating User.
- A `submitted` change set is immutable. Its `generate_timeserie_values`
  operations have `frozen_values` and a generator version, and apply uses them
  instead of regenerating.
- Only a human decision moves a change set to `applied` or `rejected`: the
  cookie-session review API with CSRF and exact Origin, or, with
  `MCP_CHANGE_SET_REVIEW_ENABLED=true`, an MCP client's `apply_change_set` or
  `reject_change_set` call that the human approved. No other MCP tool makes
  these transitions.
- `reviewed_via` is set exactly when `reviewed_time` is, and the reviewing
  client exactly when it is `mcp`.
- A dry-run never persists business rows; it always rolls back. Without
  SAVEPOINTs it stops at the first failing operation, and later operations
  report `not_run`.
- Apply is all-or-nothing. Either every operation's business rows are
  committed in one transaction, or none are.
  - The apply step alone decides whether the status changes. A
    re-validation, operation or commit failure, or a lock or statement
    timeout during re-validation or execution, then marks the change set
    `failed`.
  - Any error before re-validation, in the lock, status or fingerprint
    steps, aborts and never writes `failed`. That covers:
    - the terminal not-submitted `409`;
    - `409 review_stale`;
    - the retryable `409 apply_in_progress` (lock not acquired within
      `lock_timeout`);
    - a retryable `503` for any other error there, including a status-check
      error or a statement timeout during the fingerprint recomputation.

    A stale review leaves the change set `submitted`.
- A change set is applied at most once, even under concurrent apply requests.
  `failed` is written only through a conditional update from `submitted`, so it
  never overwrites a concurrent successful apply.
- `scenario_key` is derived from the operations and never set by a client.
- Execution goes through the owning domains' `*_in_transaction` service cores;
  a change set never writes another domain's tables directly.
- Limits: at most 500 operations and 20,000 values per change set. The value
  limit counts set and generated values; the rows a `copy_scenario` copies
  from its source are not counted.

---

# Lifecycle

States:

- `draft`: being staged and validated through MCP
- `submitted`: frozen and waiting for human review
- `applied`: a human applied it, in Shadow or through MCP; business rows
  exist
- `rejected`: a human rejected it, in Shadow or through MCP, optionally
  with a note
- `failed`: apply was attempted and rolled back
- `discarded`: the creator discarded the draft through MCP

Transitions:

```text
draft -> submitted        submit_change_set (MCP, creator's grant): re-validate and freeze
draft -> discarded        discard_change_set (MCP, creator's grant)
submitted -> applied      human apply in Shadow, or apply_change_set (MCP, switch on) approved
                          by the human (either role, any creator)
submitted -> rejected     human reject in Shadow, or reject_change_set (MCP, switch on) approved
                          by the human (either role, any creator)
submitted -> failed       apply rolled back by a re-validation, operation or commit failure,
                          or a lock or statement timeout during re-validation or execution
submitted -> submitted    apply rejected before re-validation (409 review_stale, 409
                          apply_in_progress or a retryable 503): no transition
```

`applied`, `rejected`, `failed` and `discarded` are terminal. A failed change
set is not retried; the AI stages a new one.

---

# Relationships

Related Concepts:

- User (creator and reviewer)
- Organisation
- Scenario, Organisation State, Event, Timeserie, Derived Metric Equation
  (created by applied operations)
- Graph Node, Graph Edge (created or patched by applied operations)

Related Tables:

- `ai_change_sets`
- `ai_change_set_operations`
- `mcp_oauth_grants` (staging grant)

Related APIs:

- MCP write tools `create_change_set`, `add_operations`, `remove_operation`,
  `validate_change_set`, `submit_change_set`, `discard_change_set`
- MCP write tools `apply_change_set`, `reject_change_set` (TASK-069O, only
  with `MCP_CHANGE_SET_REVIEW_ENABLED=true`)
- MCP read tools `list_change_sets`, `get_change_set`, `get_change_set_review`
- `/api/v1/organisations/{organisation_key}/ai/change-sets`

---

# Domain Rules

- A human-decided apply, in the Metrics tab or through an approved MCP
  `apply_change_set` call, is the only path from AI output to business data.
- Both `admin` and `consultant` may review any submitted change set,
  including the creator, through either channel.
- The reviewer is the actor (`created_by`/`modified_by`) of the business rows
  created by apply; the change set records the creator, grant and client.
- Apply re-validates against current data: references must exist, keys must
  be unique and values must be valid. An invalid change set fails as a whole
  instead of partially applying.
- Re-validation checks validity, not staleness. `patch_node` and value
  replacement on an existing timeserie overwrite the current data at apply
  time, including changes a human made after submit, as the same REST call
  would. The review UI flags every such operation (`replaces_existing`) with
  a summary of what it replaces.
- Replacement flags use data that existed before the change set as their
  baseline. An operation on a row created earlier in the same change set is
  never flagged. Flags and summaries are recomputed read-only against current
  data each time the review detail is read, and apply recomputes them in its
  locked transaction. Summaries include a per-target checksum of each flagged
  target's current data, so editing a single timeserie value is detected.
  Apply must send back the review's `reviewFingerprint`. On a mismatch it
  fails with `409 review_stale`, changes nothing and leaves the change set
  `submitted`. A REST commit between apply's recomputation and its writes is
  an accepted short window.
- Generated values are produced by the deterministic generator, never by the
  LLM.

---

# AI Agent Guidance

When implementing this concept:

- read ADR-015 and `docs/architecture/domains/AI.md`;
- keep dry-run and apply on whole-transaction rollback; do not use SAVEPOINTs;
- add a new operation type only together with its domain core, schema, tests,
  review rendering and this document.

Avoid:

- adding an MCP apply path other than `apply_change_set` behind
  `MCP_CHANGE_SET_REVIEW_ENABLED`, or one without the review fingerprint;
- regenerating values at apply time;
- writing other domains' tables from the engine.

---

# Open Questions

- Retention of terminal change sets and frozen values.
- Additional operation types such as edge and event patches or deletions.
- A `$ref` for the initial organisation state that `copy_scenario` creates.
  Today a change set cannot add nodes to that state, because its key is
  server-generated and not named by the copy's `ref`.
- Compatibility of stored operations with later request-schema changes. An
  operation that no longer parses makes the review detail fail and apply return
  the retryable `apply_unavailable` in its fingerprint step; such a change set
  can only be rejected, by the key from the review list.
- An overall time bound for a dry-run or apply. The statement timeout bounds
  each statement, so a change set of up to 500 operations can run much longer
  than the setting while it holds a database connection.
- Input bounds beyond the MCP tool boundary. TASK-069J bounds the title (200
  characters), rationale (4,000), operation JSON per `add_operations` call
  (2 MiB) and rejects NUL characters there, but there is no bound on the total
  stored operation JSON of a change set or on single string lengths inside a
  payload other than these.
