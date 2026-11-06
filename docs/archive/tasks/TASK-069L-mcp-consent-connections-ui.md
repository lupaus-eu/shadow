# TASK-069L MCP Consent Page And Connections UI

## Source Plan

This task is part of the approved plan "AI chat via MCP for generating Shadow
model and timeseries data", accepted on 2026-10-21. See
[TASK-069A](TASK-069A-ai-mcp-architecture.md) and ADR-015.

## Goal

Let a signed-in user approve or deny an AI client's access request, and see and
revoke their connected AI clients.

## Requirements

- Add the route `/ai/authorize` in `frontend/src/App.tsx` and the page
  `frontend/src/features/ai/AuthorizePage.tsx`.
  - An anonymous user is sent through the existing `LoginPage` with
    `return_to=/ai/authorize?request=…`.
  - The page reads `request` from its own query string and loads the pending
    request with `GET /api/v1/ai/oauth/consent?request=<id>`. The id never
    goes into an API path and is never shown or logged.
  - The page shows:
    - the client name, labelled as self-declared by the client and rendered
      isolated from the surrounding text (`<bdi>` or `dir="auto"` on its own
      element), so bidirectional text cannot reorder the label or the page;
    - the redirect host (`redirectHost`, which the API always returns) when
      `redirectIsLoopback` is false. When it is true (a `127.0.0.1`, `[::1]`
      or `localhost` redirect), the page shows a loopback notice instead of
      the host: the code goes to a program on this computer, and local
      programs cannot be verified by name. The page uses the server's flag
      and never parses host strings;
    - the requested access in plain language.
  - Read access and write access are explained separately. The write
    explanation says that changes are proposed only and must be applied in
    Shadow. The page also says that data read by the AI client goes to the
    user's AI vendor.
  - Approve and Deny call `POST /api/v1/ai/oauth/consent/approve` or `.../deny`
    with `{"request": "<id>"}` in the JSON body, through the CSRF-protected
    client. On success the page navigates with `window.location.assign` only
    to the server-returned `redirectUrl`. It never builds or modifies a
    redirect URL itself.
  - The page shows expired, invalid and already-decided states, and a
    "not available" state when `features.mcp` is false.
- `frontend/src/features/ai/ConnectionsList.tsx` lists the user's grants:
  the client name (isolated and labelled self-declared) and `clientId`,
  scope, and created, last used and expiry times. It has a revoke action
  with confirmation. The component is reusable by the Metrics AI panel
  (TASK-069M). It keeps working when `features.mcp` is false, so grants can
  still be revoked.
- In the existing `admin`-only Users administration
  (`frontend/src/features/users/UsersTab.tsx`), add a "Revoke AI connections"
  action with confirmation. It calls TASK-069F's
  `POST /api/v1/ai/users/{user_id}/connections/revoke` and shows the number
  of revoked grants. It supports offboarding and the incident procedure in
  ADR-015.
- API wrappers in `frontend/src/api/ai.ts` use `authenticatedFetch`.

## Acceptance Criteria

- [ ] Vitest tests cover:
      - the authorize page loading, approve, deny, and expired and decided
        states, with the anonymous redirect asserted;
      - that approve navigates to exactly the server-returned `redirectUrl`;
      - the "not available" state when `features.mcp` is false;
      - the client name rendered isolated with the self-declared label, on the
        consent page and in the connections list;
      - the loopback notice on the consent page when the API returns
        `redirectIsLoopback: true`, and the plain `redirectHost` for a vendor
        callback;
      - the connections list showing `clientId`, and revoke by `grantKey`;
      - the admin "Revoke AI connections" action, which is hidden for
        `consultant`;
      - the API wrappers (stubbed `fetch`).
- [ ] Tests follow the TASK-065 async rules: `findBy*` and `waitFor`, and
      `vi.restoreAllMocks()` in `afterEach`.
- [ ] No new frontend dependency is added.

## Out Of Scope

- The Metrics AI panel and change-set review (TASK-069M).

## Implementation Notes

Read before implementation:

```text
AGENTS.md
docs/adr/0015-ai-via-mcp.md
docs/architecture/domains/AI.md
docs/operations/testing.md
frontend/src/App.tsx
frontend/src/auth/AuthProvider.tsx
frontend/src/api/client.ts
docs/archive/tasks/TASK-069E-mcp-oauth-authorize-consent.md
docs/archive/tasks/TASK-069F-mcp-oauth-tokens-connections.md
```

The CSP has `form-action 'self'`. Navigating to the client callback with
`window.location` is allowed, but a form POST to it is not.

## Testing

Required:

- [ ] Frontend tests
- [ ] Manual verification (complete the OAuth flow from Claude Code locally)
- [ ] Format check
- [ ] Lint
- [ ] Build

```bash
cd frontend
pnpm format:check
pnpm lint
pnpm test
pnpm build
python3 ../scripts/ai_review_records.py validate
```

## Documentation

Update `docs/architecture/domains/AI.md` (consent UX).

## Notes For AI Agent

- Branch: `feature/TASK-069L-mcp-consent-connections-ui`.
- Do not start until TASK-069F is merged.
- Save each Step 13 review record under `docs/ai-reviews/TASK-069L/`.
- Report all changed files and every verification command run.
