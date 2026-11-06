# TASK-074 Single MCP Connector

## Source Plan

Developer-requested amendment (2026-11-03) to ADR-015, made after the
TASK-069P production enablement. Shadow exposes two MCP servers today:
`/api/mcp/read` (`shadow.read`) and `/api/mcp/write` (`shadow.write`).
Each is a separate OAuth resource, so a user adds two connectors, goes through
consent twice and holds two grants; Claude Code even registers two OAuth
clients. The developer wants **one connector that handles both read and write,
authorized once**. It must stay possible to limit a role (for example
consultants) to read-only later. Today admins and consultants both keep read
and write.

ADR-015 explicitly rejected "one MCP service with mixed scopes", so this task
amends ADR-015 and implements the amendment, as TASK-069O did.

Decisions recorded with the plan:

- **Clean switch.** `/api/mcp/read` and `/api/mcp/write` are removed. A
  migration deletes the old grants, as lazy cleanup already does: a change
  set's `grant_id` becomes null, and its `client_id` and `client_name` stay as
  the audit record. Each user replaces their two connectors with the new one
  once. Keeping the old URLs for a transition is not chosen.
- **Read-only is decided by role only.** The consent page offers no choice. A
  client may still ask for `scope=shadow.read`, and it then gets a read-only
  grant.
- **Scopes stay the permission vocabulary.** `shadow.read` and
  `shadow.write` remain. `ROLE_SCOPES`
  (`backend/app/api/v1/mcp_oauth/token_service.py`) stays the one place that
  limits a role. Changing `consultant` to `{READ_SCOPE}` later is a one-line
  change with no token format or URL change.
- **Per-tool scope check.** One FastMCP server registers every component with
  a scope check. fastmcp 4.1.4's per-component `auth` hides a tool the caller
  lacks the scope for and answers a call to it with "Unknown tool"; a check
  that raises is logged and treated as a denial, so it fails closed. A future
  read-only role sees only read tools and prompts on the same URL, and a role
  change takes effect on the next request because the token is verified on
  every call.
- **One PR.** The backend, frontend and plugin must ship together, so the PR
  stays one even though it will exceed the 500-line guideline, mostly through
  tests and docs.

| Task | Deliverable | Dependency |
| --- | --- | --- |
| TASK-074 | ADR-015 amendment, single MCP endpoint and resource, migration 020, plugin, UI and docs | `main` (TASK-069P merged) |
| Production deployment | Release with `deploy-release --mcp-approval` | TASK-074 merged and separate approval |

## Goal

Serve all Shadow MCP tools and prompts from one MCP endpoint, `/api/mcp`,
that a user connects and authorizes once, with one OAuth grant covering read
and write. Each tool checks its own scope against the effective scopes of the
caller's role, so a role can later be limited to read-only without a token,
URL or client change.

## Requirements

### ADR-015 amendment

- Amend [ADR-015](../../adr/0015-ai-via-mcp.md) with a dated
  amendment (2026-11-03):
  - the status line and context: one MCP service with two scopes;
  - replace the "Two MCP Services" section, the OAuth endpoints table,
    "Audience binding", "Authorization On Every MCP Request" (now the per-tool
    scope check) and grant reuse;
  - Data Leaving Shadow: a role, not the user, limits access to read;
    revocation is unchanged;
  - Options Considered: "one service with mixed scopes" accepted, with the
    reason (one connector and one consent), and "keep the old URLs for a
    transition" not chosen;
  - the task table with TASK-074.

### One endpoint and one resource

- `POST /api/mcp` is a single FastMCP server named "Shadow", with resource
  `<PUBLIC_ORIGIN>/api/mcp`. Protected-resource metadata is served at
  `/.well-known/oauth-protected-resource/api/mcp` with
  `scopes_supported = ["shadow.read", "shadow.write"]`.
- `/api/mcp/read`, `/api/mcp/write`, `/api/mcp/` and their metadata documents
  return 404.
- `McpBearerAuth` (`backend/app/mcp/auth.py`) no longer takes a server name.
  It requires the canonical resource and the minimum scope `shadow.read`; a
  missing scope gives the existing 403 `insufficient_scope` challenge.
  `McpServerName` is removed.

### Per-tool scope check

- Add `requires_scope(scope) -> AuthCheck` to `backend/app/mcp/auth.py`. It
  reads `current_principal.get()` and returns `scope in principal.scopes`.
  `principal.scopes` is the effective set, grant scopes ∩ `ROLE_SCOPES[role]`,
  computed in `verify_access_token`.
