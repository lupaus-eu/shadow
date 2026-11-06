# Local Development

Local development is `https://app.localhost`: loopback-only Caddy terminates a locally trusted certificate, proxies `/api` and the OAuth discovery paths `/.well-known/oauth-authorization-server*` and `/.well-known/oauth-protected-resource*` to FastAPI and proxies the Vite application (including HMR WebSockets) on every other path. Authentik is no longer part of the active runtime. This does not delete old Authentik Docker volumes, existing application data, or existing `(issuer, subject)` rows.

## Initial setup

```bash
cp .env.example .env
make dev-init
```

`make dev-init` privately prompts for the shared registration's client ID, tenant ID and development client secret, then writes mode-600 `.env.entra.local`. It is ignored by Git. It contains only OIDC configuration and secret material; do not put an administrator email in it. The generated values use the exact tenant issuer and discovery endpoint, request only `openid profile email`, and set no Graph permissions or verified-email requirement.

If an earlier federation-era `.env.entra.local` exists, move that private file
aside first and then run `make dev-init`; the setup script refuses to overwrite
an existing secret file. This preserves the old Authentik volumes and
application database while preventing a silent use of obsolete provider values.

The same command creates `.local/app-tls/app.localhost.crt` and key. If valid legacy local CA material exists at `.local/authentik-tls`, its CA is reused to sign the app leaf; otherwise a separate app CA is created in `.local/app-tls`. The Caddy container mounts only the app leaf and its key, never a CA private key. Existing valid material is inspected for signature, hostname coverage and 30-day validity and is never overwritten. If renewal is required, the script tells the operator to remove only the expiring leaf certificate; the next run reuses its valid private key. The script explains incomplete and invalid states instead of replacing key material.

Trust the displayed CA certificate on the host before browser testing. For Debian/Ubuntu, using the CA path printed by the script:

```bash
sudo install -m 0644 /path/to/ca.crt /usr/local/share/ca-certificates/shadow-local-app.crt
sudo update-ca-certificates
```

Remove that explicit trust entry when it is no longer needed. Never copy or trust `ca.key`. Browser-specific certificate stores may need a separate import.

## Run and verify

```bash
make dev-up
make local-verify
```

`make dev-up` starts the application database, applies pending migrations and
the idempotent development seed, then starts the backend, one prediction worker,
the platform `worker` (background jobs and the email outbox, ADR-019), Vite and
local Caddy. The platform worker needs only `DATABASE_URL`; check it with
`docker compose … exec worker uv run python -m app.platform.worker health-check`
(exit code 0 when the database is reachable). Authentik (ADR-017) runs beside it: `authentik-server`, `authentik-worker` and the one-shot
`authentik-config-init`, behind Caddy at `https://id.app.localhost`; see
[authentik-local](../runbooks/authentik-local.md) for the dev users, the blueprints and
`make authentik-verify`. The local TLS certificate covers `app.localhost` and
`id.app.localhost`; an earlier certificate that lacks the second name must be renewed as
the script says. Local email goes to Mailpit, started by `make dev-up`; read it at
`http://localhost:8025` (`MAILPIT_UI_PORT`, loopback only). Optional settings:
`WORKER_SCHEDULE_INTERVAL_SECONDS` (default 3600) and `QUEUE_CLAIM_TIMEOUT_SECONDS`
(default 900, after which an unfinished claim is taken again). The development wrapper keeps its two local Users in the
same transaction while invoking the shared metamodel-only SQL/JSON used by
`python -m app.seed_reference_data`; never use that full wrapper in production.
It never runs a reset, `down -v`, volume deletion or provider mutation. The
database port and ingress are bound only to loopback; FastAPI and Vite have no
host-published ports.

All local Compose commands load `.env` followed by `.env.entra.local`, including
database-only, preview and diagram commands: Compose validates the required
OIDC variables for the whole model. Run `make dev-init` once before these targets.

