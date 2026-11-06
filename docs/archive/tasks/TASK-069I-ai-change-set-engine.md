# TASK-069I AI Change-Set Schema And Engine

## Source Plan

This task is part of the approved plan "AI chat via MCP for generating Shadow
model and timeseries data", accepted on 2026-10-21. See
[TASK-069A](TASK-069A-ai-mcp-architecture.md), ADR-015 and
`docs/architecture/concepts/AI_CHANGE_SET.md`.

AI writes are staged as change sets. Only a human can apply them.

## Goal

Add the change-set tables, the typed operation schemas, and an engine that
resolves references between operations. The engine supports a dry-run that is
always rolled back and an atomic apply, both through the transaction cores
from TASK-069B.

## Requirements

- Add paired migrations `db/migrations/018_create_ai_change_sets.sql` and
  `018_create_ai_change_sets.down.sql`:
  - `ai_change_sets`:
    - id and `change_set_key`;
    - organisation foreign key;
    - nullable `scenario_id` foreign key (exposed as `scenario_key`). It is
      derived by the engine, never supplied by a client, and indexed for the
      review list filter;
    - title and rationale;
    - status (`draft|submitted|applied|rejected|failed|discarded`, CHECK
      constraint);
    - nullable grant foreign key, `ON DELETE SET NULL`;
    - `client_id`, the registered OAuth client identifier copied as a plain
      value (not a foreign key, so it survives client deletion);
    - `client_name`, the client's self-declared label.
    - When TASK-069F's lazy cleanup deletes a revoked or expired grant, the
      change set keeps `created_by`, `client_id` and `client_name` as its
      audit record. Change-set history is never deleted and never blocks
      cleanup;
    - `validation_result` and `applied_result` (JSON);
    - reviewed by, reviewed time and review note;
    - the standard audit columns.
  - `ai_change_set_operations`:
    - id and change-set foreign key;
    - `position` and `ref`;
    - `op_type` (CHECK list);
    - `payload` and `frozen_values` (JSON);
    - `error` (JSON).
    - Unique on (change set, position) and on (change set, ref).
- SQLAlchemy models live in `backend/app/api/v1/ai_change_sets/models.py`.
- In `schemas.py`, `ChangeSetOperation` is a discriminated union on `type`:
  - `create_scenario` and `copy_scenario`;
  - `create_org_state`;
  - `create_node`, `create_edge` and `patch_node`;
  - `create_timeserie`, `set_timeserie_values` and `generate_timeserie_values`
    (`TimeserieGenerationSpec`);
  - `create_derived_metric`;
  - `create_event`.
  - Payloads reuse the existing request schemas.
  - `$ref` applies only to server-generated keys: created or copied
    scenarios, organisation states, events and derived metrics. An operation
    that creates one may declare a `ref`, and later operations use `"$ref"`
    symbols for that key.
  - Graph nodes, graph edges and timeseries keep their client-supplied `id`,
    as in REST. Later operations refer to those keys verbatim.
  - Reject a client-supplied key that starts with `$`, and a `$` symbol that
    no earlier operation declares.
- In `engine.py`, `execute_operations(session, organisation, ops, actor_user_id)`:
  - Resolve references in order and call the `*_in_transaction` cores.
  - Return the result for each operation and the map from ref to real key.
  - Domain errors from `HTTPException` are mapped to per-operation errors.
- Derived scenario reference: whenever operations are added or removed,
  recompute `scenario_key`:
  - set it when every operation targets the same existing scenario, directly
    or through an organisation state, node, edge, timeserie or event in it;
  - set it to null when the change set creates or copies a scenario, or
    touches several scenarios.
- Dry-run uses a fresh session with a `before_commit` guard that raises, runs
  the operations in order, and always rolls back. Do not use SAVEPOINTs.
  - Stop at the first failing operation. Earlier operations report `ok`, the
    failing one reports its error, and later ones report `not_run`.
  - Roll back and `expunge_all()` the session before storing or returning the
    result, so a non-database failure cannot leave pending objects behind.
- Replacement flags: provide a read-only
  `compute_replacements(session, change_set)`. For each operation that
  replaces existing data, it returns `replaces_existing: true` and a short
  summary of what is replaced (the patched node fields with their current
  values, or the existing value count and date range). These operations are
  `patch_node`, and `set_timeserie_values` or `generate_timeserie_values` on a
  timeserie that has values.
  - The baseline is current data that existed before the change set. An
    operation on a row created earlier in the same change set (a node, or a
    timeserie and its values) is never flagged.
  - Each flagged summary includes a per-target value checksum: SHA-256 over
    the target's current replaced data in a canonical order. For a timeserie
    that is all date and value pairs, ordered by date; for a node, the patched
    fields and their current values, ordered by field name.
  - It also returns a `review_fingerprint`, a stable hash of all flags,
    summaries and checksums. Editing one existing value of a flagged
    timeserie therefore changes the fingerprint.
  - A target deleted after submit is reported in its summary as missing; the
    function does not raise. Re-validation at apply then fails.
  - It runs under the same `statement_timeout` as dry-run and apply.
  - It is computed against current data on every call and is never taken from
    submit time. TASK-069K calls it when the review detail is read, and apply
    calls it inside its locked transaction.