- Register every read tool and both skill prompts with
  `auth=requires_scope(READ_SCOPE)`, and every write tool with
  `auth=requires_scope(WRITE_SCOPE)`.

### Server composition

- `read_server.py` and `write_server.py` keep their tool code.
  `build_read_server` and `build_write_server` become
  `register_read_tools(server, runtime, settings)` and
  `register_write_tools(server, runtime, settings)`.
- A new `backend/app/mcp/server.py` holds `build_mcp_server(runtime, settings)`.
  It creates one `FastMCP("Shadow", instructions=..., mask_error_details=True)`
  and registers both tool sets.
- The instructions are one combined text, with variants with and without
  `MCP_CHANGE_SET_REVIEW_ENABLED`. Cross-references such as "the read service's
  get_change_set_review" become plain tool names. One sentence says that the
  change-set tools are listed only when both the user's role and the access
  granted to the connection allow proposing changes (reworded after AI review
  finding F-001, which a read-only grant also triggers).
- `MCP_CHANGE_SET_REVIEW_ENABLED` still adds `apply_change_set` and
  `reject_change_set`, with no other change.
- `backend/app/mcp/endpoints.py` builds one endpoint and one route.
- `backend/app/main.py`: `NO_STORE_PATH_PREFIXES` changes `"/api/mcp/"` to
  `"/api/mcp"` so the exact path stays no-store; the lifespan covers one
  server.

### OAuth (`backend/app/api/v1/mcp_oauth/`)

- **Constants (`service.py`).** Replace `MCP_SERVER_SCOPES` and
  `canonical_resources()` with `MCP_SCOPES = (READ_SCOPE, WRITE_SCOPE)` and
  `canonical_resource(settings)`, which returns the one URI.
- **Authorize (`_validated_authorization_parameters`).**
  - `resource` must be exactly the canonical URI, otherwise `invalid_target`.
  - `scope` is optional and may appear at most once. It is a space-separated
    set of known scopes that includes `shadow.read`, in any order and
    without duplicates. It is normalised to `"shadow.read"` or
    `"shadow.read shadow.write"`.
  - An omitted `scope` means both scopes. Anything else, including
    write-only, is `invalid_scope`.
- **Consent.**
  - `load_consent` returns the requested scopes ∩ the User's role scopes, so
    the page shows exactly what will be granted.
  - `approve_consent` stores that narrowed set on the pending request. If
    `shadow.read` is not in it, approval redirects with `access_denied`; no
    current role reaches this.
- **Exchange and grant reuse.** The grant copies the pending scopes.
  `_reusable_grant`, still keyed per (client, User, resource), takes the
  scopes of the newest consent.
- **Token response `scope`.** It is the effective set, grant scopes ∩ the
  current role, in both exchange and refresh (RFC 6749 §5.1 allows it to
  differ from the request).
- **Refresh.**
  - `resource` must equal the grant's.
  - A `scope` that is sent must name only known scopes; otherwise
    `invalid_scope`.
  - The token keeps the grant's scopes, and the response says which. Tokens
    are bound to the grant and carry no scope of their own, so narrowing per
    token is not supported. This avoids a reconnect loop when a client
    re-sends both scopes after its role was narrowed.
- **`verify_access_token`.** It checks the canonical resource and the minimum
  `shadow.read`, and returns the effective scopes on `McpPrincipal`.
- **Connections API.** `scope` reports the effective scopes. The shape is
  unchanged.
- **Discovery.** The authorization server metadata `scopes_supported` is
  unchanged.

### Database

- Migration `020_alter_mcp_oauth_single_resource.sql` and its `.down.sql`. Migration 017
  is not edited.
- **Up:**
  1. Delete all `mcp_oauth_authorization_requests`. They expire after 10
     minutes anyway.
  2. Delete the tokens, then the grants, whose `resource` is not
     `LIKE '%/api/mcp'`. The FK sets `ai_change_sets.grant_id` to null.
  3. Replace the four CHECK constraints of migration 017
     (`ck_mcp_oauth_grants_scope`, `ck_mcp_oauth_grants_scope_resource`,
     `ck_mcp_oauth_authorization_requests_scope`,
     `ck_mcp_oauth_authorization_requests_scope_resource`) with:
     - `scopes IN ('shadow.read', 'shadow.read shadow.write')`
     - `resource LIKE '%/api/mcp'`
  4. Clients stay; stale-client cleanup removes them after 30 days.
