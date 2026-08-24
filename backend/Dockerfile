FROM python:3.12-slim AS base

COPY --from=ghcr.io/astral-sh/uv:0.11.24 /uv /uvx /usr/local/bin/

FROM base AS dev

WORKDIR /app

COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen

COPY --chmod=755 backend/docker-entrypoint-dev.sh /usr/local/bin/schatten-backend-dev
COPY backend/ .

EXPOSE 8000
CMD ["/usr/local/bin/schatten-backend-dev"]

FROM base AS production

WORKDIR /workspace/backend

RUN groupadd --gid 10001 schatten \
    && useradd --uid 10001 --gid 10001 --create-home --shell /usr/sbin/nologin schatten

COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev

COPY backend/app/ ./app/
COPY backend/migrate.py ./migrate.py
COPY db/migrations/ /workspace/db/migrations/

ENV PATH="/workspace/backend/.venv/bin:${PATH}"
ENV PYTHONPATH="/workspace/backend"
ENV PYTHONDONTWRITEBYTECODE="1"

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=5 \
    CMD ["python", "-c", "import os, urllib.parse, urllib.request; origin=os.environ['PUBLIC_ORIGIN']; host=urllib.parse.urlsplit(origin).netloc; request=urllib.request.Request('http://127.0.0.1:8000/health', headers={'Host': host}); urllib.request.urlopen(request, timeout=2).read()"]

USER 10001:10001

CMD ["fastapi", "run", "app/main.py", "--host", "0.0.0.0", "--port", "8000"]
