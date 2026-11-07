# Operations guide

This guide covers running, checking, and deploying Yearclock. Service design is
in [`docs/architecture/`](../architecture/README.md); step-by-step procedures
are in [`docs/runbooks/`](../runbooks/).

## Local stack

```bash
cp .env.example .env   # then replace placeholder secrets
docker compose up --build
```

| Service | Role |
| --- | --- |
| `db` | PostgreSQL with the Yearclock and test databases |
| `authentik-db-init` | Creates Authentik's separate logical database |
| `authentik-server`, `authentik-worker` | Identity provider, pinned by `AUTHENTIK_VERSION`; upgrade with `docs/runbooks/authentik-upgrade.md` |
| `authentik-config-init` | Applies the versioned identity-flow policy |
| `migrate` | Runs `alembic upgrade head` before the backend and worker start |
| `backend` | FastAPI, host port 8100 |
| `worker` | Background worker: Invitation email and daily recurrence materialization |
| `frontend` | Vite development server on host port 8173 |
| `caddy` | Edge proxy, only with `--profile edge` (host ports 8180 and 8143) |

All containers are named `yearclock-<service>-<n>`, and all host ports are in
Yearclock's range 8100–8199 on `127.0.0.1`. The full assignment is in
[docker.md](../architecture/docker.md#project-name-and-host-ports).

First-run Authentik setup: [authentik-local.md](../runbooks/authentik-local.md).
Production operator guides: [authentik-invitations.md](../runbooks/authentik-invitations.md)
(invite people to enroll) and [backup.md](../runbooks/backup.md) (off-host
backups, disk check, restore rehearsal).
Stripe test mode: Ticket 03 of the
[end-user tutorial](../end-user-tutorial/yearclock-v1-testing.md).

## Configuration

Every required key is in [`.env.example`](../../.env.example): application and
database URLs, session cookie settings, Stripe, Authentik and OIDC, and the
shared Scaleway (`SCW_*`) and Transactional Email settings. Never commit
`.env`. Add new keys to `.env.example` in the same change that uses them.

### MCP interface

The MCP interface for agents is off by default. Its settings (`MCP_ENABLED`, `MCP_OIDC_ISSUER`,
`MCP_OIDC_CLIENT_ID`, `MCP_OIDC_CLIENT_SECRET`) are in `.env.example` and `.env.production.example`;
turning it on, adding clients, rotating the secret, and stopping it are in
[`docs/runbooks/mcp-interface.md`](../runbooks/mcp-interface.md). Migration `0048` adds the two
per-Organization switches (`mcp_enabled`, on by default; `mcp_platform_blocked`, off by default).

### Agent call log

Every MCP call is recorded without content in `mcp_calls` (migration `0059`, ADR-0047); Owners and Admins read it in Activity under **Agent calls**. `MCP_READ_LOG_RETENTION_DAYS` (default 90) sets how long successful read calls are kept; the worker enqueues one `mcp.read_log_cleanup` job per active Organization each day. Writes, refusals and failures are kept. If the table cannot be written, agent writes fail and reads still work, so watch the backend log for `could not be recorded`.

### Event content migration (P11)

- Migration `0047` adds `location`, `links`, `description_format`, `starts_at`,
  and `ends_at` to Events and Series, turns every existing single link into a
  one-link list titled with its host name, rewrites Occurrence overrides that
  hold a link, and drops `external_url`. Event History entries keep their old
  `external_url` key and read as link lists. Downgrading keeps only the first
  link of each list. Take a backup before upgrading as usual
  (`scripts/ops/backup-databases.sh`).

### Subscription (P14)

- In-product cancellation needs the Stripe secret key to be allowed to update
  subscriptions and release subscription schedules. The Customer Portal may
  keep its cancellation control on: both give the same state. Keep **Update
  quantities** off.

- Resubscription opens Checkout for the existing Stripe customer, so the
  webhook endpoint must receive `checkout.session.completed` for those sessions
  (it already does for sign-up). Metadata `purpose` and `seats` on the session
  are read by the webhook; do not strip them in a proxy.

- `LIMIT_BILLING_CONTACT_CHANGES_PER_DAY` (default 5) caps how often an
  Organization's billing name and email may change. The Stripe secret key must
  be allowed to update customers.

### Notifications

- `NOTIFICATION_RETENTION_DAYS` (default 90): the worker enqueues one
  `notifications.cleanup` job per active Organization each day (with the other
  daily jobs), which deletes older notifications. A failed job appears in the
  operator console and can be replayed. The Organization purge deletes all
  notifications and settings of the Organization.
- `LIMIT_NOTIFICATION_EMAILS_PER_DAY` (default 10) caps notification email per
  recipient in 24 hours, counted from the outbox; notifications past the cap
  stay in the app. The worker sends them with Invitation email (topic
  `notification`); failures retry like other email.
- The Summary of upcoming Events is queued by the `notifications.summary` job
  on the first scheduler pass after 08:00 in each Organization's time zone, so
  it arrives within `WORKER_SCHEDULE_INTERVAL_SECONDS` (default one hour) after
  08:00. Failures retry like other background jobs and email; a rerun never
  sends a second Summary for the same local day.
- The rows are written inside the request that causes them, so a large change
  (sharing a Yearclock with 1000 members) took about 0.2 s in the test run.

### Legal documents

The texts are Markdown files in `backend/legal/` and ship with the backend image (ADR-0041,
[`docs/legal/README.md`](../legal/README.md)). `LEGAL_SHOW_DRAFTS=true` shows the unreviewed drafts to signed-in customers only (the alpha); keep it `false` once real customers join unless counsel has cleared the drafts. Published texts are always public. And
`LEGAL_CONTACT_EMAIL` is the address the notice emails give for objections. The backend refuses to start on a
malformed set and names the file.

To publish a new version: the lawyer approves the text; raise `version`, set `effective_from` at least 30 days ahead
for a change that needs notice, set `status: published` in both locales, and release. Within one scheduler pass
(`WORKER_SCHEDULE_INTERVAL_SECONDS`, an hour by default) every Organization's Owners get a notice in the app and an
email that states the 30 days and the legal contact; a first release announces each published document once, so
publish the first set in one release. Owners accept `required` documents in Organization settings. Nothing locks an
Organization that has not accepted. Check the **Failed jobs** page in the operator console afterwards for
`legal.announce` failures.

### Exports and imports

- `LIMIT_EXPORTS_PER_HOUR` (default 20) caps the exports, imports, and import
  previews of one user in one Organization per hour. The count comes from the
  Audit Log (`yearclock.export`, and with the import ticket
  `yearclock.import` and `yearclock.import_preview`), so there is no counter to
  reset: raising the value takes effect at once, and a refused user is told
  when the oldest counted action leaves the hour.
- `LIMIT_ORGANIZATION_EXPORTS_PER_HOUR` (default 3) limits an Owner's Organization
  Exports per hour (audit action `organization.export`). The file is streamed one
  Yearclock at a time; at the largest allowed Organization (50 Yearclocks of 3000
  Events) the test run took about 13 s and produced 63 MB, so check proxy
  timeouts and buffering for `GET /api/v1/organizations/{id}/export`.
- A person's own data request is handled with
  `docs/runbooks/personal-data-request.md`.
- `LIMIT_IMPORT_ROWS` (1000) and `IMPORT_MAX_BYTES` (2 097 152) bound an import
  file; the upload is read in memory and discarded after the preview or save
  (no file storage). Raise them together with the Event ceiling if needed.
- Export files are built in memory on the API; a Yearclock holds at most 3000
  Events (`LIMIT_EVENTS_PER_YEARCLOCK`), so a file stays small. The audit entry
  has the format, scope, row count, and language, never the content.

### Data transfer

- `LIMIT_TRANSFERS_PER_HOUR` (default 3) caps a user's all-Organizations CSV
  exports, import previews, and import saves per hour. One transfer writes one
  audit entry per Organization (`data.export`, `data.import_preview`,
  `data.import`) with a shared request id; the limit counts distinct request
  ids, so there is no counter to reset.
- `LIMIT_TRANSFER_ROWS` (200 000) and `TRANSFER_MAX_BYTES` (104 857 600) bound
  an import file. The upload is read in memory (expect several times the file
  size in memory while it is checked) and discarded; raise the proxy body size
  and timeouts for `POST /api/v1/data-transfer/import`, and check buffering for
  the streamed `GET /api/v1/data-transfer/export`.
- A preview runs the whole import in a savepoint and rolls it back, so it
  costs as much as a save.

## Checks

| Check | Command |
| --- | --- |
| Backend tests (needs `db`) | `cd backend && pytest -q` |
| Frontend type check and build | `npm --prefix frontend run typecheck && npm --prefix frontend run build` |
| Browser tests (needs the stack) | `npm --prefix frontend run test:browser` |
| Compose project name and ports | `python3 scripts/check-compose-ports.py` |

CI (`.github/workflows/ci.yml`) runs the Compose port check, the frontend
checks and browser tests, Alembic upgrade and downgrade, and the backend
tests.

## Monitoring and recovery

- Health: `GET http://localhost:8100/health`. Database readiness:
  `GET /api/v1/system/status` (requires sign-in).
- Failed work: the worker retries email up to three times and background
  jobs up to five times with backoff, then marks them `failed`. The operator
  console (**Failed jobs**, `/platform/jobs`) lists them with a short error, and Platform Admins can
  replay them.
- Monitoring and alerts: `docs/operations/monitoring.md`.
- Backups: `scripts/ops/backup-databases.sh [dir]` dumps the Yearclock and
  Authentik databases separately; `scripts/ops/restore-drill.sh <yearclock dump>
  <authentik dump>` restores each into a scratch database, verifies it, and
  drops it. Run the drill monthly.
- Organization purge: `ORGANIZATION_DELETION_RETENTION_DAYS` (default 30)
  sets the recovery window. Failed `organization.purge` jobs appear in the
  operator console and can be replayed safely.
- Support Access expiry: the worker marks approved grants past their end
  time as `expired` about once a minute and audits each. Access already stops
  at the end time because PostgreSQL checks the expiry on every query.
- Platform staff: enroll with
  `docker compose exec backend python -m app.platform_admin enroll --email <address> --role platform_admin`.
- Monitoring, alerting, and backup and restore drills are not yet defined.

## Production

Production deployment is not ready. See
[deployment.md](../architecture/deployment.md) for the known gaps and
[production-readiness.md](../runbooks/production-readiness.md) for the
pre-launch checklist.