- **Down:** delete requests, and tokens and grants on the new resource, then
  restore the 017 constraints verbatim.
- Mirror the constraints in `backend/app/api/v1/mcp_oauth/models.py`.
- Add 020 to the hand-written down sequences in
  `backend/tests/test_migrations_integration.py`.

### Client-facing changes

- **Plugin.**
  - `backend/app/mcp/plugin/.mcp.json`: one server, `"shadow"` →
    `https://shadow.lupaus.eu/api/mcp`.
  - `backend/app/mcp/plugin/.claude-plugin/plugin.json`: version 0.2.0 →
    0.3.0, and update the description.
  - `.claude-plugin/marketplace.json`: update the description.
  - Skills (`backend/app/mcp/plugin/skills/*/SKILL.md`). Their guidance stays;
    only the references to two servers change, plus one sentence for a
    read-only role:
    - `shadow-model-building`:
      - The description says "through the Shadow MCP server".
      - "when the write server lists `apply_change_set`" becomes "when
        `apply_change_set` is listed", and "Only when the write server lists
        `apply_change_set` and `reject_change_set`" becomes "Only when
        `apply_change_set` and `reject_change_set` are listed".
      - Drop "(read server)" after `get_change_set_review`.
      - "the read server's MCP prompt `timeseries_generation`" becomes "the
        MCP prompt `timeseries_generation`".
      - Add to the opening section: "If `create_change_set` is not listed,
        this connection can only read, because of the user's role or because
        the client asked only for read access when it connected: say so
        instead of proposing changes." (Reworded after AI review finding
        F-001: a read-only grant also hides the write tools.)
        No role is limited today; the sentence ships now so that limiting one
        later needs no new plugin release.
    - `shadow-timeseries-generation`: the description says "through the
      Shadow MCP server". The rest names no server and stays.
    - The plugin, the MCP prompts and the skill zips are all built from these
      files, so they change together.
  - `backend/app/mcp/skills.py`: update the comments.
- **Frontend (`frontend/src/features/ai/`).**
  - `ConnectInstructions.tsx`: one URL row ("Copy URL"), "Paste the URL and
    connect", and `claude mcp add --transport http shadow <origin>/api/mcp`.
    The Claude Code text says the plugin adds the Shadow server and skills,
    the hint for another origin says to add the server below, and the
    authenticate step says to select the Shadow server.
  - `aiPresentation.ts` `aiScopeLabel` and `AuthorizePage.tsx`
    `ScopeExplanation`: parse the space-separated set. Read only → "Read
    access". Read and write → "Read and propose changes", or "Read, propose,
    apply and reject changes" when review is on.
  - `frontend/src/api/ai.ts`: types unchanged.
- **Production check script.**
  `.github/scripts/verify-production-frontend-client.py` checks the one
  metadata document.
- **Caddy.** No change: `/api/*` and `/.well-known/oauth-protected-resource*`
  are prefix routes. Verified in the local end-to-end check.
- **Rate limit.** `MCP_RATE_LIMIT_PER_MINUTE` (120) now applies to one grant
  covering reads and writes together; previously each grant had its own
  bucket. Keep the default and document it.

## Acceptance Criteria

- [ ] ADR-015 records the dated amendment, and no current document still
      describes two MCP servers, two connectors or the URLs `/api/mcp/read`
      and `/api/mcp/write`, except historical task, QA and review records.
- [ ] `POST /api/mcp` serves one FastMCP server "Shadow". The old paths, the
      trailing-slash path and their metadata documents return 404.
- [ ] An unauthenticated request gets 401 with
      `resource_metadata=<origin>/.well-known/oauth-protected-resource/api/mcp`,
      and that document lists both scopes.
- [ ] A user with a current role authorizes once and gets one grant with both
      scopes. The token response, the consent page and the connections list
      show the effective scopes.
- [ ] A full-role principal lists 13 read tools and 6 write tools (8 with
      `MCP_CHANGE_SET_REVIEW_ENABLED=true`) and both prompts.
- [ ] With `ROLE_SCOPES` stubbed to a read-only role, the same endpoint lists
      only the read tools and the prompts, and a call to `create_change_set`
      or `apply_change_set` gets "Unknown tool". A role change shows or hides
      the write tools on the next call.
- [ ] Authorize accepts an omitted `scope`, `shadow.read`, and both scopes in
      either order; it rejects write-only, unknown and duplicated scopes and a
      repeated `scope` parameter with `invalid_scope`, and any other
      `resource` with `invalid_target`.
