# TASK-018 Scenario Copy And Scenario Refresh Follow-Up

## Source Plan

Approved plan: keep scenario copy and org-state graph-date synchronisation out
of the first Organisation States CRUD task.

This follow-up task exists because the current frontend Scenarios tab expects
scenario copy behavior and currently has a Refresh action wired to a
non-existing graph-date synchronisation endpoint.

## Goal

Implement scenario copy behavior needed by the frontend Scenarios tab, and
update Refresh so it reloads the selected scenario and its org states through
existing read endpoints.

## Requirements

- Implement `POST /api/v1/organisations/{organisation_key}/scenarios/copy`.
- Keep route handlers thin.
- Put Organisation States Domain behavior in `org_states_service.py`.
- Coordinate graph snapshot copying through Organisation Twin Structure Domain
  service boundaries.
- Scenario copy request uses:
  - `sourceScenarioId`
  - `sourceOrgStateId`
  - `name`
  - `description`
- Scenario copy behavior:
  - source scenario lookup is organisation-scoped and active-only
  - source org-state lookup is active-only inside the selected source scenario
  - copied scenario gets a generated `scenario_key`
  - copied scenario uses request `name` and `description`
  - copied scenario always has `protected=false`, including copies from
    protected `Reality`
  - copied scenario `source_scenario_id` points to the selected source scenario
  - copy all active source org states that belong to the source scenario and
    have `target_date <= sourceOrgStateId.target_date`; `target_date` is
    mandatory for org states, so no null-date copy boundary is supported
  - copied org states get generated `org_state_key` values and preserve `name`,
    `description`, `target_date` and `version`
  - copied scenario `initial_state_id` points to the copied version of
    `sourceOrgStateId`
  - copy active graph snapshots for copied org states through Organisation Twin
    Structure Domain service code
  - do not mutate the source scenario, source org states or source graphs
- Refresh behavior:
  - do not implement
    `POST /api/v1/organisations/{organisation_key}/scenarios/{scenario_key}/org-states/synchronise-graph-dates`
  - frontend Refresh for a selected scenario calls:
    - `GET /api/v1/organisations/{organisation_key}/scenarios/{scenario_key}`
    - `GET /api/v1/organisations/{organisation_key}/scenarios/{scenario_key}/org-states`
  - update the selected scenario/sidebar data and current org-state list from
    those responses
- Add backend and frontend tests for success and failure paths.
- Update relevant domain and concept documentation.

## Acceptance Criteria

- [ ] Scenario copy endpoint exists at
      `POST /api/v1/organisations/{organisation_key}/scenarios/copy`.
- [ ] Scenario copy returns a frontend-compatible scenario response with HTTP
      `201`.
- [ ] Scenario copy rejects missing organisation, source scenario or source org
      state with HTTP `404`.
- [ ] Scenario copy from protected source scenarios is allowed and creates an
      unprotected target scenario.
- [ ] Scenario copy only copies org states that belong to the selected source
      scenario and are within the selected target-date boundary.
- [ ] Scenario copy copies active graph snapshots for copied org states.
- [ ] Scenario copy sets `source_scenario_id` and `initial_state_id` according
      to the defined rules.
- [ ] Scenario copy does not mutate source rows.
- [ ] No graph-date synchronisation endpoint is added.
- [ ] Refresh no longer calls `synchronise-graph-dates`.
- [ ] Refresh updates selected scenario data and selected scenario org states
      using GET endpoints.
- [ ] Documentation describes implemented copy semantics and states that
      graph-date synchronisation is not implemented.
- [ ] No new dependency is added without approval.

## Out Of Scope

- Basic scenario CRUD.
- Basic org-state CRUD.
- Users CRUD.
- Organisations CRUD.
- General graph editing UI.
- Event CRUD.
- Timeseries CRUD or timeseries value copy.
- Authentication or authorization.
- Database schema changes unless separately approved and documented.
- Graph-date-derived org-state creation, deletion or synchronisation.

## Implementation Notes

- Depends on `TASK-016 Organisation States Backend CRUD`.
- Coordinate with `TASK-017 Organisation States CRUD Documentation` so docs do
  not claim graph-date synchronisation exists.
- Read these before implementation:

```text
AGENTS.md
docs/architecture/overview.md
docs/adr/0001-tech-stack.md
docs/architecture/domains/ORG_STATES.md
docs/architecture/domains/ORG_TWIN_STRUCTURE.md
docs/architecture/concepts/SCENARIO.md
docs/architecture/concepts/ORGANISATION_STATE.md
docs/architecture/data/DATA-MODEL.md
docs/architecture/data/DATABASE.md
docs/operations/testing.md
```

- Add or update an ADR only if the implementation changes architecture, data
  strategy, deployment strategy or another significant technical decision.
- No new dependency is expected.

## Testing

Required:

- [ ] Backend tests
- [ ] Frontend tests
- [ ] Integration tests
- [ ] Manual verification
- [ ] Lint
- [ ] Typecheck
- [ ] Frontend build

Commands:

```bash
cd backend
uv run ruff check .
uv run pytest
uv run pyright

cd frontend
pnpm lint
pnpm test
pnpm build
```

Backend tests should cover:

- scenario copy success path
- source scenario not found
- source org state not found
- copy from protected source scenario
- copied scenario and source scenario independence
- source org-state scenario ownership enforcement
- source org-state target-date boundary
- graph snapshot copy
- interaction with soft-deleted scenarios, org states and graphs

Frontend tests should cover:

- Refresh calls selected scenario GET and org-states GET
- Refresh updates selected scenario and org-state data
- Refresh does not call the old synchronise endpoint

Manual verification should cover:

- copy a scenario from the Scenarios tab
- verify the copied scenario appears in scenario list
- refresh selected scenario from the Scenarios toolbar refresh action
- verify returned org states remain ordered by target date

## Documentation

Update documentation only after behavior is implemented and tested.

Expected documentation targets:

- `docs/architecture/domains/ORG_STATES.md`
- `docs/architecture/domains/ORG_TWIN_STRUCTURE.md`, for graph snapshot copy behavior
- `docs/architecture/concepts/SCENARIO.md`
- `docs/architecture/concepts/ORGANISATION_STATE.md`
- data and diagram documentation only if schema, relationships or ownership
  change

## Notes For AI Agent

- Toteuta vain taman taskin scope.
- Ala toteuta tata ennen kuin CRUD task on valmis.
- Ala toteuta graph-date synchronisation -endpointtia tassa taskissa.
- Kayta olemassa olevia service-rajoja domainien valilla.
- Lisaa tai paivita testit muutoksen riskin mukaan.
- Kerro lopuksi mita muutettiin ja miten tyo tarkistettiin.
