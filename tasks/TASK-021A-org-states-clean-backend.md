# TASK-021A Org States Clean Backend

## Source Plan

Approved plan: add a synchronous backend cleanup action for organisation states
inside a selected scenario, then let the frontend refresh the org-state list.

This task covers only the backend endpoint, service behavior and backend tests.
Authentication and authorization implementation are not included in this task,
because the current repository does not yet implement that layer.

## Goal

Implement a backend cleanup endpoint for Organisation States Domain scenarios so
that a caller can clean active organisation states from a selected non-protected
scenario through one synchronous API call.

The implementation must preserve current domain rules: organisation states use
soft-delete semantics, protected scenarios cannot be mutated through normal CRUD
flows, and a scenario initial-state reference must be cleared when it points to
a cleaned state.

## Requirements

- Implement
  `POST /api/v1/organisations/{organisation_key}/scenarios/{scenario_key}/org-states/clean`.
- Keep route handlers thin in `backend/app/api/v1/org_states/router.py`.
- Put Organisation States Domain cleanup behavior in
  `backend/app/api/v1/org_states/org_states_service.py`.
- Add a response schema for the cleanup result:
  - `{ "cleaned": <n> }`
- Service behavior:
  - validate active organisation exists
  - validate active scenario exists inside the organisation
  - reject cleanup for protected scenarios with HTTP `409`
  - select active org states that belong to the selected scenario
  - soft-delete the selected org states synchronously in one transaction
  - soft-delete graph snapshots for cleaned org states through the existing
    Organisation Twin Structure service boundary
  - clear `scenarios.initial_state_id` if it points to one of the cleaned org
    states
  - return the number of cleaned org states
- Reuse existing helper patterns for active organisation, scenario and org-state
  lookup where practical.
- Add logging for the cleaned count and unexpected failures.
- Do not add new dependencies.
- Do not add a database migration.
- Do not implement authentication or authorization in this task.

## Acceptance Criteria

- [ ] Cleanup endpoint exists at
      `POST /api/v1/organisations/{organisation_key}/scenarios/{scenario_key}/org-states/clean`.
- [ ] Successful cleanup returns HTTP `200` and JSON `{ "cleaned": n }`.
- [ ] Missing active organisation or scenario returns HTTP `404`.
- [ ] Cleanup for a protected scenario returns HTTP `409`.
- [ ] Active organisation states in the selected scenario are soft-deleted by
      the cleanup call.
- [ ] Graph snapshots for cleaned org states are soft-deleted through the
      existing service boundary.
- [ ] `scenarios.initial_state_id` is cleared when it points to a cleaned org
      state.
- [ ] A cleanup call against a scenario with no active org states returns HTTP
      `200` and `{ "cleaned": 0 }`.
- [ ] No new dependency is added.
- [ ] No database migration is added.

## Out Of Scope

- Frontend button, confirm flow or refresh behavior.
- Documentation-only updates beyond small comments needed for code clarity.
- Authentication or authorization implementation.
- New permission model or membership checks.
- Scenario copy behavior.
- Graph-date synchronisation behavior.
- Event, timeseries or timeserie-value cleanup outside existing scenario-delete
  semantics unless explicitly required by current org-state ownership rules.
- Database schema changes.

## Implementation Notes

- Depends on `TASK-016 Organisation States Backend CRUD`.
- Read these before implementation:

```text
AGENTS.md
ARCHITECTURE.md
docs/decisions/ADR-001-tech-stack.md
docs/domains/ORG_STATES.md
docs/domains/ORG_TWIN_STRUCTURE.md
docs/concepts/SCENARIO.md
docs/concepts/ORGANISATION_STATE.md
docs/data/DATA-MODEL.md
docs/data/DATABASE.md
docs/TESTING.md
```

- Keep cleanup behavior aligned with current repo rules:
  - protected scenario mutation returns `409`
  - org-state deletion is a soft delete
  - graph cleanup is delegated through existing org-twin-structure service code
- The current repository does not yet implement authentication or
  authorization. Do not invent a temporary auth layer in this task.
- Prefer reusing existing mutable-scenario checks and timestamp handling.
- If implementation reveals a domain-rule conflict about which owned rows must
  be cleaned, stop and ask for human clarification before widening scope.

## Testing

Required:

- [ ] Backend tests
- [ ] Integration tests
- [ ] Manual verification
- [ ] Lint
- [ ] Typecheck

Not applicable:

- [ ] Frontend tests: no frontend code is changed in this task.
- [ ] Build: no frontend build change is expected in this task.

Commands:

```bash
cd backend
uv run ruff check .
uv run pytest
uv run pyright
```

Backend tests should cover:

- cleanup success path with multiple active org states
- cleanup returning `{ "cleaned": 0 }` when no active org states remain
- protected scenario cleanup returning `409`
- missing organisation or scenario returning `404`
- clearing `initial_state_id` when the initial org state is cleaned
- graph snapshot soft-delete for cleaned org states
- excluding already soft-deleted org states from the cleaned count

Manual verification should cover:

- create or select a non-protected scenario
- add multiple org states
- call the cleanup endpoint
- verify the response count matches cleaned active org states
- verify subsequent org-state list reads return an empty list

## Documentation

Do not treat documentation as part of this task's main scope. Planned
documentation updates belong to `TASK-021C`.

If implementation uncovers a direct mismatch that would make the code behavior
misleading without documentation, update only the minimum relevant docs:

- `docs/domains/ORG_STATES.md`
- `docs/concepts/SCENARIO.md`
- `docs/concepts/ORGANISATION_STATE.md`

## Notes For AI Agent

- Lue `AGENTS.md` ja `ARCHITECTURE.md` ennen toteutusta.
- Lue relevantit domain-, concept-, data- ja testing-dokumentit ennen
  toteutusta.
- Toteuta vain taman taskin scope.
- Ala lisaa uusia riippuvuuksia ilman hyvaksyntaa.
- Ala muuta tietokantaskeemaa tai lisaa migraatioita tassa taskissa.
- Ala toteuta autentikointia tai authorization-layeria tassa taskissa.
- Lisaa tai paivita backend-testit muutoksen riskin mukaan.
- Kerro lopuksi mita muutit ja miten tarkistit tyon.