Open `https://app.localhost`. Caddy permits only the exact Host, discards browser-supplied forwarding headers and sends FastAPI a fixed HTTPS/Host plus a client IP only from its fixed peer address. FastAPI accepts that header only from the Caddy `/32` peer. The backend and Caddy both redact callback `code`, `state`, `error`, `error_description` and Entra `session_state` values, ADR-015's MCP OAuth request id carriers `request` and `return_to`, and misplaced OAuth token parameters (`token`, `access_token`, `refresh_token`, `code_verifier`) from access logs. Caddy also replaces the `Location` response header and the `Authorization` and `X-Csrf-Token` request headers in its access log. Cookies are Secure, HttpOnly, host-only and preserve the existing SameSite and Path policy; unsafe requests still require exact Origin and CSRF checks.

The Vite HMR client uses `wss://app.localhost` port 443. Do not browse the internal Vite service directly: it is intentionally unexposed.

The development CSP in `local/Caddyfile` permits Vite's inline React-refresh
bootstrap by its SHA-256 hash. `pnpm test -- localCsp` in `frontend/` checks the
hash against the installed React plugin. If an upgrade changes the bootstrap,
update the hash from the exact inline script served by Vite (including whitespace)
and verify page rendering and HMR in a browser. Reload an already-running local
Caddy after changing its policy:

```bash
docker compose --env-file .env --env-file .env.entra.local exec -T local-caddy \
  caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile
```

## AI via MCP settings (TASK-069E, TASK-069F, TASK-069G, TASK-069N, TASK-069O, TASK-074)

MCP is off by default. `docker-compose.yml` passes these backend settings with
the defaults shown in `.env.example`; override them in `.env` (no secrets):

| Setting | Default | Meaning |
| --- | --- | --- |
| `MCP_ENABLED` | `false` | With `false`, the MCP endpoint `/api/mcp`, OAuth discovery, `/api/oauth/register`, `/api/oauth/authorize`, `/api/oauth/token`, `/api/oauth/revoke`, the `/api/v1/ai/oauth/consent` API and the skill zip download `/api/v1/ai/skills/{name}.zip` return 404 and `GET /api/v1/auth/session` reports `features.mcp=false`; the `/api/v1/ai/connections` API stays available |
| `MCP_CHANGE_SET_REVIEW_ENABLED` | `false` | With `true` (and `MCP_ENABLED=true`) the MCP server also lists the write tools `apply_change_set` and `reject_change_set`, and the session reports `features.mcpChangeSetReview=true` (ADR-015 amendment) |
| `MCP_OAUTH_REDIRECT_URIS` | claude.ai and claude.com callbacks plus `http://localhost:{port}/callback` (Claude Code) | Redirect URI allowlist; `{port}` is literal. A local client with another loopback callback, such as OpenCode's `http://127.0.0.1:{port}/mcp/oauth/callback`, needs its own entry in `.env` |
| `MCP_OAUTH_AUTHORIZATION_REQUEST_LIFETIME_SECONDS`, `MCP_OAUTH_AUTHORIZATION_CODE_LIFETIME_SECONDS` | `600`, `60` | Pending request and code lifetimes |
| `MCP_OAUTH_ACCESS_TOKEN_LIFETIME_SECONDS`, `MCP_OAUTH_REFRESH_TOKEN_IDLE_LIFETIME_SECONDS`, `MCP_OAUTH_GRANT_LIFETIME_SECONDS` | `3600`, `604800`, `2592000` | Access token lifetime, refresh token idle timeout and absolute grant lifetime; no token outlives its grant |
| `MCP_OAUTH_REGISTER_RATE_LIMIT_PER_MINUTE`, `..._AUTHORIZE_...`, `..._TOKEN_...`, `..._REVOKE_...` | `30`, `20`, `300`, `60` | Per-IP buckets of the separate `oauth_rate_limiter` |
| `MCP_OAUTH_MAX_PENDING_REQUESTS_PER_CLIENT`, `MCP_OAUTH_MAX_PENDING_REQUESTS`, `MCP_OAUTH_MAX_CLIENTS` | `20`, `1000`, `10000` | Pending request and client caps |
| `MCP_TOOL_CONCURRENCY` | `4` | Shared `anyio.CapacityLimiter` for MCP bearer verification and tool database work (1 to 64); change-set validate and submit use two connections per token |
| `MCP_RATE_LIMIT_PER_MINUTE` | `120` | Requests per grant and minute on `/api/mcp`, reads and writes together in one bucket (TASK-074), counted by the separate `mcp_rate_limiter` |
| `AI_CHANGE_SET_STATEMENT_TIMEOUT_MS`, `AI_CHANGE_SET_LOCK_TIMEOUT_MS` | `30000`, `5000` | Change-set `statement_timeout` and apply `lock_timeout`; the statement timeout must be longer |

