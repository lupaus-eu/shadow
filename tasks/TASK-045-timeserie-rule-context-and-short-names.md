# TASK-045 Timeserie Rule Context And Short Names

## Source Plan

Approved plan: improve the Structure Timeserie editor rule presentation, expose
the selected Metric node as the source for existing explicit links, and add
equation-safe unique timeserie short names for a future equation editor.

## Goal

Make the Timeserie editor explain a selected Metric's rule using the names and
actual node-type labels from its graph context instead of showing the opaque
metamodel rule string. The rule presentation follows the `Has` relationship
path from an organisation-like node through a Goal node to the selected Metric.

Add a persisted optional `shortName` to scenario-owned timeseries. A supplied
short name is an equation-safe identifier and is unique within its active
scenario, so a future equation editor can refer to it unambiguously.

Also prevent confusing duplicate Timeserie display names: active timeseries in
one scenario must have distinct names after trimming and case-insensitive
comparison.

## Requirements

- In Structure Timeserie mode, replace the raw `timeserieIdRule` value in the
  `Rule` detail with graph-derived context for the selected Metric:

  ```text
  Measured by from <goal node name> (<goal node type display label>)
  Has goal from <organisation-like node name> (<organisation-like node type display label>)
  ```

  Render the two statements as separate lines in the `dd` element.
- Resolve the context by following visible directed `Has` graph edges:
  `organisation-like node -> Goal node -> selected Metric node`. Use the active
  type-catalog `displayName` value; do not hardcode `Organisation`, `Team`, or
  any other node-type label.
- Define and render a clear fallback when either relationship is absent or
  more than one matching path exists; never display a misleading single name.
- When a primary or secondary explicit node link resolves to an existing
  timeserie, show its status-card `Source` as
  `<selected node name> (<selected node type display label>)`, replacing the
  generic `Node link` text. Preserve `Type default` for inherited links.
- Add nullable `short_name` storage to `timeseries` through paired migration
  `012_add_timeserie_short_name.sql` and
  `012_add_timeserie_short_name.down.sql`.
- Expose the additive camelCase `shortName` field in Timeserie create, get and
  list API contracts, their Pydantic schemas, the SQLAlchemy model, service
  mapping and frontend types.
- Add `Short name` to the missing-timeserie creation form in Structure
  Timeserie mode. It is optional; blank input is persisted and returned as
  `null`/an empty frontend value according to the established API convention.
- Validate supplied short names as equation-safe ASCII identifiers:
  `^[A-Za-z][A-Za-z0-9_]*$`.
- Enforce active-scenario uniqueness for supplied short names in both backend
  validation and the database (partial unique index that excludes `NULL` and
  soft-deleted timeseries). Return the existing conflict response style for a
  duplicate.
- Enforce active-scenario display-name uniqueness after trimming and
  case-insensitive comparison in both the backend and database. Add a backend
  create preflight check that returns HTTP `409` with a clear duplicate-name
  error, and a partial unique expression index on `(scenario_id, lower(name))`
  that excludes soft-deleted timeseries.
- Preserve `shortName` when Organisation States copies scenario-owned
  timeseries.
- Do not add a timeserie metadata update endpoint or equation editor in this
  task.

## Acceptance Criteria

- [ ] A Metric with the visible path `Team -> Goal -> Metric` shows, for
  example, `Measured by from Grow revenue (Goal)` and
  `Has goal from Sales (Team)` on separate Rule lines.
- [ ] Rule context uses each connected node's type-catalog display label rather
  than a hardcoded organisation label.
- [ ] Missing and ambiguous relationship paths produce an explicit, safe Rule
  fallback rather than an arbitrary node name.
- [ ] An existing explicit primary or secondary link shows the selected
  node's name and actual type label as its Source; inherited links still show
  `Type default`.
- [ ] A user can submit an optional Short name while creating a missing
  timeserie from Structure Timeserie mode.
- [ ] Timeserie create, get and list responses include `shortName`; a valid
  provided value survives persistence and scenario copy.
- [ ] Invalid identifiers, duplicate active-scenario short names, and blank
  optional input follow the documented validation and API behaviour.
- [ ] Timeserie creation rejects `Revenue`, `revenue`, and whitespace-padded
  variants as duplicate active display names in the same scenario with HTTP
  `409`.
- [ ] The same display name is allowed in a different scenario and after the
  original Timeserie has been soft-deleted.
