# TASK-023 Protected Scenarios Editable

## Source Plan

Approved plan: allow protected scenarios, especially the default `Reality`
scenario, to have their `name` and `description` patched through the backend
API while keeping destructive protected-scenario guards in place.

This task covers backend service behavior, backend regression tests and domain
documentation updates.

## Goal

Update Organisation States Domain scenario semantics so protected scenarios are
not fully immutable. A protected scenario may be renamed and redescribed through
the normal scenario PATCH endpoint, but it must still be protected from
destructive operations.

The change should align backend behavior with the Scenarios tab expectation
that `Reality` can be edited while deletion and organisation-state cleanup
remain unavailable.

## Requirements

- Allow
  `PATCH /api/v1/organisations/{organisation_key}/scenarios/{scenario_key}` to
  update `name` and `description` for protected scenarios.
- Keep protected-scenario delete behavior unchanged:
  `DELETE /api/v1/organisations/{organisation_key}/scenarios/{scenario_key}`
  must continue to return HTTP `409`.
- Keep protected-scenario cleanup behavior unchanged:
  `POST /api/v1/organisations/{organisation_key}/scenarios/{scenario_key}/org-states/clean`
  must continue to return HTTP `409`.
- Keep scenario patch validation unchanged for allowed fields, including blank
  name validation.
- Reuse existing service patterns in
  `backend/app/api/v1/org_states/org_states_service.py`.
- Add or update backend tests in
  `backend/tests/test_users_organisations_api.py`.
- Update protected-scenario language in domain and concept documentation.
- Do not add dependencies.
- Do not add database schema changes or migrations.
- Do not implement frontend changes in this task.

## Acceptance Criteria

- [ ] Protected scenario PATCH for `name` succeeds with HTTP `200`.
- [ ] Protected scenario PATCH for `description` succeeds with HTTP `200`.
- [ ] Patching the default `Reality` scenario persists the changed `name` and
      `description`.
- [ ] Protected scenario DELETE still returns HTTP `409`.
- [ ] Protected scenario organisation-state cleanup still returns HTTP `409`.
- [ ] Non-protected scenario patch behavior continues to work.
- [ ] Scenario patch validation for blank `name` remains enforced.
- [ ] Domain docs state that protected scenarios can be renamed/described but
      cannot be deleted or cleaned.
- [ ] No new dependency is added.
- [ ] No database migration is added.

## Out Of Scope

- Frontend UI changes.
- Database schema, migration or seed-data changes.
- Authentication or authorization changes.
- New scenario fields or additional editable protected-scenario fields.
- Changes to organisation-state PATCH, DELETE or cleanup semantics except for
  preserving the existing protected cleanup guard.
- Changes to scenario copy behavior.
- ADR changes.

## Implementation Notes

- Read these before implementation:

```text
AGENTS.md
docs/architecture/overview.md
docs/adr/0001-tech-stack.md
docs/architecture/domains/ORG_STATES.md
docs/architecture/concepts/SCENARIO.md
docs/operations/testing.md
```

- Primary implementation target:

```text
backend/app/api/v1/org_states/org_states_service.py
```

- Primary test target:

```text
backend/tests/test_users_organisations_api.py
```

- Current behavior to review:
  - `patch_scenario` calls `_ensure_scenario_is_mutable`.
  - `soft_delete_scenario` calls `_ensure_scenario_is_mutable`.
  - `clean_org_states` calls `_ensure_scenario_is_mutable`.
- Update `patch_scenario` so protected scenarios are allowed through the patch
  path for `name` and `description`.
- Keep destructive protections in delete and cleanup flows. If the current
  helper name becomes misleading, introduce or rename a helper for destructive
  protected-scenario guards while keeping the behavior scoped.
- Documentation targets:

```text
docs/architecture/concepts/SCENARIO.md
docs/architecture/domains/ORG_STATES.md
```

- Search for any other current domain or concept documentation that says
  protected scenarios cannot be patched, and update it if found.
- Do not update historical task files unless the implementation uncovers a
  direct current-source-of-truth conflict outside this task.
- No ADR is expected because this is a scoped domain/API semantics adjustment,
  not a technology or architecture decision.

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

- patching the default `Reality` scenario name and description returns HTTP
  `200`
- patched `Reality` scenario name and description persist on a follow-up read
- deleting the protected `Reality` scenario still returns HTTP `409`
- cleaning organisation states for the protected `Reality` scenario still
  returns HTTP `409`
- existing non-protected scenario patch behavior still succeeds
- blank protected scenario `name` PATCH still returns validation error

Manual verification should cover:

- create or select an organisation with the default `Reality` scenario
- call
  `PATCH /api/v1/organisations/{organisation_key}/scenarios/reality` with new
  `name` and `description`
- verify the response is HTTP `200`
- verify a follow-up GET returns the updated values
- verify DELETE and org-state cleanup for the same protected scenario still
  return HTTP `409`

## Documentation

Update these source-of-truth docs:

- `docs/architecture/concepts/SCENARIO.md`
- `docs/architecture/domains/ORG_STATES.md`

The updated docs must say that protected scenarios:

- can be patched for `name` and `description`
- cannot be deleted through normal backend CRUD flows
- cannot be cleaned through the backend organisation-state cleanup flow

No data model, database, architecture, diagram or ADR updates are expected.

## Notes For AI Agent

- Lue `AGENTS.md` ja `docs/architecture/overview.md` ennen toteutusta.
- Lue `docs/adr/0001-tech-stack.md`,
  `docs/architecture/domains/ORG_STATES.md`, `docs/architecture/concepts/SCENARIO.md` ja
  `docs/operations/testing.md` ennen toteutusta.
- Toteuta vain taman taskin scope.
- Ala lisaa uusia riippuvuuksia ilman hyvaksyntaa.
- Ala muuta tietokantaskeemaa tai lisaa migraatioita tassa taskissa.
- Ala toteuta frontend-muutoksia tassa taskissa.
- Lisaa tai paivita backend-testit protected-scenario patch-, delete- ja
  cleanup-semanticsille.
- Kerro lopuksi mita muutit ja miten tarkistit tyon.
