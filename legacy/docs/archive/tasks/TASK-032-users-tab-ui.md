# TASK-032 Users Tab UI

Status: Implemented

## Source Plan

Approved plan: add a Users workspace tab for managing application-wide Shadow
users through the existing Users Domain backend CRUD API.

The tab is available from an organisation workspace for compatibility with the
current navigation shell, but user records are not organisation-owned. The
workspace `orgId` is therefore used only for navigation and must not be sent to
the Users API.

## Goal

Implement a frontend Users tab that lists active application users and lets an
operator create, edit and soft-delete users.

The UI must preserve the Users Domain rules in `docs/architecture/domains/USERS.md`: a user
has a non-blank display name, a role of `consultant` or `admin`, and normal
reads exclude soft-deleted records.

## Requirements

- Add an enabled `Users` workspace tab with the signature `users` at
  `/shadow/:orgId/users`.
- Place Users last in the existing workspace tab bar.
- Keep the Users tab available without a selected scenario or organisation
  state.
- Treat users as application-wide records even though the tab is reached from
  an organisation workspace.
- Add a typed frontend Users API client for:
  - `GET /api/v1/users`
  - `POST /api/v1/users`
  - `PATCH /api/v1/users/{userId}`
  - `DELETE /api/v1/users/{userId}`
- Model the API contract as:
  - `UserRole = "consultant" | "admin"`
  - `UserDto = { id: number; name: string; role: UserRole }`
- Follow the existing API client conventions for `VITE_API_BASE_URL`, JSON
  requests, `AbortSignal`, FastAPI error payloads and actionable error messages.
- Add a dedicated `UsersTab` feature component.
- Show a toolbar with the page title, active-user count and Refresh action.
- Show users in a selectable list with their name and role.
- Sort users case-insensitively by name and use user id as a deterministic
  tie-breaker.
- Automatically select the first user after loading when no preserved
  selection is available.
- Preserve the selected user after refresh or update when that active user
  still exists.
- Fall back to the first remaining user after the selected user is deleted or
  otherwise disappears.
- Provide a create-user form with name and role fields.
- Provide a selected-user form for editing name and role.
- Restrict role controls to `Consultant` and `Admin` values backed by the API
  values `consultant` and `admin`.
- Trim user names before submission and reject blank names in the UI.
- Require explicit confirmation before deleting a user.
- Treat DELETE as soft deletion; do not display deleted users or add restore
  behavior.
- Show explicit loading, empty, list-error, mutation-error and saving states.
- Provide a retry path after a list-load failure.
- Prevent duplicate mutations by disabling relevant controls while a request
  is in progress.
- Cancel or ignore stale list requests during unmount, route changes and
  overlapping refreshes.
- Reuse existing design tokens and management-view patterns; do not add a new
  dependency.
- Use semantic headings, labelled form fields, keyboard-accessible controls,
  accessible selected state, `role="alert"` for errors, and accessible delete
  confirmation controls.
- Keep the layout usable at the responsive widths supported by the existing
  workspace shell.

## Acceptance Criteria

- [x] `Users` appears last in the workspace tab bar and links to
      `/shadow/:orgId/users`.
- [x] The active Users tab is derived from the URL.
- [x] Users remains enabled when no scenario or organisation state is selected.
- [x] Opening the tab loads active users from `GET /api/v1/users` without
      including `orgId` in the API path.
- [x] Users are sorted case-insensitively by name with a deterministic id
      tie-breaker.
- [x] The UI renders loading, empty, error and retry states for the user list.
- [x] A user can be created with a trimmed, non-blank name and either supported
      role.
- [x] Blank user names are rejected before an API mutation is sent.
- [x] A selected user's name and role can be updated.
- [x] User deletion requires explicit confirmation.
- [x] A successfully deleted user disappears from the active list and is not
      offered for restoration.
- [x] Selection is preserved after refresh and update when possible, with a
      predictable fallback when the selected user no longer exists.
- [x] Mutation progress and failures are visible, and duplicate submissions are
      prevented while saving.
- [x] Stale or aborted loads do not overwrite current tab state.
- [x] User-management controls are accessible by keyboard and have meaningful
      labels, states and error announcements.
- [x] No Entra ID, organisation membership, authentication or authorization
      behavior is introduced.
- [x] Frontend tests, lint and build pass.
- [x] The existing backend Users CRUD contract test passes.

## Out Of Scope