- [ ] Refresh keeps the grant's scopes, rejects unknown scopes and another
      resource, and reports the effective scopes.
- [ ] Migration 020 removes legacy requests, grants and tokens, nulls the
      change sets' `grant_id` while keeping `client_id` and `client_name`,
      enforces the new constraints on PostgreSQL, and rolls back fully.
- [ ] The plugin's `.mcp.json` has exactly one server `shadow`, and the
      plugin version is 0.3.0.
- [ ] The skills, and so the plugin, the MCP prompts and the skill zips,
      name one Shadow MCP server and no read or write server, and the
      model-building skill says what to do when `create_change_set` is not
      listed.
- [ ] The Metrics tab AI panel and the consent page show one URL and the
      combined scope labels.
- [ ] The LikeC4 model shows one `mcpService` component, and its PNG exports
      are regenerated.

## Out Of Scope

- The production deployment. It needs separate approval and
  `deploy-release --mcp-approval`.
- Limiting any role to read-only in code. Only the stubbed tests exercise it.
- A user-selectable read-only choice on the consent page.
- Keeping the old URLs, a redirect from them or a transition period.
- Per-token scope narrowing on refresh.
- Changes to the Entra registration, Caddy, the change-set engine or the
  Metrics tab review.
- Editing historical records: completed tasks, earlier QA records in
  `docs/operations/qa/AI-MCP-QA-CHECKLIST.md` and the review records.

## Implementation Notes

Read before implementation:

```text
AGENTS.md
docs/architecture/overview.md
docs/adr/0015-ai-via-mcp.md
docs/architecture/domains/AI.md
docs/architecture/concepts/AI_CHANGE_SET.md
docs/architecture/data/DATA-MODEL.md
docs/architecture/data/DATABASE.md
db/migrations/README.md
docs/operations/testing.md
docs/archive/tasks/TASK-069D-mcp-oauth-schema.md
docs/archive/tasks/TASK-069E-mcp-oauth-authorize-consent.md
docs/archive/tasks/TASK-069F-mcp-oauth-tokens-connections.md
docs/archive/tasks/TASK-069G-mcp-read-server-foundation.md
docs/archive/tasks/TASK-069O-mcp-change-set-review.md
```

Relevant code:

```text
backend/app/mcp/auth.py
backend/app/mcp/endpoints.py
backend/app/mcp/read_server.py
backend/app/mcp/write_server.py
backend/app/mcp/skills.py
backend/app/mcp/plugin/
backend/app/main.py
backend/app/api/v1/mcp_oauth/service.py
backend/app/api/v1/mcp_oauth/token_service.py
backend/app/api/v1/mcp_oauth/router.py
backend/app/api/v1/mcp_oauth/models.py
db/migrations/017_create_mcp_oauth_schema.sql
frontend/src/features/ai/
.claude-plugin/marketplace.json
.github/scripts/verify-production-frontend-client.py
```

- fastmcp 4.1.4 per-component auth: `_component_auth_allows` in
  `fastmcp/server/server.py` and `_evaluate_check` in
  `fastmcp/utilities/authorization.py`. No new dependency is needed.
- Branch: `feature/TASK-074-single-mcp-connector` from `main`. Merging it is
  the human approval of the amendment.

## Testing

Required:

- [ ] Backend tests
  - `test_mcp_auth.py`: one endpoint; the old paths and the trailing slash
    give 404; exact `WWW-Authenticate` with the new metadata URL; a token
    whose grant has another origin's `/api/mcp` resource gets 401
    `invalid_token`; the full-role and stubbed read-only tool lists, "Unknown
    tool" for write tools, and the next-call role change; the `fastmcp` lazy
    import and the 405s still hold.
  - `test_mcp_oauth_authorize.py`: scope parsing (omitted, read, both in
    either order, write-only, unknown, duplicate `scope` parameter);
    `invalid_target` against the single resource; the metadata documents;
    consent shows the role-narrowed scope, and approval with no read scope
    gives `access_denied`.
  - `test_mcp_oauth_tokens.py`: one grant for both scopes; the token response
    scope is the effective set; refresh `scope` rules; reuse takes the newest
    consent's scopes; verification against the single resource; connections
    report the effective scope.
  - `test_mcp_oauth_models.py`: the new constraints.
  - `test_mcp_tools.py`, `test_mcp_write_tools.py`, `test_ai_skills.py`,
    `test_ai_change_set_engine.py`: build the combined server, fixtures use
    `/api/mcp` with both scopes, the updated instruction wording, and
    `.mcp.json` has exactly one server.
  - `test_ai_skills.py`: the skills name no read or write server, and the
    model-building skill contains the read-only sentence.
