# Schatten Backend

FastAPI backend scaffold for Schatten.

## Development

```bash
uv sync
uv run fastapi dev app/main.py
```

The API fails closed outside tests unless the OIDC relying-party settings are
present. Copy the non-secret names from `.env.example` and inject the client
secret through the local environment or deployment secret store. Authentik and
Entra use the same settings; Authentik additionally sets
`OIDC_REQUIRE_VERIFIED_EMAIL=true`, while the reviewed Entra workforce flow may
set it to `false` for guarded first-link discovery.

`PUBLIC_ORIGIN` determines the one accepted Host, callback URL and local
redirect base. `APP_ALLOWED_ORIGIN` is the exact Origin accepted by unsafe
requests and the sole credentialed CORS origin in development. Production must
use HTTPS, Secure cookies and explicit trusted Caddy peer CIDRs.

Health check:

```bash
curl --header 'Host: app.localhost:5173' http://localhost:8000/health
```

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