To try the endpoints locally, set `MCP_ENABLED=true` in `.env` and recreate the
backend (`make dev-up`). Vendor-cloud connectors such as claude.ai cannot reach
`app.localhost`, so use a local MCP client (ADR-015).

### Connect Claude Code locally

Claude Code runs on Node.js, which does not read the host's CA store. Point
`NODE_EXTRA_CA_CERTS` at the local CA certificate that `make dev-init` printed:
`.local/app-tls/ca.crt`, or `.local/authentik-tls/ca.crt` when the legacy CA
was reused. Never point it at a key.

```bash
export NODE_EXTRA_CA_CERTS="$PWD/.local/app-tls/ca.crt"
claude mcp add --transport http shadow https://app.localhost/api/mcp
claude
```

In Claude Code, run `/mcp`, select `shadow` and authenticate **once**.
Claude Code registers itself and opens the consent page in the browser, where
you sign in with Entra and approve read and write access; the code returns to
Claude Code on an allowlisted loopback redirect and Claude Code exchanges it
for tokens. One connection then appears in the Metrics tab AI panel. Ask it
to call the `whoami` tool, which returns your Shadow User. The one grant
covers every tool your role allows: both current roles see all read and write
tools and both prompts. Until TASK-074 the read and write tools were separate
servers (`/api/mcp/read` and `/api/mcp/write`, now 404); remove such old
entries with `claude mcp remove`.

Ask Claude Code to stage a small change set, for example an
event in the `reality` scenario: it calls `create_change_set`,
`add_operations`, `validate_change_set` and `submit_change_set` and returns the
review URL `https://app.localhost/shadow/<org>/metrics?changeSet=<key>`.
`get_change_set` shows the submitted change set. With
`MCP_CHANGE_SET_REVIEW_ENABLED=false` nothing is applied by MCP: a human opens
the review URL, which opens the Metrics tab AI panel on the change set
(TASK-069M), and applies or rejects it there through the review API
`/api/v1/organisations/<org>/ai/change-sets/<key>/apply` or `/reject`
(TASK-069K).

To try the in-chat review (TASK-069O), also set
`MCP_CHANGE_SET_REVIEW_ENABLED=true` in `.env`, recreate the backend and
reconnect `shadow` in `/mcp` so that Claude Code reloads its tool list
(21 tools with the switch on). Ask Claude Code to review the submitted change
set: it calls `get_change_set_review` and shows the operations and any
replaced data. Tell it to apply or reject; Claude Code asks for permission
before `apply_change_set` or `reject_change_set` (do not add them to an allow
rule). The Metrics tab then shows the change set as reviewed through the AI
client.

An unauthenticated request shows the discovery challenge:

```bash
curl -si --cacert "$NODE_EXTRA_CA_CERTS" -X POST https://app.localhost/api/mcp
```

It answers `401` with
`WWW-Authenticate: Bearer resource_metadata="https://app.localhost/.well-known/oauth-protected-resource/api/mcp"`.
That document lists the scopes `shadow.read` and `shadow.write`. The old
paths `/api/mcp/read` and `/api/mcp/write` answer 404.

### Skills, the Claude Code plugin and MCP prompts locally (TASK-069N)

The skills are `backend/app/mcp/plugin/skills/*/SKILL.md`. The plugin in
`backend/app/mcp/plugin/` bundles them with a `.mcp.json` whose one server
`shadow` points at production, `https://shadow.lupaus.eu/api/mcp`.
Locally, keep the `app.localhost` server added above and load the plugin for
its skills, either for one session straight from the checkout (picks up
`SKILL.md` edits on the next start):