- Apply:
  - Run in one transaction. Lock the change-set row `FOR UPDATE` under a
    short, configurable PostgreSQL `lock_timeout` (default 5 seconds). Both
    timeouts apply to the lock wait, and the short `lock_timeout` fires
    before the longer `statement_timeout`.
  - Track the current apply step explicitly. The step alone decides whether
    the status changes, whatever the exception type or SQLSTATE:
    - an error in the lock, status or fingerprint step never changes it;
    - an error during re-validation, execution or commit marks the change set
      `failed`.

    Within the first steps, the retryable response is chosen by recognising
    the lock-not-available error (SQLSTATE `55P03`) in the lock step
    (`apply_in_progress`); any other error there is the generic retryable
    error. The same lock timeout is therefore `apply_in_progress` in the lock
    step and an operation failure during re-validation or execution.
  - The `lock_timeout` stays in force for the whole apply transaction. A
    business-row lock wait longer than it during re-validation or execution
    therefore marks the change set `failed`, which ADR-015 accepts.
  - Check the status is `submitted`; otherwise fail with a not-submitted
    error before execution.
  - Take the `review_fingerprint` the reviewer saw. Recompute it with
    `compute_replacements` inside the locked transaction. If it differs, fail
    with a `review_stale` error and change nothing. The status stays
    `submitted`, so the reviewer can reload and confirm again.
  - These two pre-execution rejections roll back and never write `failed`.
    Neither does any other error in these first steps (waiting for the lock,
    checking the status or recomputing the fingerprint). Such an error rolls
    back and returns a retryable error:
    - an `apply_in_progress` error when the change-set lock is not acquired
      within `lock_timeout` (the lock-not-available error in the lock step),
      distinct from the terminal not-submitted error;
    - a generic retryable error for anything else, such as a statement
      timeout during the recomputation.
  - A REST commit to a flagged target between this recomputation and the
    writes is the short window that ADR-015 accepts, because target rows are
    not locked.
  - Re-run validation, execute, commit once, and store `applied_result`.
    Re-validation checks validity against current data, not general staleness.
    Apply overwrites values changed after submit, as the same REST call would;
    the replacement flag is the reviewer's safeguard.
  - Only a failure from re-validation, an operation or the commit, or a lock
    or statement timeout during re-validation or execution (for example
    waiting for a business row that a REST transaction holds), marks the
    change set `failed`. On such a failure, roll back.
    Then, in a new transaction, mark the change set `failed` with the error
    through a conditional update that changes only a change set still in
    `submitted`. A concurrent apply that succeeded in the meantime is never
    overwritten.
- Freeze generated values on submit: store `frozen_values` and the
  `GENERATOR_VERSION`. Apply uses the frozen values.
- Limits: at most 500 operations and 20,000 values per change set. Set a
  PostgreSQL `statement_timeout` for dry-run, apply and the review detail's
  `compute_replacements` (configurable, default 30 seconds). Settings
  validation at startup rejects a `statement_timeout` that is not longer than
  the apply `lock_timeout`.

## Acceptance Criteria

- [ ] Up and down migrations both run on disposable PostgreSQL 18. The
      PostgreSQL migration test also checks migration 018's own rule:
      deleting a grant that a change set references sets the change set's
      `grant_id` to null and keeps `created_by`, `client_id` and
      `client_name`.
