# TASK-042 Scenario Fork Timeseries And Events Copy

## Source Plan

Developer-approved follow-up to scenario-fork behavior: a fork must copy the
source scenario's timeseries and their data, as well as its events. The selected
source organisation state establishes an inclusive cutoff: copy only active
timeserie values and events dated on or before that state’s `target_date`.

TASK-027 and TASK-041B are retained unchanged as historical decision records.
This task supersedes their no-timeseries-copy scope only for the implementation
and current-state documentation listed below.

## Goal

Make scenario forks self-contained for metrics and events that existed at the
selected source organisation state. The copied scenario must receive
independent active timeseries definitions, values and events through the
selected state date, while the source scenario remains unchanged.

Copied graph nodes must retain valid metric links by referencing the matching
copied timeseries rather than the source scenario's rows.

## Requirements

- Keep the existing scenario-copy endpoint and request/response contract:
  `POST /api/v1/organisations/{organisation_key}/scenarios/copy`.
- Keep the existing selected-org-state behavior: exactly one organisation state
  is copied, and its `target_date` is the inclusive timeserie-value cutoff.
- Copy every active source-scenario timeserie, including a series with no
  eligible values.
- Preserve each copied timeserie's stable `timeserie_key`, `name`,
  `description`, `unit`, `time_unit` and `value_unit`; the target receives a
  new internal `timeserie_id`.
- Copy only active `timeserie_values` whose `date` is less than or equal to the
  selected source organisation state's `target_date`. Preserve each eligible
  value's date and JSON value payload under the matching copied timeserie.
- Do not copy soft-deleted timeseries, soft-deleted values, or active values
  after the selected source-state date.
- Set `created_by` on all copied timeseries and values to the authenticated
  actor. Do not copy source audit, persistence identity, or soft-delete data.
- Copy active source-scenario events whose `target_date` is less than or equal
  to the selected source organisation state's `target_date`.
- Preserve each copied event's stable `event_key`, `name`, `target_date`,
  `version` and `event_details`; the target receives a new internal `event_id`
  and the authenticated actor as `created_by`.
- Do not copy soft-deleted events or active events after the selected
  source-state date. Do not copy source event audit, persistence identity or
  soft-delete data.
- Extend the Organisation Twin Structure graph-copy service boundary with a
  source-to-copied-timeserie ID mapping. Copied graph nodes must translate both
  primary and secondary timeserie references through that mapping.
- Preserve the existing graph snapshot date semantics and all other scenario
  copy behavior. Do not copy metamodel data, prediction versions or prediction
  results.
- Perform the scenario, selected organisation state, events, timeseries,
  values and graph snapshot copy in the existing single database transaction.
  A failed copy must not leave a partial target scenario.
- Do not add dependencies, alter the public API, or add a database migration.

## Acceptance Criteria

- [ ] Forking a scenario creates active target timeseries for every active
      source timeserie, with preserved stable keys and metadata.
- [ ] The fork includes only active source values with dates on or before the
      selected source organisation state's `target_date`.
- [ ] A source timeserie with no eligible values is still copied.
- [ ] Active values after the selected source-state date and all soft-deleted
      source timeseries or values are absent from the target.
- [ ] The fork includes active source events only when their `target_date` is
      on or before the selected source organisation state's `target_date`.
- [ ] Copied events preserve their stable keys and fields, receive distinct
      persistence IDs and the forking user as `created_by`.
- [ ] Active source events after the selected source-state date and all
      soft-deleted source events are absent from the target.
- [ ] Copied timeseries and values have different persistence IDs from their
      source rows and have the forking user as `created_by`.
- [ ] Copied graph nodes preserve primary and secondary metric links by
      referencing the matching copied target-scenario timeseries; no copied
      node references a source-scenario timeserie.
- [ ] Editing or soft-deleting a copied timeserie or value does not change the
      source, and vice versa.
- [ ] Existing source validation, protected-source, generated-name and
      selected-org-state fork behavior remains unchanged.
- [ ] The copy response remains the existing frontend-compatible scenario DTO
      with HTTP `201`.
- [ ] No database migration, public API field, frontend code, dependency,
      metamodel copy or prediction-data copy is added.

## Out Of Scope

- Copying organisation states other than the selected source state.
- Copying timeserie values or events later than the selected source-state date.
- Changing Forecasting algorithms, target-observation override policy or saved
  prediction data.
- Changing timeserie CRUD APIs, value validation, stable-key rules or database
  schema.
- Frontend Scenarios-tab changes.
- Revising the historical task files
  `docs/archive/tasks/TASK-027-fix-scenario-fork-state-copy.md` or
  `docs/archive/tasks/TASK-041B-predictions-backend-modeling.md`.

