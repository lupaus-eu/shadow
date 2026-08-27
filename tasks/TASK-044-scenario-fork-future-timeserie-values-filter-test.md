# TASK-044 Scenario Fork Future Timeserie Values Filter Test

## Source Plan

Developer-approved correction: scenario forks copy every active timeserie in
the source scenario. The selected source organisation state's `target_date`
filters only copied active `timeserie_values`.

## Goal

Add regression coverage proving that a source timeserie remains present in a
fork even when its graph node and all of its values begin after the selected
source organisation-state date. The fork must omit only that timeserie's
post-cutoff values.

## Requirements

- Keep the existing scenario-copy endpoint and response contract unchanged.
- Do not filter active source timeseries by graph-node dates or timeserie links.
- Assert every active source timeserie is copied, including timeseries linked
  through the primary and secondary fields of a graph node created after the
  selected source organisation-state date.
- Assert copied values include only active source values with
  `date <= source_org_state.target_date`.
- Verify the forked timeseries API response used by the Metrics page contains
  the future-linked timeseries, while their post-cutoff values are absent.
- Do not add dependencies, migrations, public API changes, frontend changes or
  production logic changes.

## Acceptance Criteria

- [x] A future-created graph node's primary and secondary active timeseries
      are present in the fork.
- [x] Timeseries with only values after the selected source state date are
      copied as empty timeseries.
- [x] Source values exactly on the selected state date remain copied.
- [x] Source values after the selected state date are absent from the fork.
- [x] The forked `GET .../timeseries` response contains all active copied
      timeseries expected by the Metrics page.
- [x] Existing event copying, graph snapshot projection and source/target
      independence assertions continue to pass.

## Out Of Scope

- Changing scenario-fork application logic.
- Filtering timeseries by `graph_nodes.create_date` or adding a
  `timeseries.target_date` column.
- Timeserie CRUD, graph-node lifetime, event-copy, frontend or schema changes.

## Implementation Notes

Read before implementation:

```text
AGENTS.md
docs/domains/ORG_STATES.md
docs/domains/ORG_TWIN_STRUCTURE.md
docs/concepts/SCENARIO.md
docs/concepts/ORGANISATION_STATE.md
docs/data/DATA-MODEL.md
docs/TESTING.md
tasks/TASK-042-scenario-fork-timeseries-events-copy.md
tasks/TASK-044-scenario-fork-future-timeserie-values-filter-test.md
```

- Extend the existing scenario-copy API test in
  `backend/tests/test_users_organisations_api.py`.
- Use a source-state cutoff of `2030-02-01`, graph-node creation and timeserie
  values on `2030-03-01`, and assert the copied timeseries have no values.
- Retain the existing exact-cutoff value assertion as the inclusive-boundary
  regression case.

## Testing

Completed:

- [x] Backend focused scenario-copy tests
- [x] Backend full suite
- [x] Lint
- [x] Typecheck

Not applicable:

- [x] Frontend tests and build: no frontend code or API contract change.
- [x] Database migration integration tests: no schema change.
- [x] Manual verification: no visible frontend behavior changed.

Commands run:

```bash
cd backend
uv run pytest tests/test_users_organisations_api.py -k scenario_copy
uv run pytest
uv run ruff check .
uv run pyright
```

## Documentation

No current-state documentation change is required: the existing scenario-copy
documentation already states that every active source timeserie is copied and
only values through the selected source organisation-state date are included.

## Notes For AI Agent

- Implement only this task's test scope.
- Do not change scenario-fork logic, schema, APIs or dependencies.
- Report the changed test and verification commands.