- [ ] PostgreSQL integration tests
  - `test_migrations_integration.py`: 020 up removes legacy grants and
    tokens, nulls the change set's `grant_id` and keeps `client_name`; 020
    down fully reverses.
  - `test_ai_change_sets_postgresql_integration.py`,
    `test_mcp_oauth_postgresql_integration.py`: fixtures on the single
    resource.
- [ ] Frontend tests: `AiPanel.test.tsx`, `AuthorizePage.test.tsx`,
      `ConnectionsList.test.tsx`, `App.test.tsx`, `api/ai.test.ts` and
      `MetricsTabAiPanel.test.tsx` for one URL and the combined scope labels.
- [ ] Lint, format, typecheck and build
- [ ] Diagram and review record validation
- [ ] Manual verification (local end to end)

```bash
cd backend && uv run ruff check . && uv run ruff format --check . && uv run pytest && uv run pyright
cd ../frontend && pnpm format:check && pnpm lint && pnpm test && pnpm build
npx -y likec4@1.60.0 validate ../docs/diagrams/likec4/shadow-ai-mcp
python3 ../scripts/ai_review_records.py validate
```

Run the PostgreSQL integration tests as described in `docs/operations/testing.md`.

Local end to end at `https://app.localhost`, with `MCP_ENABLED=true` and
`MCP_CHANGE_SET_REVIEW_ENABLED=true` after migrating to 020:

- [ ] An unauthenticated `curl -X POST https://app.localhost/api/mcp` gives 401
      with `resource_metadata=.../.well-known/oauth-protected-resource/api/mcp`.
      `/api/mcp/read` gives 404.
- [ ] `claude mcp add --transport http shadow https://app.localhost/api/mcp`,
      then `/mcp` → authenticate **once**. The consent page shows read and
      write access, and one connection appears in the Metrics tab.
- [ ] The client lists all 21 tools and both prompts. `whoami` works, and a
      change set can be staged, submitted and applied from the chat.
- [ ] Revoking the connection in the Metrics tab cuts off both reading and
      writing.
- [ ] The plugin, reinstalled from the repository marketplace, shows one
      `shadow` server.

The read-only role is covered by the automated tests with the `ROLE_SCOPES`
stub; no role is limited in code.

## Documentation

- ADR-015, as described in Requirements.
- `docs/architecture/overview.md`, `AGENTS.md` (the MCP paragraph) and `README.md`.
- `docs/operations/local-development.md` and `docs/architecture/deployment.md`.
- `docs/architecture/domains/AI.md` and `docs/architecture/domains/DOMAIN.md`; check
  `docs/architecture/concepts/AI_CHANGE_SET.md` for references to the two services.
- `docs/architecture/data/DATA-MODEL.md` and `docs/architecture/data/DATABASE.md` (migration 020 and
  the constraints).
- `docs/operations/testing.md`.
- `docs/runbooks/production.md` section 14: one URL, the smoke `curl`, the
  shared rate-limit bucket, and the user steps after the release:
  - remove the old connectors and add the new one;
  - users who uploaded the skill zips to claude.ai or Claude Desktop
    download them again from the Metrics tab and replace the uploaded
    skills, which otherwise keep the old text about read and write servers.
    Plugin users get the new skills by updating the plugin.
- `docs/operations/qa/AI-MCP-QA-CHECKLIST.md`: append a TASK-074 section. The historical
  records stay unchanged.
- LikeC4 (`docs/architecture/diagrams/likec4/shadow-ai-mcp/` `model.c4`, `views.c4`,
  `deployment.c4`): one `mcpService` component. Regenerate the
  `docs/architecture/diagrams/generated/likec4-*.png` exports.
- PlantUML: check `docs/architecture/diagrams/db-physical-schema.puml` for the constraint
  text and regenerate its SVG if it changes.

## Notes For AI Agent

- Do not deploy to production or change `production.env`; the production
  release needs separate approval.
- Do not limit any role to read-only in `ROLE_SCOPES`.
- Do not add dependencies.
- Save each Step 13 review record under `docs/ai-reviews/TASK-074/`.
- Report all changed files and every verification command run.