```bash
claude --plugin-dir backend/app/mcp/plugin
```

or installed from the local marketplace, as users install it from GitHub:

```bash
claude plugin marketplace add ./
claude plugin install shadow@shadow
```

The plugin's own server (`plugin:shadow:shadow` in `/mcp`) connects to
production, where MCP is on since 2026-11-03 (TASK-069P); disable it in `/mcp`
for local work. Production serves `/api/mcp` only after the release that
brings TASK-074 there. `claude --plugin-dir backend/app/mcp/plugin plugin details shadow` (or
`claude plugin details shadow@shadow` once installed) lists the skills
`shadow-model-building` and `shadow-timeseries-generation` and the one
`shadow` server. Then ask for a small model, for example a
team with a goal measured by a monthly revenue metric and two years of
generated revenue. Claude Code should call `get_type_catalog` first, preview
the generator spec with `preview_generated_timeserie`, stage, validate and
submit a change set, and return the review URL without claiming that anything
was applied. With the in-chat review enabled it should also offer to review
the change set in the chat and apply it only when you say so.

The MCP prompts `model_building` and `timeseries_generation` serve the same
`SKILL.md` bodies; Claude Code offers them as
`/mcp__shadow__model_building` and
`/mcp__shadow__timeseries_generation`. The backend reads the files when
it builds the app, and the dev server reloads only on Python changes, so
restart the backend container after editing a skill
(`docker compose --env-file .env --env-file .env.entra.local restart backend`).
The Metrics tab AI panel's Connect section links the skill zips
(`/api/v1/ai/skills/<name>.zip`, read on each request) for upload to claude.ai
or Claude Desktop; those vendor-cloud clients cannot reach `app.localhost`, so
test them only against an environment they can reach.

## Designated local Entra administrator

After migrations and the development seed have completed, pre-provision the designated administrator interactively:

```bash
make provision-local-admin
```

The command accepts no identity arguments, requires a terminal confirmation, validates display name and email through the shared User validation, and creates only an active `admin` User. It prints no email and creates no identity or session. It is development-only, is not an HTTP endpoint, and preserves all existing users, seeded users and roles. An existing active admin with the same email is verified without change; a consultant conflict, ambiguous match or soft-deleted account fails without an implicit role change or replacement.

Direct Entra login then uses the ordinary guarded first-link flow: only one active pre-provisioned User with the normalized email may receive a new exact `(issuer, subject)` binding. Login never creates a User. Existing Authentik bindings remain unchanged and are not relabelled or copied.

## Operator configuration and rotation

The Entra registration must already authorize the exact callback `https://app.localhost/api/v1/auth/callback` and post-logout return `https://app.localhost/login`, with the designated tester permitted by the tenant's policy. Those are authorized provider actions and are not performed by this repository. A missing/invalid private configuration makes Compose and FastAPI fail with an actionable configuration error without printing a secret.

To rotate the development secret, deliberately replace only `.env.entra.local` using `scripts/setup-local-entra.sh`, restart the local stack, and re-run `make local-verify`. Keep the development secret separate from the production secret. Removing obsolete callbacks or unused Graph permissions requires the remaining-consumer check and authorization under TASK-059F.

## Browser evidence

Automated tests simulate direct Entra; they do not prove a real tenant login. Record authorized browser verification separately with date, commit, tester, environment and redacted result for login, callback, guarded first-link, session role and logout. Until that setup is authorized, record it as pending; do not treat mock evidence as live-provider evidence.

The authorized TASK-059B browser run is recorded in `docs/operations/qa/AUTHENTICATION-QA-CHECKLIST.md`; TASK-059E repeated only the automated and read-only local probes. Local HTTPS and direct-Entra success does not establish production DNS, TLS or client-secret correctness; production setup follows `docs/runbooks/production.md` under TASK-059F. When probing HMR without a browser, note that the Vite WebSocket requires the per-server `token` query value served in `/@vite/client`; a tokenless upgrade returns `400`.
