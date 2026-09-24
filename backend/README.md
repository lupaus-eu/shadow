# Schatten Backend

FastAPI backend scaffold for Schatten.

## Development

```bash
uv sync
uv run fastapi dev app/main.py
```

The API fails closed outside tests unless the OIDC relying-party settings are
present. Copy the non-secret names from `.env.example` and inject the client
secret through the local environment or deployment secret store. Local
development uses direct Entra with `OIDC_REQUIRE_VERIFIED_EMAIL=false`; the
reviewed workforce flow uses the email claim only for guarded first-link
discovery.

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
DATABASE_URL=postgresql://user:password@database:5432/schatten \
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
DATABASE_URL=postgresql://user:password@database:5432/schatten \
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
docker build --target production -t schatten-backend:local -f backend/Dockerfile .
```

The default command runs the production API. The same image provides the
one-shot release migration command. Both run as numeric user/group
`10001:10001`:

```bash
docker run --rm \
  -e DATABASE_URL=postgresql://user:password@database:5432/schatten \
  schatten-backend:local python migrate.py up
```

Deployment policy and secret-safe operator commands are documented in
`docs/DEPLOYMENT.md`.

## Verification

```bash
uv run ruff check .
uv run pytest
uv run pyright
```
