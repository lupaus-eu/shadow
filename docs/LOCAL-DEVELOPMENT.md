# Local Development

Local development is `https://app.localhost`: loopback-only Caddy terminates a locally trusted certificate, proxies `/api` to FastAPI and proxies the Vite application (including HMR WebSockets) on every other path. Authentik is no longer part of the active runtime. This does not delete old Authentik Docker volumes, existing application data, or existing `(issuer, subject)` rows.

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
sudo install -m 0644 /path/to/ca.crt /usr/local/share/ca-certificates/schatten-local-app.crt
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
Vite and local Caddy. It never runs a reset, `down -v`, volume deletion or
provider mutation. The database port and ingress are bound only to loopback;
FastAPI and Vite have no host-published ports.

All local Compose commands load `.env` followed by `.env.entra.local`, including
database-only, preview and diagram commands: Compose validates the required
OIDC variables for the whole model. Run `make dev-init` once before these targets.

Open `https://app.localhost`. Caddy permits only the exact Host, discards browser-supplied forwarding headers and sends FastAPI a fixed HTTPS/Host plus a client IP only from its fixed peer address. FastAPI accepts that header only from the Caddy `/32` peer. The backend and Caddy both redact callback `code`, `state`, `error` and `error_description` values from access logs. Cookies are Secure, HttpOnly, host-only and preserve the existing SameSite and Path policy; unsafe requests still require exact Origin and CSRF checks.

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
