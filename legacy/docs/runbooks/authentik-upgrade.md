# Upgrading Authentik

Authentik is pinned by `AUTHENTIK_VERSION` (ADR-017). Authentik cannot be
downgraded, and a release line must not be skipped (2026.8, then 2026.11, …), so the
only way back is the backup taken in step 1.

## Before

1. Read the release notes of the target version at
   `https://docs.goauthentik.io/releases/<version>/` for breaking changes and
   required actions.
2. Be on the latest patch of the current release line first.
3. Back up the Authentik database. Locally:

   ```bash
   docker compose --env-file .env exec -T database pg_dump -U shadow -Fc authentik > authentik-before-upgrade.dump
   ```

   Production backups of the Authentik database and the production env file are part
   of step 086B.

## Upgrade

1. Change `AUTHENTIK_VERSION` in `docker-compose.yml` and `.env.example` (and, once
   Authentik runs in production, `docker-compose.production.yml` and the production
   env contract), in the release that is deployed.
2. Local: `make dev-up`. The server and worker migrate the database on first start,
   then `authentik-config-init` reapplies the blueprints because the image version is part
   of the configuration fingerprint.

## Verify

- `docker compose --env-file .env ps -a` shows `authentik-server` and
  `authentik-worker` healthy and `authentik-config-init` exited (0).
- The admin interface shows the new version under Dashboard, Overview.
- `python3 scripts/verify-authentik-local.py` passes (discovery, providers, second
  factor, authorization code with PKCE).
- The sign-in page still has Shadow's look: a new Authentik version can rename the
  variables or parts that `authentik/blueprints/shadow-brand.css` uses.
- Sign in, sign out and recover an account.

## Roll back

Stop the stack, restore the dump into an empty `authentik` database, set
`AUTHENTIK_VERSION` back to the previous value, and start the stack. Changes made in
Authentik after the backup are lost.
