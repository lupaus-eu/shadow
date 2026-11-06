# Shadow Backend

FastAPI backend scaffold for Shadow.

## Development

```bash
uv sync
uv run fastapi dev app/main.py
```

The API fails closed outside tests unless the OIDC relying-party settings are
present. Copy the non-secret names from `.env.example` and inject the client
secret through the local environment or deployment secret store. Local
development uses the local Authentik provider
(issuer `https://id.app.localhost/application/o/shadow/`, fixed in
`docker-compose.yml`). The issuer must be an Authentik per-provider issuer
`https://<identity host>/application/o/<slug>/`; discovery is the issuer plus
`.well-known/openid-configuration`, and `OIDC_INTERNAL_BASE_URL` optionally
names the Docker-internal address of Authentik. `OIDC_REQUIRE_VERIFIED_EMAIL`
defaults to true; the email claim is used only for guarded first-link
discovery and sign-in never creates an account.

`PUBLIC_ORIGIN` determines the one accepted Host, callback URL and local
redirect base. `APP_ALLOWED_ORIGIN` is the exact Origin accepted by unsafe
requests and the sole credentialed CORS origin in development. Production must
use HTTPS, Secure cookies and explicit trusted Caddy peer CIDRs.

Health check through local Caddy:

```bash
curl --cacert /path/printed/by/setup-local-app-tls.sh/ca.crt \
  https://app.localhost/health
```

## Prediction Worker

The durable prediction supervisor is a standalone backend module and is never
started by FastAPI:

```bash
DATABASE_URL=postgresql://user:password@database:5432/shadow \
  uv run python -m app.api.v1.predictions.worker
```

It requires only `DATABASE_URL`; OIDC credentials are not required. Exactly one
instance obtains the global PostgreSQL advisory lock and calculates work. A
second instance exits nonzero without claiming a request. Runtime service
wiring is provided by the local and release Compose manifests as the distinct,
internal `prediction-worker` service.

The process health-check command returns zero only while another live database
session owns the worker lock:

```bash
DATABASE_URL=postgresql://user:password@database:5432/shadow \
  uv run python -m app.api.v1.predictions.worker health-check
```

Compose gives this service its own health check, automatic restart, an init
process and a ten-second stop grace so the supervisor can terminate and reap an
active calculation child. The service publishes no port and receives no OIDC,
session or public-origin settings.

## Production Image

Build the provider-neutral production image from the repository root so it can
include both backend code and repository migrations:

```bash
docker build --target production -t shadow-backend:local -f backend/Dockerfile .
```

The default command runs the production API. The same image provides the
one-shot release migration command, explicit reference-data seed and interactive
first-administrator bootstrap. All run as numeric user/group `10001:10001`:

```bash
docker run --rm \
  -e DATABASE_URL=postgresql://user:password@database:5432/shadow \
  shadow-backend:local python migrate.py up

docker run --rm \
  -e DATABASE_URL=postgresql://user:password@database:5432/shadow \
  --workdir /tmp \
  shadow-backend:local python -m app.seed_reference_data

docker run --rm --interactive --tty \
  --env DATABASE_URL \
  --workdir /tmp \
  shadow-backend:local python -m app.bootstrap_admin
```

Run the seed only after migrations. It needs only `DATABASE_URL`, inserts the
approved default metamodel without Users or business records, and reports a
successful no-op when an active default already exists. It resolves its packaged
SQL/JSON independently of the working directory and does not initialize FastAPI
or OIDC configuration.

Run the bootstrap only after migrations and the reference seed, from a private
operator terminal with session recording and screen sharing disabled. It prompts
for the designated administrator's display name and designated administrator email; never
place either value in command arguments or repository records. The command
creates one active fixed-role `admin` with null bootstrap audit actors only when
the entire `users` table is empty, including soft-deleted rows. Any existing User
causes a nonzero refusal without mutation. It creates no identity or session;
the administrator's first Authentik sign-in links to that account by verified email using normal guarded identity
linking. Manage every later User through the authenticated Users UI/API.

Deployment policy and secret-safe operator commands are documented in
`docs/architecture/deployment.md`.

## Verification

```bash
uv run ruff check .
uv run pytest
uv run pyright
```
