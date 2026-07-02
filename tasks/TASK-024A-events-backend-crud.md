# TASK-024A Events Backend CRUD

## Source Plan

Approved plan: implement backend CRUD API for scenario-owned events so Events
can work like existing Scenarios and Organisation States.

This task covers only backend schemas, routes, service logic, backend tests and
the Organisation States Domain documentation needed for event CRUD.

## Goal

Add FastAPI routes, schemas, service logic and backend tests for scenario event
CRUD under the Organisation States Domain.

The API must use stable text event keys in public responses and paths,
soft-delete events, and preserve the existing Organisation States Domain
service/router patterns.

## Requirements

- Add `EventCreateRequest`, `EventPatchRequest` and `EventResponse` in
  `backend/app/api/v1/org_states/schemas.py`.
- Use this public event response shape:
  `{ id, name, targetDate, eventDetails }`.
- Add service functions in
  `backend/app/api/v1/org_states/org_states_service.py`:
  - `list_scenario_events`
  - `get_event`
  - `create_event`
  - `patch_event`
  - `soft_delete_event`
- Add routes under:
  - `GET /api/v1/organisations/{organisation_key}/scenarios/{scenario_key}/events`
  - `POST /api/v1/organisations/{organisation_key}/scenarios/{scenario_key}/events`
  - `GET /api/v1/organisations/{organisation_key}/scenarios/{scenario_key}/events/{event_id}`
  - `PATCH /api/v1/organisations/{organisation_key}/scenarios/{scenario_key}/events/{event_id}`
  - `DELETE /api/v1/organisations/{organisation_key}/scenarios/{scenario_key}/events/{event_id}`
- Treat `{event_id}` as the stable `event_key`, not the numeric database
  primary key.
- Generate new event keys server-side, using the `event_{uuid}` style.
- Validate active organisation, active scenario and active event ownership.
- Require non-blank `name`.
- Require `targetDate` on create.
- Reject patch payloads that explicitly set `targetDate` to `null`.
- Do not enforce target-date uniqueness for events unless source
  documentation is changed first.
- Exclude soft-deleted events from list and get.
- PATCH only supplied `name`, `targetDate` and `eventDetails` fields and
  update `modified_time`.
- DELETE soft-deletes the event and returns HTTP `204`.
- Do not add database migrations or new dependencies.
- Update `docs/domains/ORG_STATES.md` with event API ownership and event CRUD
  workflows.

## Acceptance Criteria

- [ ] Event list, get, create, patch and delete endpoints exist.
- [ ] Event create returns HTTP `201`.
- [ ] Event delete returns HTTP `204`.
- [ ] Missing active organisation, scenario or event returns HTTP `404`.
- [ ] Event responses use stable `id`, `name`, `targetDate` and
      `eventDetails`.
- [ ] Soft-deleted events are excluded from reads.
- [ ] Scenario soft-delete propagation to events still works.
- [ ] Blank event names are rejected.
- [ ] Missing create `targetDate` and explicit patch `targetDate: null` are
      rejected.
- [ ] Backend tests cover CRUD, validation, 404s and soft-delete behavior.
- [ ] No database migration is added.
- [ ] No new dependency is added.
- [ ] Organisation States Domain documentation includes the event endpoints and
      workflows.

## Out Of Scope

- Frontend Events tab.
- Authentication or authorization changes.
- Event target-date uniqueness.
- Pagination.
- Timeseries, graph or scenario-copy behavior.
- Database schema changes.
- Changes to production data.

## Implementation Notes

- Read these before implementation:

```text
AGENTS.md
ARCHITECTURE.md
docs/decisions/ADR-001-tech-stack.md
docs/domains/ORG_STATES.md
docs/data/DATA-MODEL.md
docs/data/DATABASE.md
docs/TESTING.md
```

- The existing `events` table and SQLAlchemy `Event` model are already present.
  Do not add a migration for this task.
- Keep route handlers thin and put business logic in
  `org_states_service.py`.
- Follow the existing Scenario and Organisation State CRUD patterns for:
  - Pydantic schemas inheriting `StrictBaseModel`
  - server-side stable key generation
  - active parent/resource lookup
  - soft-delete filtering through `deleted_time IS NULL`
  - `modified_time` updates on patch and soft delete
  - HTTP `404`, `201` and `204` behavior
- Use `event_details` as the ORM field and `eventDetails` as the public API
  field.
- Protected scenarios do not block child event CRUD, matching current child
  organisation-state CRUD behavior.
- If implementation uncovers documentation that defines event target-date
  uniqueness, stop and update this task before implementing that invariant.
- No ADR is expected because this is scoped API/domain behavior on the existing
  architecture and schema.

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

- event create, list, get, patch and delete
- stable keys in response `id` fields
- missing active organisation, scenario and event returning `404`
- blank `name` validation
- required create `targetDate`
- explicit patch `targetDate: null` rejection
- patching `name`, `targetDate` and `eventDetails`
- duplicate event target dates being allowed inside a scenario
- soft-deleted events being excluded from list and get
- scenario soft-delete propagation to active owned events still passing

Manual verification should cover:

- create or select an organisation and scenario
- create an event for that scenario
- list and get the created event
- patch the event name, target date and details
- delete the event and verify subsequent list/get excludes it
- verify the database row has `deleted_time` set after delete

## Documentation

Update `docs/domains/ORG_STATES.md` to include:

- Event CRUD endpoints in the API ownership section.
- Event response shape.
- Create, patch and delete event workflows.
- Required event target-date behavior.
- Soft-delete semantics for normal event deletion.

No data model, database, architecture, diagram or ADR updates are expected
because the event table and logical entity already exist.

## Notes For AI Agent

- Read `AGENTS.md` and `ARCHITECTURE.md` before implementation.
- Read `docs/decisions/ADR-001-tech-stack.md`,
  `docs/domains/ORG_STATES.md`, `docs/data/DATA-MODEL.md`,
  `docs/data/DATABASE.md` and `docs/TESTING.md` before implementation.
- Implement only this task's scope.
- Do not add new dependencies without approval.
- Do not change the database schema or add migrations in this task.
- Do not implement frontend changes in this task.
- Add or update backend tests for event CRUD and validation behavior.
- Report what changed and which checks were run.
