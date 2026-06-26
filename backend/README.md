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

## Verification

```bash
uv run ruff check .
uv run pytest
uv run pyright
```
