# PostgreSQL major version upgrade (17 to 18)

ADR-0053 moves the stack from PostgreSQL 17 to 18. A major version is never upgraded in
place: the new image starts an empty cluster and the data comes back from the dumps that
`scripts/ops/backup-databases.sh` writes (ADR-0011). The old data stays untouched in the old
volume until you remove it.

Why a new volume: the official `postgres:18` image keeps data in
`/var/lib/postgresql/18/docker` and declares `/var/lib/postgresql` as its volume. The data volume
is therefore mounted at `/var/lib/postgresql` and is named `postgres18_data`; the PostgreSQL 17
volume (`postgres_data`, for the local stack `shadow_postgres_data`) is not used any more.

Production holds no data yet and starts on 18: skip this runbook there.

## Local stack (keep your Authentik users and models)

Do this once, on the machine that has data. Commands run from the repository root.

1. **Back up while the old stack runs on PostgreSQL 17:**

   ```bash
   scripts/ops/backup-databases.sh backups
   ```

   The two files (`shadow-<stamp>.dump`, `authentik-<stamp>.dump`) are in `backups/`, which Git
   ignores. Both dumps contain data and credentials hashes: do not share or commit them.
2. **Switch to the new definitions** (`git pull` or your branch) and stop the stack:

   ```bash
   make dev-down
   ```

3. **Start only the database** (a fresh PostgreSQL 18 cluster in the new volume; the init scripts
   create the test database and the Authentik role) and create the Authentik database:

   ```bash
   COMPOSE="docker compose -f docker-compose.yml -f docker-compose.dev.yml"
   $COMPOSE up -d --wait db
   $COMPOSE run --rm authentik-db-init
   ```

4. **Create the application role** that the migrations normally create, because the dump holds
   only its grants (roles belong to the cluster, not to a database):

   ```bash
   $COMPOSE exec -T db psql -v ON_ERROR_STOP=1 -U shadow -d shadow \
     -c "CREATE ROLE shadow_app NOLOGIN NOSUPERUSER NOBYPASSRLS" -c "GRANT shadow_app TO shadow"
   ```

5. **Restore both dumps** (use the file names from step 1; the owner of the Authentik database is
   the `authentik` role):

   ```bash
   $COMPOSE exec -T db pg_restore --clean --if-exists --no-owner --role=shadow -U shadow -d shadow < backups/shadow-<stamp>.dump
   $COMPOSE exec -T db pg_restore --clean --if-exists --no-owner --role=authentik -U shadow -d authentik < backups/authentik-<stamp>.dump
   ```

   No output means no errors.
6. **Start everything.** `migrate` applies any migration newer than the dump:

   ```bash
   make dev
   ```

7. **Check:** sign in at http://localhost:8173 and open your model; `docker compose ... exec db psql -U shadow -d shadow -tAc "show server_version"` shows 18.x.
8. **Clean up** after a few days, when you are sure: `docker volume rm shadow_postgres_data` and
   delete the files in `backups/`.

If something goes wrong, nothing is lost: `make dev-down`, restore the previous definitions with
`git checkout`, and `make dev` starts PostgreSQL 17 on the old volume again.

## What was rehearsed

On 2026-11-09 the dumps of the running PostgreSQL 17 development stack were restored into a
throwaway PostgreSQL 18.6 project with exactly these steps (organizations, models, timeline rows
and the four Authentik users came back), `alembic upgrade head` was a no-op at 0065, and the
whole backend suite passed against that PostgreSQL 18.6.

## Next major version

Repeat this runbook with the next image and volume name (`postgres19_data`), after reading the
image's release notes for a changed data path.
