# TASK-031 Replace Deprecated FormEvent

## Source Plan

Approved plan: replace React's deprecated `FormEvent` type with the event type
used by React 19.2 for form submission handlers.

This task is limited to a type migration. It must not change form behavior,
validation, asynchronous operations or user-visible UI.

## Goal

Remove the TypeScript `ts(6385)` deprecation warnings caused by
`FormEvent<HTMLFormElement>` while retaining precise types for every form
submission handler.

Use React's `SubmitEvent<HTMLFormElement>` type because all current
`FormEvent` usages are attached to form `onSubmit` callbacks.

## Requirements

- Replace type-only imports of `FormEvent` from React with `SubmitEvent`.
- Replace every `FormEvent<HTMLFormElement>` annotation on submit handlers
  with `SubmitEvent<HTMLFormElement>`.
- Update component callback prop types that expose those submit handlers.
- Preserve all existing handler implementations, including `preventDefault()`,
  validation, async operations and error handling.
- Do not add or update dependencies.
- Do not introduce unrelated refactoring or user-visible changes.

## Acceptance Criteria

- [ ] No `FormEvent` or `FormEventHandler` references remain under
      `frontend/src/`.
- [ ] All affected form submission handlers use
      `SubmitEvent<HTMLFormElement>`.
- [ ] Component callback prop types remain compatible with React form
      `onSubmit` props.
- [ ] Existing form behavior and UI remain unchanged.
- [ ] No dependency changes are introduced.
- [ ] Frontend lint, tests and build pass.
- [ ] The `FormEvent is deprecated.ts(6385)` editor warning no longer appears.

## Out Of Scope

- Changes to form behavior, validation, requests or state management.
- Changes to non-submit event types such as change or input events.
- New tests for runtime behavior when existing tests already cover the forms.
- Dependency upgrades or changes to TypeScript or React configuration.
- Backend, database, API, architecture or deployment changes.

## Implementation Notes

Expected files to update:

```text
frontend/src/features/events/EventsTab.tsx
frontend/src/features/scenarios/ScenariosTab.tsx
frontend/src/features/structure/EdgeForm.tsx
frontend/src/features/structure/NodeForm.tsx
frontend/src/features/structure/TimeseriePanel.tsx
```

React 19.2's type declarations deprecate `FormEvent` because it does not
represent an actual event category. React's JSX type for a form's `onSubmit`
prop uses `SubmitEventHandler`, whose event parameter is `SubmitEvent`.

Keep the `HTMLFormElement` generic so `currentTarget` remains typed as the form
element. Apply the replacement both to concrete handler functions and to any
component props that receive those functions.

No ADR is required because this task does not change the architecture or
technology choices.

## Testing

Required:

- [ ] Frontend tests
- [ ] Manual verification
- [ ] Lint
- [ ] Build

Not applicable:

- [ ] Backend tests: backend code is not changed.
- [ ] Integration tests: this is a frontend-only type annotation change with
      no runtime behavior change.
- [ ] New frontend tests: no behavior or logic changes; run the existing suite
      as regression coverage.
- [ ] Dedicated typecheck command: the frontend has no separate typecheck
      script; `pnpm build` runs `tsc -b`.

Commands:

```bash
cd frontend
pnpm lint
pnpm test
pnpm build
rg -n "FormEvent|FormEventHandler" src
```

The final `rg` command is expected to return no matches. Manually confirm that
the TypeScript language service no longer reports `ts(6385)` for the affected
handlers.

## Documentation

No documentation updates are expected because the change does not affect
architecture, behavior, public APIs or development workflows.

If implementation reveals a behavior or public contract change, stop and
update the task scope before making that change.

## Notes For AI Agent

- Read `AGENTS.md`, `ARCHITECTURE.md`, `docs/TESTING.md` and this task before
  implementation.
- Implement only this task's scope.
- Use `SubmitEvent<HTMLFormElement>` for form submission callbacks; do not
  replace the deprecated type with a broader event type without justification.
- Do not add or update dependencies.
- Do not change handler logic or UI behavior.
- Do not add tests solely for a type-only migration; explain that existing
  frontend tests provide regression coverage.
- Report what changed and which checks were run.
