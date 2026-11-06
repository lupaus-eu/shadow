# TASK-039F Frontend Authentication And Session UI

Status: Planned

## Source Plan

Approved TASK-039 plan: React consumes Shadow's application-session API and
never acts as an OIDC client or reads provider tokens. The visible flow and API
behavior are identical with local Authentik and Entra.

## Goal

Add session restoration, login/logout UX, protected routes and centralized
authenticated requests to the React application using the backend contract from
TASK-039C/D.

## Requirements

- Depends on TASK-039C and TASK-039D.
- Add a shared auth context/store that owns only session loading, current user,
  CSRF token, login navigation, logout and authentication errors.
- On application startup call `GET /api/v1/auth/session`; render a stable
  loading state until restoration completes.
- Add a login screen that navigates the browser—not `fetch`—to
  `/api/v1/auth/login` with a safe relative return path.
- Add protected-route behavior for the application workspace. Anonymous `401`
  results show the login screen and preserve the intended relative route.
- Display current user name and role in the existing shell and provide logout.
  Logout sends the CSRF header, consumes `{ "logoutUrl": <string-or-null> }`,
  then navigates to that trusted URL or the local login screen. Do not expect a
  `fetch` redirect to perform top-level browser navigation.
- Centralize the duplicated API fetch behavior sufficiently to ensure:
  - same-origin cookies are used
  - every unsafe request sends the current session CSRF token
  - a `401` invalidates frontend auth state consistently
  - a `403` remains a permission error and does not trigger a login loop
- Do not store tokens, session IDs or CSRF tokens in localStorage/sessionStorage.
  CSRF state is memory-only and restored from `/auth/session` after reload.
- Hide Users navigation and administration UI from consultants as a UX aid;
  backend admin enforcement remains authoritative.
- Add an admin-only "Revoke sessions" action to the existing Users
  administration UI. It calls
  `POST /api/v1/users/{user_id}/sessions/revoke` through the shared CSRF-aware
  helper, confirms the destructive sign-out effect, and reports success or the
  existing API error without implying provider logout.
- Preserve existing API error parsing and cancellation behavior while
  centralizing authenticated requests.
- Do not add MSAL, Authentik SDK, an OIDC library, a state-management package or
  an E2E framework.

## Acceptance Criteria

- [ ] Initial loading does not flash protected application content.
- [ ] Anonymous users can start login and return to their intended safe route.
- [ ] Authenticated user/session restoration works without a provider token in
      JavaScript-visible storage.
- [ ] Every unsafe API request carries the current CSRF header.
- [ ] Global `401` handling returns to login without loops; `403` is shown as a
      permission failure.
- [ ] Logout clears frontend state and the next protected navigation requires
      login.
- [ ] Consultants cannot see or navigate to Users administration through the
      normal UI; admins retain it.
- [ ] Admins can revoke a selected user's application sessions; consultants do
      not see the action and backend authorization remains authoritative.
- [ ] Existing frontend feature tests and API clients remain functional.

## Out Of Scope

- OIDC callback parsing or token validation in React.
- Provider-specific UI or claims.
- Backend auth/authorization changes.
- Fine-grained role-based controls outside Users administration.
- New frontend dependencies or automated browser E2E tooling.

## Implementation Notes

- Read ADR-004, `docs/operations/testing.md`, current router/workspace/API-client patterns,
  and TASK-039C/D contracts.
- Prefer one shared request helper over separate auth logic in every feature
  client. Migrate all clients in this task so unsafe requests cannot silently
  omit CSRF.
- Component tests should mock application-session endpoints, not Entra or
  Authentik internals.

## Testing

Required:

- [ ] Auth context and protected-route tests
- [ ] Shared request-helper and migrated API-client tests
- [ ] Admin/consultant navigation and session-revocation tests
- [ ] Login, restoration, logout, `401`, `403` and CSRF cases
- [ ] Frontend lint, full tests and build
- [ ] Manual local Authentik browser flow after TASK-039E

Commands:

```bash
cd frontend
pnpm lint
pnpm test
pnpm build
```

## Documentation

Update frontend-facing test documentation only where necessary. The complete
operator/local flow and architecture diagrams belong to TASK-039G.

## Notes For AI Agent

- Ala lisaa provider-tokenien kasittelya frontendiin.
- Ala lisaa uusia riippuvuuksia.
- Varmista, etta kaikki mutation-clientit kayttavat CSRF-suojattua helperia.
