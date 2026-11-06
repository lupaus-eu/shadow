# Upgrading Authentik

Authentik is pinned by `AUTHENTIK_VERSION` (ADR-0010, ADR-0036). Authentik cannot be
downgraded, and a release line must not be skipped (2026.5, then 2026.8, then 2026.11),
so the only way back is the backup taken in step 1.

## Before

1. Read the release notes of the target version at
   `https://docs.goauthentik.io/releases/<version>/` for breaking changes and
   required actions.
2. Be on the latest patch of the current release line first.
3. Back up the Authentik database. On the production host run `make backup`
   (`backup.md`); locally:

   ```bash
   docker compose exec -T db pg_dump -U authentik -Fc authentik > authentik-before-upgrade.dump
   ```

## Upgrade

1. Change `AUTHENTIK_VERSION` in `docker-compose.yml`, `docker-compose.prod.yml`,
   `.env.example`, and `.env.production.example`, in the release that is deployed.
   Local and production `.env` files that set `AUTHENTIK_VERSION` need the same change.
2. Production: `make deploy`. Local: `make up`. The server and worker migrate the
   database on first start, then `authentik-config-init` reapplies the blueprints
   because the image changed.

## Verify

- `make ps` (production) or `docker compose ps -a` shows `authentik-server` and
  `authentik-worker` healthy and `authentik-config-init` exited (0).
- The admin interface shows the new version under Dashboard, Overview.
- Discovery reports the public HTTPS issuer when asked the way the backend asks:

  ```bash
  docker compose exec -T backend python -c "import urllib.request,json;r=urllib.request.Request('http://authentik-server:9000/application/o/yearclock/.well-known/openid-configuration',headers={'Host':'<identity host>','X-Forwarded-Proto':'https'});print(json.load(urllib.request.urlopen(r))['issuer'])"
  ```

  The output must start with `https://`. If it starts with `http://`, the connecting
  address is not in `AUTHENTIK_TRUSTED_PROXY_CIDRS`.
- The sign-in page still has the application's look (canvas background, teal button, no photograph): a new
  Authentik version can rename the variables or parts that `authentik/blueprints/yearclock-brand.css` uses.
- Sign in, sign out, and recover an account (`production-readiness.md`, section 2).

## Roll back

Stop the stack, restore the dump into an empty `authentik` database
(`scripts/ops/restore-drill.sh` shows the procedure), set `AUTHENTIK_VERSION` back to
the previous value, and start the stack. Changes made in Authentik after the backup
are lost.
