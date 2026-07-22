# TASK-027 Fix Scenario Fork State Copy

## Source Plan

Approved plan: fix scenario forking so the new scenario copies only the selected
source organisation state from the scenario being forked from.

## Goal

When a scenario is forked, create exactly one organisation state in the new
scenario: the selected `sourceOrgStateId`. Do not copy earlier source states
just because their `target_date` is before the selected state.

## Requirements

- Keep the existing scenario copy API request shape:
  - `sourceScenarioId`
  - `sourceOrgStateId`
  - `name`
  - `description`
- Treat copy `name` as optional.
- When copy `name` is missing or blank, the backend must generate
  `Fork of {source scenario name}`.
- Validate the source scenario is active and belongs to the requested
  organisation.
- Validate the source organisation state is active and belongs to the selected
  source scenario.
- Create the copied scenario as unprotected.
- Set copied scenario `source_scenario_id` to the selected source scenario.
- Copy only the selected source organisation state into the copied scenario.
- Set copied scenario `initial_state_id` to the copied selected organisation
  state.
- Preserve copied org-state `name`, `description`, `target_date`, and
  `version`.
- Generate a new `org_state_key` for the copied organisation state.
- Continue copying graph snapshot data through the Organisation Twin Structure
  service boundary for the copied org-state pair.
- Allow the frontend fork form to submit with a blank name so the backend can
  apply the generated default.
- Do not mutate source scenario, source org states, or source graph data.
- Update documentation that currently describes selected state target date as a
  multi-state copy boundary.

## Acceptance Criteria

- [ ] Scenario copy creates exactly one active org state in the copied scenario.
- [ ] The copied org state is copied from `sourceOrgStateId`.
- [ ] Earlier source org states are not copied.
- [ ] Later source org states are not copied.
- [ ] Soft-deleted source org states are not copied.
- [ ] Copied scenario `initial_state_id` points to the copied selected source
      state.
- [ ] Missing or blank copy `name` defaults to
      `Fork of {source scenario name}`.
- [ ] The frontend fork form can submit without a name.
- [ ] Copying from protected `reality` still works and creates an unprotected
      scenario.
- [ ] Missing source scenario or source org state behavior remains unchanged.
- [ ] Source org state from another scenario is still rejected.
- [ ] Relevant backend tests pass.
- [ ] Relevant documentation is updated.
- [ ] No new dependency is added.

## Out Of Scope

- No new scenario copy request or response fields.
- No metamodel copy behavior.
- No timeseries or timeserie value copy behavior.
- No database schema or migration changes.
- No changes to graph copy semantics beyond receiving one copied org-state
  pair.

## Implementation Notes

- Update `backend/app/api/v1/org_states/org_states_service.py`.
- Replace the current bounded source org-state query with direct copying of the
  validated selected source org state.
- Pass a one-entry source-to-copy org-state ID map into
  `copy_graph_snapshots_for_org_states`.
- Keep the Organisation Twin Structure copy service unchanged unless tests
  reveal it cannot support a single copied org-state pair.

## Testing

Required:

- [ ] Backend scenario/org-state tests
- [ ] Frontend Scenarios tab tests
- [ ] Ruff
- [ ] Pyright
- [ ] Frontend lint
- [ ] Frontend build

Commands:

```bash
cd backend
uv run ruff check .
uv run pytest tests/test_users_organisations_api.py
uv run pyright

cd frontend
pnpm lint
pnpm test
pnpm build
```

## Documentation

Update documentation that describes scenario copy behavior:

- `docs/domains/ORG_STATES.md`
- `docs/concepts/SCENARIO.md`
- `docs/concepts/ORGANISATION_STATE.md`

Documentation should say scenario copy copies only the selected source
organisation state, not all active states within the selected state's
target-date boundary.

## Notes For AI Agent

- Lue `AGENTS.md`, `ARCHITECTURE.md`, relevantit ADR:t,
  `docs/domains/ORG_STATES.md`, `docs/domains/ORG_TWIN_STRUCTURE.md`,
  `docs/concepts/SCENARIO.md`, `docs/concepts/ORGANISATION_STATE.md`, ja
  `docs/TESTING.md` ennen toteutusta.
- Toteuta vain tämän taskin scope.
- Älä lisää uusia riippuvuuksia ilman hyväksyntää.
- Lisää tai päivitä testit, koska muutos koskee backend-sovelluskoodia.
- Päivitä dokumentaatio, koska domain- ja concept-semantiiikka muuttuu.
- Kerro lopuksi mitä muutettiin ja miten työ tarkistettiin.
