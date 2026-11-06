# TASK-015 Organisation Defaults And Frontend Flow

## Source Plan

Approved plan: make organisation creation transactional and usable from the current frontend by creating default scenario, org state and organisation-specific metamodel data.

This task connects the frontend organisation flow to persisted backend behavior.

## Goal

When a new organisation is created through the backend, create all default data required for the workspace to open immediately.

The frontend organisation fetch/create flow should use the backend API and show backend errors clearly.

## Requirements

- Keep `POST /api/v1/organisations` transactional.
- On organisation creation, create a default scenario with:
  - `DEFAULT_SCENARIO_NAME = "Reality"`
  - `DEFAULT_SCENARIO_DESCRIPTION = "The reality of the organisation"`
  - `DEFAULT_SCENARIO_PROTECTED = True`
- On organisation creation, create a default org state with:
  - `DEFAULT_ORG_STATE_NAME = "Initial state"`
  - `DEFAULT_ORG_STATE_DESCRIPTION = "Initial state of reality"`
  - `DEFAULT_ORG_STATE_TARGET_DATE = dt_date(2020, 1, 1)`
- Place default org state/scenario creation functions in `org_states/org_states_service.py`.
- Set the default scenario `initial_state_id` to the created org state.
- Copy, not reference, the active default metamodel for the organisation.
- Place default metamodel copy functions in `org_twin_structure/org_twin_structure_service.py`.
- Copy metamodel rows from the database, seeded default if not replaced by an updated active default metamodel.
- Copy the metamodel row, node types, edge types, type attributes and allowed connections.
- Validate metamodel values using these allowed sets:
  - `ALLOWED_ATTR_DATA_TYPES = {"string", "int", "float", "bool", "date", "datetime", "enum", "list"}`
  - `ALLOWED_NODE_SHAPES = {"rectangle", "round-rectangle", "ellipse", "diamond", "hexagon"}`
  - `ALLOWED_EDGE_ENDINGS = {"none", "arrow", "circle", "diamond"}`
- Add minimal read endpoints needed by the current workspace:
  - `GET /api/v1/organisations/{org_id}/scenarios`
  - `GET /api/v1/organisations/{org_id}/scenarios/{scenario_id}/org-states`
- Ensure the frontend organisation list and create flow uses the backend.

## Acceptance Criteria

- [ ] `POST /api/v1/organisations` runs in one transaction.
- [ ] It creates default scenario:
  - name: `Reality`
  - description: `The reality of the organisation`
  - protected: `True`
- [ ] It creates default org state through `org_states/org_states_service.py`:
  - name: `Initial state`
  - description: `Initial state of reality`
  - target date: `2020-01-01`
- [ ] It sets the scenario `initial_state_id` to the created org state.
- [ ] It copies, not references, the active default metamodel through `org_twin_structure/org_twin_structure_service.py`.
- [ ] Copied metamodel includes metamodel row, node types, edge types, type attributes, and allowed connections.
- [ ] Metamodel validation enforces:
  - attribute data types: `string`, `int`, `float`, `bool`, `date`, `datetime`, `enum`, `list`
  - node shapes: `rectangle`, `round-rectangle`, `ellipse`, `diamond`, `hexagon`
  - edge endings: `none`, `arrow`, `circle`, `diamond`
- [ ] Add minimal `GET /api/v1/organisations/{org_id}/scenarios` and `GET /api/v1/organisations/{org_id}/scenarios/{scenario_id}/org-states` so the workspace can show the created default data.
- [ ] Frontend organisation fetch/create remains wired to `/api/v1/organisations`; tests cover loading, creation, and duplicate-name error display.

## Out Of Scope

- Backend runtime scaffold.
- General users CRUD.
- General scenario CRUD beyond the listed minimal read endpoints.
- General org state CRUD beyond the listed minimal read endpoint.
- Authentication or authorization.
- Graph, event or timeseries behavior.
- Editing the metamodel in the UI.

## Implementation Notes

- Depends on `TASK-012 Backend Runtime Scaffold`.
- Depends on `TASK-013 Core Schema And Domain Documentation Updates`.
- Depends on `TASK-014 Users And Organisations Backend CRUD`.
- Use the current active default metamodel from database tables where `metamodels.organisation_id IS NULL AND deleted_time IS NULL`.
- Do not copy from the JSON seed file at runtime.
- Preserve stable keys while copying metamodel child rows into the new organisation-specific metamodel.
- Keep default creation idempotent within a failed transaction by rolling back the whole create operation on error.

## Testing

Required:

- [ ] Backend tests
- [ ] Frontend tests
- [ ] Integration tests
- [ ] Manual verification
- [ ] Lint
- [ ] Build
- [ ] Typecheck

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

Manual verification:

- Apply schema migrations.
- Run development seed.
- Start backend and frontend.
- Create an organisation from the frontend.
- Verify the new organisation appears in the list.
- Open the organisation workspace.
- Verify the Reality scenario and Initial state are available.
- Verify duplicate organisation name creation fails clearly.

## Documentation

Update API, local development or domain documentation if implementation adds documented behavior not already covered by earlier tasks.

## Notes For AI Agent

- Toteuta vain tämän taskin scope.
- Älä muuta tuotantotietokantaa.
- Älä lisää uusia riippuvuuksia ilman hyväksyntää.
- Lisää tai päivitä testit muutoksen riskin mukaan.
- Kerro lopuksi mitä muutit ja miten tarkistit työn.
