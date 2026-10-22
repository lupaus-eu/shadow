# AI Change Set Concept

Status: accepted design in ADR-015; implementation pending TASK-069I through
TASK-069M

## Purpose

AI Change Set tarkoittaa AI-asiakkaan MCP:n kautta valmistelemaa, tyypitettyjen
operaatioiden joukkoa, jonka ihminen tarkistaa ja joko soveltaa tai hylkää
Schattenissa.

An AI Change Set is a proposal, not business data. Nothing in it affects
scenarios, graphs or timeseries until a human applies it in the Metrics tab.
It is not a prediction, a forecast or an audit log of REST edits.

---

# Owner

Owning Domain:

- AI Domain

Related Domain Document:

- `docs/domains/AI.md`

Related Decision:

- `docs/decisions/ADR-015-ai-via-mcp.md`

---

# Definition

```text
An AI Change Set is an organisation-scoped, ordered list of typed operations
staged by an MCP client on behalf of one User. It is validated by a dry-run
that always rolls back, frozen on submit, and applied atomically through the
owning domains' services only when a human approves it in Schatten.
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
  deletes a revoked or expired grant (`ON DELETE SET NULL`); `created_by`,
  `client_id` and `client_name` stay as the audit record
- `validation_result`: per-operation result of the latest dry-run (`ok`, an
  error or `not_run`). The `replaces_existing` flags shown for review are not
  taken from it; they are recomputed against current data (see Domain Rules)
- `applied_result`: per-operation result and the `$ref` to real key map
- `reviewed_by`, `reviewed_time`, `review_note`
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

# Invariants

- A change set belongs to exactly one organisation and one creating User. It
  references its staging grant until lazy cleanup deletes that grant. After
  that, `created_by`, the copied `client_id` and `client_name` remain the audit
  record.
- Operations are ordered by unique `position`; a `ref` is unique within the
  change set and refers only to an earlier operation.
- Only a `draft` change set can be edited, and only through a grant of its
  creating User.
- A `submitted` change set is immutable. Its `generate_timeserie_values`
  operations have `frozen_values` and a generator version, and apply uses them
  instead of regenerating.
- No MCP tool can move a change set to `applied` or `rejected`. Those
  transitions require a human through the cookie-session review API with CSRF
  and exact Origin.
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
- Limits: at most 500 operations and 20,000 values per change set.

---

# Lifecycle

States:

- `draft`: being staged and validated through MCP
- `submitted`: frozen and waiting for human review
- `applied`: a human applied it; business rows exist
- `rejected`: a human rejected it, optionally with a note
- `failed`: apply was attempted and rolled back
- `discarded`: the creator discarded the draft through MCP

Transitions:

```text
draft -> submitted        submit_change_set (MCP, creator's grant): re-validate and freeze
draft -> discarded        discard_change_set (MCP, creator's grant)
submitted -> applied      human apply in Schatten (either role)
submitted -> rejected     human reject in Schatten (either role)
submitted -> failed       human apply rolled back by a re-validation, operation or commit failure,
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
- MCP read tools `list_change_sets`, `get_change_set`
- `/api/v1/organisations/{organisation_key}/ai/change-sets`

---

# Domain Rules

- The human apply is the only path from AI output to business data.
- Both `admin` and `consultant` may review, including the creator.
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

- read ADR-015 and `docs/domains/AI.md`;
- keep dry-run and apply on whole-transaction rollback; do not use SAVEPOINTs;
- add a new operation type only together with its domain core, schema, tests,
  review rendering and this document.

Avoid:

- adding an MCP apply path;
- regenerating values at apply time;
- writing other domains' tables from the engine.

---

# Open Questions

- Retention of terminal change sets and frozen values.
- Additional operation types such as edge and event patches or deletions.