## Implementation Notes

Read before implementation:

```text
AGENTS.md
docs/architecture/overview.md
docs/adr/0007-predictions-forecasting-domain.md
docs/adr/0008-target-scenario-observation-overrides.md
docs/architecture/domains/ORG_STATES.md
docs/architecture/domains/ORG_TWIN_STRUCTURE.md
docs/architecture/concepts/SCENARIO.md
docs/architecture/concepts/ORGANISATION_STATE.md
docs/architecture/data/DATA-MODEL.md
docs/architecture/data/DATABASE.md
docs/operations/testing.md
docs/archive/tasks/TASK-027-fix-scenario-fork-state-copy.md
docs/archive/tasks/TASK-041B-predictions-backend-modeling.md
```

- Extend `copy_scenario` in
  `backend/app/api/v1/org_states/org_states_service.py` after the target
  scenario and selected target organisation state have been created, but before
  graph snapshot copying and the final commit.
- Query active source events and copy those with `target_date <=
  source_org_state.target_date`, in deterministic `target_date`, `event_id`
  order. Preserve the event's public key and fields while creating a new target
  row with the current actor as `created_by`.
- Query source timeseries and values with active-row filters. Order copied
  timeseries deterministically by `timeserie_key`, `timeserie_id`, and values
  by `date`, `timeserie_value_id`.
- Build a `{source_timeserie_id: copied_timeserie_id}` map while flushing copied
  timeseries. Use a deep copy of the JSON value payload when constructing each
  copied `TimeserieValue`.
- Extend
  `backend/app/api/v1/org_twin_structure/org_twin_structure_service.py` so
  `copy_graph_snapshots_for_org_states` accepts the mapping and assigns mapped
  primary/secondary timeserie IDs to copied nodes. Keep the service boundary:
  Organisation States owns copying its data; Organisation Twin Structure owns
  graph-row creation.
- An active source graph node can only reference an active source-scenario
  timeserie. Treat a missing map entry as an invalid copy invariant rather than
  silently retaining a cross-scenario reference.
- No router, Pydantic schema, frontend API-client, migration or diagram change
  is expected.
- ADR-008 already defines how target-scenario values participate in prediction
  observation history; this task does not amend that policy. No ADR is expected
  unless implementation uncovers an architectural conflict.

## Testing

Required:

- [ ] Backend tests
- [ ] Manual verification
- [ ] Lint
- [ ] Typecheck

Not applicable:

- [ ] Frontend tests and build: no frontend code or API contract changes are
      expected; run them only if implementation changes frontend code.
- [ ] Database migration integration tests: this task makes no schema change.

Commands:

```bash
cd backend
uv run ruff check .
uv run pytest tests/test_users_organisations_api.py
uv run pytest
uv run pyright
```

Backend tests must cover:

- copying source events before and exactly on the selected state date, while
  excluding later and soft-deleted events;
- copied-event field preservation, new persistence identity, audit actor and
  source/target mutation independence;
- copying multiple active timeseries with number, string and boolean values;
- inclusive cutoff behavior for a value exactly on the selected state date;
- exclusion of later and soft-deleted values and soft-deleted timeseries;
- copying an active timeserie that has no qualifying value;
- target/source persistence and mutation independence;
- mapping both graph-node timeserie references to copied target rows; and
- existing copy failures and audit-actor behavior as regression coverage.

Manual verification must cover:

- create source events and metrics with dates before, on and after a selected
  org-state date;
- fork from that state and open Metrics and Structure for the new scenario;
- confirm only through-cutoff events and values, plus valid copied graph metric
  links, appear;
- edit a copied value and confirm the source value is unchanged.

## Documentation

After implementation and tests, update current-state documentation:

- `docs/architecture/domains/ORG_STATES.md`
- `docs/architecture/domains/ORG_TWIN_STRUCTURE.md`
- `docs/architecture/concepts/SCENARIO.md`
- `docs/architecture/concepts/ORGANISATION_STATE.md`
- `docs/architecture/data/DATA-MODEL.md`

Document that scenario copy duplicates active source events, timeseries and
timeserie values only through the selected source organisation-state date, and
that graph timeserie references are remapped to the copied scenario.

Do not modify `docs/archive/tasks/TASK-027-fix-scenario-fork-state-copy.md` or
`docs/archive/tasks/TASK-041B-predictions-backend-modeling.md`; they intentionally retain
their historical decision context.

## Notes For AI Agent

- Implement only this task's scope.
- Preserve soft-delete, audit-actor, stable-key and same-scenario graph-link
  invariants.
- Add backend tests for all changed domain behavior.
- Do not add dependencies or a migration without approval.
- Report changed files and all checks run.