- [ ] Engine tests:
      - an end-to-end change set (scenario, org state, nodes, edge, timeserie
        with generated values, derived metric) dry-runs with zero rows
        persisted;
      - the same change set applies atomically;
      - a failing operation in the middle leaves nothing persisted;
      - dry-run of a change set with a unique violation in the middle, on
        PostgreSQL, reports `ok`, the error and `not_run` correctly and
        persists nothing;
      - the derived `scenario_key` for a single existing scenario, for a new
        scenario and for several scenarios;
      - `replaces_existing` and its summary for `patch_node` and for value
        replacement on an existing timeserie, computed against current data:
        a timeserie that gains values after submit is flagged, and
        operations on rows created earlier in the same change set are not;
      - apply with a stale `review_fingerprint` (data changed after the
        review was loaded) fails with `review_stale`, persists nothing and
        leaves the change set `submitted`;
      - running TASK-069F's lazy cleanup while a change set references a
        revoked grant: the grant is deleted, the change set's grant reference
        becomes null, `created_by`, `client_id` and `client_name` are intact,
        and the token request that triggered the cleanup succeeds. This test
        runs on PostgreSQL, or on SQLite with `PRAGMA foreign_keys=ON`, so the
        `ON DELETE SET NULL` rule itself is exercised;
      - a `review_stale` apply and a not-submitted apply leave the status
        unchanged and never write `failed`;
      - in the PostgreSQL integration module
        `backend/tests/test_ai_change_sets_postgresql_integration.py`, since
        SQLite has no row locks or lock timeouts:
        - a change-set lock not acquired within `lock_timeout` while another
          apply holds it returns `apply_in_progress` and leaves the change set
          `submitted`;
        - a lock timeout during execution, while a REST transaction holds a
          target business row, is an operation failure and marks the change
          set `failed`;
        - TASK-069B's `*_in_transaction` cores composed directly in one
          transaction on the migrated schema, with foreign keys and the
          partial unique indexes in force: a real unique-index conflict in a
          later core (for example a duplicate active timeserie key) raises
          that core's `409`, and rolling back leaves no rows from the earlier
          cores (TASK-069B review F-001).
      - a statement timeout during the fingerprint recomputation returns the
        generic retryable error and leaves the change set `submitted`. On
        SQLite, which has no statement timeout, this test injects the timeout
        error at the step boundary (for example by patching
        `compute_replacements` to raise PostgreSQL's query-cancelled error)
        and asserts the step-based classification;
      - settings validation rejects a `statement_timeout` that is not longer
        than `lock_timeout`;
      - editing a single existing value of a flagged timeserie after the
        review load (count and date range unchanged) makes apply fail with
        `review_stale`;
      - a target deleted after submit is reported as missing by
        `compute_replacements`, and apply then fails re-validation;
      - `$ref` only for server-generated keys, verbatim client keys for new
        nodes and edges, and rejection of undeclared `$` symbols;
      - ref resolution errors are clear;
      - the limits are enforced.
- [ ] A PostgreSQL integration test shows that concurrent apply of the same
      change set applies it only once. Also, when a first apply fails
      transiently (for example by `statement_timeout`) while a second apply
      succeeds, the change set ends `applied`, not `failed`.
- [ ] No MCP tool, REST route or UI is added.

## Out Of Scope

- MCP write tools (TASK-069J), the review REST API (TASK-069K) and UI.

## Implementation Notes

Read before implementation:

```text
AGENTS.md
docs/architecture/overview.md
docs/adr/0002-database-migrations.md
docs/adr/0015-ai-via-mcp.md
docs/architecture/domains/AI.md
docs/architecture/concepts/AI_CHANGE_SET.md
docs/architecture/domains/ORG_STATES.md
docs/architecture/domains/ORG_TWIN_STRUCTURE.md
docs/architecture/data/DATA-MODEL.md
docs/architecture/data/DATABASE.md
db/migrations/README.md
docs/operations/testing.md
docs/archive/tasks/TASK-069B-domain-service-transaction-cores.md
docs/archive/tasks/TASK-069C-timeseries-generator.md
```

The AI domain must not write other domains' tables directly. It goes only
through their services' transaction cores.

## Testing

Required:

- [ ] Backend tests (`backend/tests/test_ai_change_set_engine.py`)
- [ ] PostgreSQL integration tests (migrations, concurrent apply, the
      lock-timeout classification, and the composed TASK-069B cores with a
      real unique-index conflict in
      `backend/tests/test_ai_change_sets_postgresql_integration.py`, skipped
      without `MIGRATION_TEST_DATABASE_URL`, always run in CI)
- [ ] Lint
- [ ] Typecheck

```bash
cd backend
uv run ruff check .
uv run pytest
uv run pyright
MIGRATION_TEST_DATABASE_URL=postgresql://shadow:shadow_dev_password@localhost:5432/shadow \
  uv run pytest tests/test_ai_change_sets_postgresql_integration.py -v
python3 ../scripts/ai_review_records.py validate
```

## Documentation

Update `docs/architecture/data/DATABASE.md`, `docs/architecture/data/DATA-MODEL.md`,
`db/migrations/README.md`, `docs/architecture/concepts/AI_CHANGE_SET.md` and
`docs/architecture/diagrams/db-physical-schema.puml` with its SVG. Add a change-set
lifecycle diagram (`docs/architecture/diagrams/state-ai-change-set.puml` and its SVG).

## Notes For AI Agent

- Branch: `feature/TASK-069I-ai-change-set-engine`.
- Do not start until TASK-069B and TASK-069C are merged.
- Save each Step 13 review record under `docs/ai-reviews/TASK-069I/`.
- Report all changed files and every verification command run.