- [ ] Migration up adds the column and active-row uniqueness index; migration
  down cleanly removes them in a disposable PostgreSQL database.
- [ ] Migration up also adds the active-row, case-insensitive display-name
  unique index; migration down cleanly removes it.
- [ ] Relevant frontend and backend tests, lint, build and type checks pass.

## Out Of Scope

- Equation parsing, storage, validation or an equation-editor UI.
- Editing an existing timeserie's metadata, including its short name.
- Changes to graph relationship persistence, metamodel editing, or new edge
  types.
- Authentication, authorization, or dependency changes.

## Implementation Notes

Relevant sources:

```text
frontend/src/features/structure/TimeseriePanel.tsx
frontend/src/features/structure/StructureTab.tsx
frontend/src/features/structure/StructureTab.test.tsx
frontend/src/api/timeseries.ts
backend/app/api/v1/org_states/models.py
backend/app/api/v1/org_states/schemas.py
backend/app/api/v1/org_states/org_states_service.py
backend/tests/test_users_organisations_api.py
db/migrations/README.md
docs/domains/ORG_STATES.md
docs/domains/ORG_TWIN_STRUCTURE.md
docs/data/DATA-MODEL.md
docs/data/DATABASE.md
```

- Keep graph traversal in the Structure UI. The loaded graph already provides
  visible nodes and directed edges, and the type catalog supplies display
  labels. Pass the smallest required graph context into `TimeseriePanel`.
- The default metamodel represents the organisation-like level as `Team`; the
  rendered output must therefore be `(<actual displayName>)`, not a fixed
  `(Organisation)` suffix.
- Treat an explicit node link as the user-entered primary or secondary key.
  Do not change the existing effective-id, existence-check, create, delete or
  inherited-default behaviour beyond the requested Source label.
- Use the repository migration runner and add the up/down pair together. Do
  not modify the baseline migration after it has been applied.
- The short-name uniqueness rule must cover only active rows so a soft-deleted
  timeserie does not block reuse. Keep public stable `id` semantics unchanged.
- Apply the same active-row lifecycle scope to display-name uniqueness. Compare
  names after trimming and case-insensitively; links still resolve only by the
  stable Timeserie `id`, never by display name.

## Testing

Required:

- [ ] Frontend tests for graph-derived Rule text, missing/ambiguous fallbacks,
  explicit-link Source text, and Short name submission.
- [ ] Backend API/service tests for short-name response serialization,
  identifier validation, duplicate conflict behaviour and scenario-copy
  preservation, plus case-insensitive display-name conflicts, cross-scenario
  reuse and reuse after soft deletion.
- [ ] Database migration integration test or documented disposable PostgreSQL
  verification of both migration directions, the short-name partial unique
  index and the case-insensitive display-name partial unique index.
- [ ] Manual verification in Structure Timeserie mode for both explicit and
  inherited links.
- [ ] Lint.
- [ ] Build.
- [ ] Typecheck.

Commands:

```bash
cd frontend
pnpm lint
pnpm test
pnpm build

cd backend
uv run ruff check .
uv run pytest
uv run pyright
```

Run migration integration checks only with the disposable database configuration
documented in `docs/TESTING.md`.

## Documentation

Update:

- `docs/domains/ORG_STATES.md` for the additive Timeserie API field and
  equation-safe unique short-name and case-insensitive display-name uniqueness
  rules.
- `docs/domains/ORG_TWIN_STRUCTURE.md` if the Rule-context presentation needs
  documented Structure UI semantics.
- `docs/data/DATA-MODEL.md` and `docs/data/DATABASE.md` for `short_name` and
  its active-scenario uniqueness invariant, and the active-scenario
  case-insensitive display-name uniqueness invariant.
- `docs/diagrams/db-physical-schema.puml` and its generated SVG.
- `docs/diagrams/data-logical-model.puml` and its generated SVG only if the
  logical Timeserie field detail is added there.

## Notes For AI Agent

- Read `AGENTS.md`, `ARCHITECTURE.md`, this task, `docs/TESTING.md`, the two
  listed domain documents, `docs/data/` and `db/migrations/README.md` before
  implementation.
- Implement only this task's scope. Do not add an equation editor, a new
  dependency or a metadata edit endpoint.
- Use paired version-controlled migrations; never change a production database
  manually.
- Add or update tests for all application behaviour changed by this task.
- Update PlantUML sources and generated SVGs for any affected data diagram.
- Report the changed files and exact verification results when finished.
