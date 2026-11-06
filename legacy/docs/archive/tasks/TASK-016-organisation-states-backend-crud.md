# TASK-016 Organisation States Backend CRUD

## Source Plan

Approved plan: implement backend CRUD for Organisation States Domain scenarios and organisation states.

This task adds thin FastAPI routes and service-layer business logic for scenario and org-state CRUD. It preserves the current frontend path shape under organisations and keeps non-CRUD behavior for later tasks.

## Goal

Implement backend CRUD operations for scenarios and organisation states.

The implementation should make the existing Scenarios frontend API contract persist against the backend for create, read, update and soft delete behavior, while preserving Organisation States Domain ownership and lifecycle rules.

## Requirements

- Add `backend/app/api/v1/org_states/router.py`.
- Include the org-states router from `backend/app/api/v1/router.py`.
- Keep route handlers thin.
- Put business logic in `backend/app/api/v1/org_states/org_states_service.py`.
- Move the existing scenario and org-state list endpoints out of the organisations router into the new org-states router without changing public URLs.
- Preserve these public paths:
  - `GET /api/v1/organisations/{organisation_key}/scenarios`
  - `POST /api/v1/organisations/{organisation_key}/scenarios`
  - `GET /api/v1/organisations/{organisation_key}/scenarios/{scenario_key}`
  - `PATCH /api/v1/organisations/{organisation_key}/scenarios/{scenario_key}`
  - `DELETE /api/v1/organisations/{organisation_key}/scenarios/{scenario_key}`
  - `GET /api/v1/organisations/{organisation_key}/scenarios/{scenario_key}/org-states`
  - `POST /api/v1/organisations/{organisation_key}/scenarios/{scenario_key}/org-states`
  - `GET /api/v1/organisations/{organisation_key}/scenarios/{scenario_key}/org-states/{org_state_key}`
  - `PATCH /api/v1/organisations/{organisation_key}/scenarios/{scenario_key}/org-states/{org_state_key}`
  - `DELETE /api/v1/organisations/{organisation_key}/scenarios/{scenario_key}/org-states/{org_state_key}`
- Use stable text keys in API paths and responses.
- Generate new `scenario_key` and `org_state_key` values server-side.
- Keep scenario responses compatible with `{ id, name, description, protected }`.
- Keep org-state responses compatible with `{ id, name, description, targetDate }`.
- Use Pydantic request and response schemas that inherit `StrictBaseModel`.
- Validate required names in request schemas.
- Exclude soft-deleted scenarios and org states from normal reads.
- Implement scenario soft delete as normal application deletion behavior.
- Propagate scenario soft delete to active owned organisation states, events, timeseries, timeserie values and graph snapshots through the appropriate service/domain boundary.
- Implement org-state delete as a soft delete.
- Clear `scenarios.initial_state_id` if the deleted org state is the scenario initial state.
- Reject mutation of protected scenarios with HTTP 409.
- Enforce active org-state `targetDate` uniqueness within a scenario for non-null target dates with HTTP 409.

## Acceptance Criteria

- [ ] `backend/app/api/v1/org_states/router.py` exists and is included by the v1 API router.
- [ ] Existing scenario and org-state list URLs still work after moving route ownership to the org-states router.
- [ ] Routes call services; business logic is not embedded in route handlers.
- [ ] Scenario CRUD supports list, get, create, patch and soft delete.
- [ ] Org-state CRUD supports list, get, create, patch and soft delete.
- [ ] Scenario create returns HTTP 201 and a frontend-compatible response.
- [ ] Org-state create returns HTTP 201 and a frontend-compatible response.
- [ ] Patch endpoints update only fields in task scope and update `modified_time`.
- [ ] Delete endpoints return HTTP 204.
- [ ] Missing active organisation, scenario or org state returns HTTP 404.
- [ ] Protected scenario patch and delete return HTTP 409.
- [ ] Soft-deleted scenarios and org states are excluded from list and get endpoints.
- [ ] Scenario soft delete propagates to active owned rows required by Organisation States Domain lifecycle rules.
- [ ] Deleting an initial org state clears the parent scenario `initial_state_id`.
- [ ] Duplicate active non-null target dates inside a scenario return HTTP 409.
- [ ] No database migration is added.
- [ ] No new dependency is added.

## Out Of Scope

- Scenario copy behavior.
- Org-state graph-date synchronisation behavior.
- Frontend changes.
- Database schema changes.
- Authentication or authorization.
- Event CRUD.
- Timeseries CRUD.
- Graph editing or graph copy behavior.
- Metamodel copy behavior.
- Changes to production data.

## Implementation Notes

- Depends on `TASK-014 Users And Organisations Backend CRUD`.
- Depends on `TASK-015 Organisation Defaults And Frontend Flow`.
- Read these before implementation:

```text
AGENTS.md
docs/architecture/overview.md
docs/adr/0001-tech-stack.md
docs/architecture/domains/ORG_STATES.md
docs/architecture/concepts/SCENARIO.md
docs/architecture/concepts/ORGANISATION_STATE.md
docs/architecture/data/DATA-MODEL.md
docs/architecture/data/DATABASE.md
docs/operations/testing.md
```

- The public API remains nested under organisations because the existing frontend client already uses that path shape.
- Use the existing Organisations service boundary to validate active organisations.
- Use SQLAlchemy ORM and the existing `Session` dependency pattern.
- Keep audit user fields nullable until authentication exists.
- Suggested generated key prefixes:
  - `scenario_{uuid}`
  - `org_state_{uuid}`
- Do not implement `POST /scenarios/copy` or `POST /org-states/synchronise-graph-dates` in this task.
- If soft-delete propagation needs ORM models for owned tables that are not yet mapped, add only minimal model coverage needed for service behavior and tests. Do not change the database schema.

## Testing

Required:

- [ ] Backend tests
- [ ] Integration tests
- [ ] Manual verification
- [ ] Lint
- [ ] Typecheck

Not applicable:

- [ ] Frontend tests: no frontend code is changed in this task.
- [ ] Build: no frontend build changes.

Commands:

```bash
cd backend
uv run ruff check .
uv run pytest
uv run pyright
```

Backend tests should cover:

- scenario create, list, get, patch and delete
- org-state create, list, get, patch and delete
- stable keys in response `id` fields
- missing parent and missing resource 404 behavior
- blank name validation
- protected scenario mutation returning 409
- duplicate active org-state target date returning 409
- soft-deleted target dates being reusable
- soft-deleted scenarios and org states being excluded from reads
- scenario soft-delete propagation to owned rows covered by the implementation
- existing organisation default creation behavior still passing

Manual verification should cover:

- create an organisation
- list default scenario and org state
- create, update and delete a non-protected scenario
- create, update and delete an org state
- verify protected Reality scenario cannot be patched or deleted

## Documentation

Do not update documentation in this task unless implementation uncovers a direct mismatch that blocks accurate behavior. Planned documentation updates are covered by `TASK-017`.

## Notes For AI Agent

- Toteuta vain taman taskin scope.
- Ala lisaa uusia riippuvuuksia ilman hyvaksyntaa.
- Ala muuta tietokantaskeemaa tassa taskissa.
- Ala toteuta scenario copy- tai org-state synchronise -endpointteja tassa taskissa.
- Lue relevantit domain-, concept-, data- ja testing-dokumentit ennen toteutusta.
- Lisaa tai paivita testit muutoksen riskin mukaan.
- Aja saatavilla olevat backend-tarkistukset ja raportoi tulokset.
