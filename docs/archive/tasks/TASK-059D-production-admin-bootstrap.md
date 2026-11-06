# TASK-059D First Production Administrator Bootstrap Command

## Source Plan

The approved UpCloud/Caddy/direct-Entra amendment is recorded in
[ADR-013](../../adr/0013-shared-entra-local-https-deployment.md).
The initial host is Ubuntu 26.04 LTS with private Docker PostgreSQL 18 and
required daily encrypted on-server backups in `/opt/postgres-backups` with
7-day retention (G/E/F).
These CLI contracts remain database-only and provider-neutral.

Approved deployment plan: initialize reference data without users, then create
the first production administrator through `python -m app.bootstrap_admin`.
This specification does not implement or execute the command.

Dependency: [TASK-059A](TASK-059A-shared-entra-local-https-architecture.md).
Final sequence verification also requires
[TASK-059C](TASK-059C-production-reference-data-seed.md).

## Goal

Resolve fresh-install login admission without manual production SQL, development
accounts, automatic user creation at login, or an unauthenticated public endpoint.

## Requirements

- Add interactive `python -m app.bootstrap_admin` to the production backend
  image. Prompt for the designated administrator's name and matching Entra email.
- Reuse existing User validation and trimming, set the role to admin internally,
  and insert one active user. Do not expose a role-selection or promotion mode.
- Use DATABASE_URL only without initializing FastAPI, OIDC, browser/session
  settings, or requiring an existing application actor.
- Require an empty users table, including no soft-deleted rows. Check emptiness
  and insert in one transaction serialized against concurrent writers. A second
  call must refuse without updating, reviving, promoting, or creating a user.
- Permit existing metamodel/reference data: this is not an empty-database check.
  Leave initial audit actor fields null as allowed for administrator bootstrap.
- Require the schema to be migrated already. Do not run baseline, migrations,
  reference seeding, or bootstrap automatically during service startup.
- Handle invalid/blank input, interrupted input, populated tables, missing schema,
  and database failures without partial writes. Return nonzero on failure/refusal.
- Emit generic result messages without echoing name/email, credentials, or database
  URLs into application logs. Keep personal input out of command arguments and
  repository records; document using an appropriately private operator terminal.
- Preserve database roles, user soft-delete rules, `(issuer, subject)` linking,
  and the authenticated Users API for subsequent user management.

## Acceptance Criteria

- [ ] The production image command creates exactly one valid active admin in an
      empty users table, including after TASK-059C reference-data initialization.
- [ ] Existing active or soft-deleted rows cause refusal without any mutation.
- [ ] Concurrent attempts cannot both create administrators.
- [ ] Invalid input, cancellation, and database errors leave no partial user and
      do not expose credentials/personal data in result or error logs.
- [ ] Database-only, non-root image execution works without OIDC configuration.
- [ ] Matching direct-Entra identity can subsequently first-link through existing
      guarded authentication; bootstrap does not create identities or sessions itself.
- [ ] No public endpoint, schema change, production user, or production mutation.

## Out Of Scope

- Account recovery, role promotion, batch provisioning, identity relinking,
  resetting an existing database, or changes to authentication/authorization APIs.
- Development seed changes, new dependencies, and actual production execution.

## Implementation Notes

Read `AGENTS.md`, `docs/architecture/overview.md`, A's amendment, ADR-002/004,
`docs/architecture/domains/USERS.md`, `docs/architecture/concepts/USER.md`, `docs/architecture/data/DATA-MODEL.md`,
`docs/architecture/data/DATABASE.md`, database instructions, and `docs/operations/testing.md`.
Reuse validation/models and database-only runner patterns while preserving the
bootstrap exception for nullable audit actors. Do not fabricate an actor ID or
grant application access based on Entra groups.

## Testing

Required: CLI validation/error/redaction tests and disposable PostgreSQL tests
for successful insertion, active/deleted-user refusal, concurrent writers,
rollback, and reference-seed -> bootstrap ordering. Exercise normal identity
first-link with a test provider and verify bootstrap created no identity/session.

```bash
cd backend
uv run ruff check .
uv run pytest
uv run pyright
cd ..
docker build --target production -t shadow-backend:local -f backend/Dockerfile .
```

Exercise the production image with DATABASE_URL only against a migrated
disposable database. Frontend tests and real production login are not applicable
to this CLI task; actual direct-Entra smoke is part of F.

## Documentation

Update `backend/README.md`, `docs/architecture/deployment.md`, `docs/operations/testing.md`, and relevant
Users/bootstrap documentation. Explain private terminal use, empty-users-table
requirement, reference seed ordering, refusal behavior, and subsequent Users UI
management. Do not document manual production INSERTs as a fallback.

## Notes For AI Agent

- Implement only this command and its checks when separately requested.
- Never bootstrap a real production administrator as part of implementation QA.
- Record eventual Step 13 reviews under `docs/ai-reviews/TASK-059D/` and report checks.
