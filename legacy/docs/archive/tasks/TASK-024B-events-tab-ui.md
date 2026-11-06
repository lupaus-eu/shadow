# TASK-024B Events Tab UI

## Source Plan

Approved plan: implement the frontend Events tab and API client using the
backend Event CRUD API from `TASK-024A`.

This task covers only the frontend API client, Events tab UI, workspace wiring
and frontend tests. It assumes the backend endpoints from `TASK-024A` exist.

## Goal

Replace the placeholder Events workspace tab with a usable event management
view for the selected scenario.

The UI should mirror existing Scenarios tab patterns: list, selected detail,
create, edit, soft-delete flow, empty states, error states and refresh after
mutations.

## Requirements

- Depends on `TASK-024A Events Backend CRUD`.
- Add `frontend/src/api/events.ts` with:
  - `fetchEvents`
  - `fetchEvent`
  - `createEvent`
  - `updateEvent`
  - `deleteEvent`
- Use frontend event DTO shape:
  `{ id, name, targetDate, eventDetails }`.
- Reuse existing frontend API request/error patterns; if helper sharing is
  needed, extract only the minimal common API helper.
- Add `frontend/src/features/events/EventsTab.tsx`.
- Use `WorkspaceSelectionContext` to read the selected scenario.
- Keep event selection local to `EventsTab`; do not add global event selection
  unless implementation proves it necessary.
- Preserve the current workspace gating: Events is enabled only after both
  scenario and org state are selected.
- Wire `EventsTab` in `frontend/src/pages/Workspace.tsx`.
- Keep or minimally adjust `frontend/src/workspace/workspaceTabs.ts` metadata
  for the Events tab.
- Support:
  - event list loading for selected scenario
  - first-event auto-selection when available
  - create event
  - edit selected event
  - delete confirmation and delete
  - empty state
  - loading and error states
- After create, update or delete, refresh the selected scenario's event list
  and keep/select a sensible event: updated event, created event, first
  remaining event, or none.
- Do not add dependencies.
- Do not implement backend behavior in this task.

## Acceptance Criteria

- [ ] Events tab renders real UI instead of placeholder content.
- [ ] Events are fetched from the selected scenario endpoint.
- [ ] Empty event list shows a user-visible empty state.
- [ ] User can create an event with name, target date and event details.
- [ ] User can edit the selected event.
- [ ] User can delete an event only after confirmation.
- [ ] Successful mutations refresh the event list and detail selection.
- [ ] Failed loads or mutations show user-friendly errors.
- [ ] Workspace tab routing to `/shadow/{orgId}/events` still works.
- [ ] Existing Scenarios tab selection still activates the Events tab only
      after both scenario and org state are selected.
- [ ] No new dependency is added.

## Out Of Scope

- Backend API implementation.
- Authentication or authorization changes.
- Event timeline visualisation beyond CRUD list/detail UI.
- Pagination.
- Global event selection context.
- Broad Scenarios tab redesign.
- Documentation updates unless implementation changes user-facing workflow
  documentation.

## Implementation Notes

- Depends on `TASK-024A Events Backend CRUD`.
- Read these before implementation:

```text
AGENTS.md
docs/architecture/overview.md
docs/adr/0001-tech-stack.md
docs/architecture/domains/ORG_STATES.md
docs/operations/testing.md
```

- Keep frontend behavior consistent with current repo patterns in:
  - `frontend/src/features/scenarios/ScenariosTab.tsx`
  - `frontend/src/api/scenarios.ts`
  - `frontend/src/pages/Workspace.tsx`
  - `frontend/src/workspace/WorkspaceSelectionContext.tsx`
  - `frontend/src/App.test.tsx`
- Use these backend endpoints:
  - `GET /api/v1/organisations/{organisation_key}/scenarios/{scenario_key}/events`
  - `POST /api/v1/organisations/{organisation_key}/scenarios/{scenario_key}/events`
  - `GET /api/v1/organisations/{organisation_key}/scenarios/{scenario_key}/events/{event_id}`
  - `PATCH /api/v1/organisations/{organisation_key}/scenarios/{scenario_key}/events/{event_id}`
  - `DELETE /api/v1/organisations/{organisation_key}/scenarios/{scenario_key}/events/{event_id}`
- The public backend event response shape from `TASK-024A` is:
  `{ id, name, targetDate, eventDetails }`.
- Match existing visual density and form patterns from the Scenarios tab rather
  than creating a new design system.
- Use local component state for create/edit/delete forms and confirmation
  state.
- Use the existing selected scenario from workspace context as the parent for
  event loading and mutations.
- Do not add event data to `WorkspaceSelectionContext` in this task.
- If the backend response shape differs from the planned shape, update this
  task before implementing frontend normalisation that hides the mismatch.

## Testing

Required:

- [ ] Frontend tests
- [ ] Manual verification
- [ ] Lint
- [ ] Build

Not applicable:

- [ ] Backend tests: backend code is not changed in this task.
- [ ] Integration tests: frontend unit/interaction coverage is the expected
      automated level unless a lightweight existing integration path already
      supports this without new tooling.
- [ ] Typecheck: no dedicated frontend typecheck command is currently defined
      in the repository workflow.

Commands:

```bash
cd frontend
pnpm lint
pnpm test
pnpm build
```

Frontend tests should cover:

- Events route rendering at `/shadow/{orgId}/events`
- Events tab remaining gated until both scenario and org state are selected
- event list loading for the selected scenario
- empty event list state
- first-event auto-selection
- create event request and refreshed list selection
- edit event request and refreshed selected detail
- delete confirmation before request submission
- delete event request and post-delete selection behavior
- user-friendly load and mutation error messages

Manual verification should cover:

- select a scenario and org state in Scenarios
- open Events
- create an event with name, target date and event details
- edit the event fields
- delete the event through the confirmation flow
- verify backend data changes through the local dev stack, including
  `deleted_time` after delete when checking the database directly

## Documentation

No documentation updates are expected in this frontend task.

If implementation changes visible workflow steps that would make existing docs
wrong or incomplete, update only the minimum relevant documentation and explain
the reason in the final implementation summary.

## Notes For AI Agent

- Read `AGENTS.md` and `docs/architecture/overview.md` before implementation.
- Read `docs/adr/0001-tech-stack.md`,
  `docs/architecture/domains/ORG_STATES.md` and `docs/operations/testing.md` before implementation.
- Implement only this task's scope.
- Do not add new dependencies without approval.
- Do not implement backend behavior in this task.
- Reuse existing Scenarios tab API, state and UI patterns where practical.
- Add or update frontend tests for the Events tab behavior.
- Report what changed and which checks were run.
