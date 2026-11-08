# Ticket 02: postgresql 18

Status: implemented

## Goal

Run PostgreSQL 18 everywhere and document the dump-and-restore upgrade.

## Implementation

- `postgres:18-alpine` in both compose files and `ci.yml`; volume `postgres18_data` at `/var/lib/postgresql`.
- `.gitignore` gets `/backups/`; new runbook `docs/runbooks/postgres-major-upgrade.md`; update `docker.md`, C4 and `deployment.md` volume names.
- Rehearse the upgrade with the dumps of the running stack.

## Acceptance criteria

- [x] A throwaway project starts PostgreSQL 18 with the init scripts (test database, Authentik role and database) and a healthy check.
- [x] The dumps from PostgreSQL 17 restore into it for both databases; row counts of key tables match.
- [x] The whole backend suite passes against PostgreSQL 18; compose and port checks pass; `make models` is valid.

## Testing

- [x] Migration/integration/architecture validation — see the technical design

## Ajetut tarkistukset

- [x] throwaway project `docker compose -p shadowpg18 ... up -d db` — PostgreSQL 18.6, data in `/var/lib/postgresql/18/docker` inside the named volume, init scripts created `shadow_test` and the Authentik role, healthy
- [x] dump of the running PostgreSQL 17 stack restored with `pg_restore --clean --if-exists --no-owner` — no errors; 1 organization, 6 timeline changes and 4 Authentik users came back; `alembic upgrade head` no-op at 0065
- [x] `TEST_DATABASE_URL=...:18132/shadow_test pytest -q` — 296 passed, 1 deselected
- [x] `python3 scripts/check-compose-ports.py` — OK; `make models` — valid

## AI review

- [x] Self-review of the diff against ADR-0053 and the technical design

## Documentation effects

- [x] Update architecture or ADR

## Blocked by

None.

## Completion record

- `postgres:18-alpine` in both compose files and CI, data volume `postgres18_data` at `/var/lib/postgresql`, `/backups/` ignored by Git, runbook `docs/runbooks/postgres-major-upgrade.md`, C4 and architecture documents updated; the throwaway project was removed (`down -v`). Local data still has to be moved once with the runbook (the dumps are in `backups/`).