- Microsoft Entra ID integration or subject-to-user mapping.
- Authentication and authorization.
- Restricting the tab or its actions by the current user's role.
- Organisation membership or organisation-specific users.
- Passing the workspace `orgId` to Users Domain endpoints.
- Email addresses, invitations, passwords or account registration.
- User-name uniqueness rules.
- Preventing self-deletion or requiring at least one active admin.
- Displaying, restoring or permanently deleting soft-deleted users.
- Backend CRUD implementation unless contract verification exposes a separate
  defect that is approved as additional scope.
- Database schema changes, migrations or seed changes.
- New frontend dependencies.
- A separate global administration shell or top-level `/users` route.

## Implementation Notes

- Read `AGENTS.md`, `docs/architecture/overview.md`,
  `docs/adr/0001-tech-stack.md`, `docs/architecture/domains/USERS.md`,
  `docs/operations/testing.md` and this task before implementation.
- The existing backend contract lives under `backend/app/api/v1/users/` and is
  covered by `backend/tests/test_users_organisations_api.py`.
- Expected frontend areas include:
  - `frontend/src/workspace/workspaceTabs.ts`
  - `frontend/src/pages/Workspace.tsx`
  - `frontend/src/api/users.ts`
  - `frontend/src/features/users/UsersTab.tsx`
  - relevant frontend tests and styles
- Use the backend as the trusted validation and lifecycle boundary. Frontend
  validation exists for user experience and must not replace backend checks.
- Use the existing workspace management patterns where they fit, while keeping
  Users Domain state independent of scenario and organisation-state selection.
- Prefer request-state handling that cannot allow an older response to replace
  a newer load result.
- No ADR is required because this task uses the existing frontend, backend and
  navigation architecture.

## Testing

Required:

- [x] Frontend API client tests
- [x] Frontend component/integration tests
- [ ] Manual verification after AI-review fixes
- [x] Backend contract verification
- [x] Frontend lint
- [x] Frontend build and TypeScript checking

Not applicable:

- [x] Database or migration tests: no schema or persistence changes are in
      scope.
- [x] New backend tests: no backend implementation change is planned; add them
      only if an approved backend correction is required.
- [x] End-to-end browser automation: component/integration coverage and manual
      verification are proportionate for this UI task.

Frontend automated coverage must include:

- Users route, tab link and active state.
- Availability without scenario or organisation-state selection.
- Successful loading, sorting and initial selection.
- Loading, empty, error and retry behavior.
- Creating a user with a trimmed name and supported role.
- Rejecting a blank name without making a mutation request.
- Editing a selected user's name and role.
- Cancelling and confirming deletion.
- Removing a deleted user from the active list.
- Selection preservation and fallback behavior.
- Mutation progress and API failure behavior.
- Correct HTTP methods, paths and request payloads.
- Aborted or stale request handling.

Commands:

```bash
cd frontend
pnpm lint
pnpm test
pnpm build

cd backend
uv run pytest tests/test_users_organisations_api.py -v
```

Manual verification must cover:

- Opening Users directly by URL and through the workspace tab bar.
- Using the tab without selecting a scenario or organisation state.
- Loading and refreshing users.
- Creating consultant and admin users.
- Editing a user's name and role.
- Cancelling and confirming deletion.
- Empty and API-error presentation.
- Keyboard navigation and responsive layout behavior.

Manual verification of the original implementation was performed by the
developer in a browser with no issues found. After the AI review changed
mutation reconciliation and refresh lockout behavior, targeted browser
re-verification of those flows is pending.

Last automated verification by AI agent:

- `pnpm lint`
- `pnpm test` (9 files, 106 tests passed)
- `pnpm build`
- `uv run pytest tests/test_users_organisations_api.py -v` (38 tests passed)

## Documentation

- Update `docs/architecture/overview.md` after implementation to record the Users frontend
  feature and its application-wide API boundary.
- Update `docs/operations/testing.md` only if a permanent Users-specific verification
  section adds value beyond this task.
- Do not change `docs/architecture/domains/USERS.md`, logical/physical data documentation,
  migrations or diagrams unless implementation reveals a separately approved
  domain, schema or architecture change.

## Notes For AI Agent

- Toteuta vain tassa taskissa maaritelty scope.
- Ala lisaa uusia riippuvuuksia ilman hyvaksyntaa.
- Ala lisaa Entra ID-, authentication-, authorization- tai organisation
  membership -toiminnallisuutta.
- Ala muuta backendia vain siksi, etta frontend tarvitsee Users APIa; nykyinen
  CRUD-sopimus on taman taskin lahtokohta.
- Lisaa testit muutoksen riskin mukaan.
- Kerro lopuksi mita muutit ja miten tarkistit tyon.
