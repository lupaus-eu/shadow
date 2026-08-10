# Schatten Backend

FastAPI backend scaffold for Schatten.

## Development

```bash
uv sync
uv run fastapi dev app/main.py
```

Health check:

```bash
curl http://localhost:8000/health
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
