FROM docker.io/library/python:3.12-slim@sha256:b18b261e1b4974b4f321451ad5251ded85abb22c2b8b262da527dda1d031ab30 AS base

COPY --from=ghcr.io/astral-sh/uv:0.13.4@sha256:9f130421e930bfbdc563c00740466603f8723158e90297d07957c2294640262b /uv /uvx /usr/local/bin/

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
COPY db/init/001_seed_reference_data.sql db/init/metamodel_state_##default##.json /workspace/db/init/

ENV PATH="/workspace/backend/.venv/bin:${PATH}"
ENV PYTHONPATH="/workspace/backend"
ENV PYTHONDONTWRITEBYTECODE="1"

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=5 \
    CMD ["python", "-c", "import os, urllib.parse, urllib.request; origin=os.environ['PUBLIC_ORIGIN']; host=urllib.parse.urlsplit(origin).netloc; request=urllib.request.Request('http://127.0.0.1:8000/health', headers={'Host': host}); urllib.request.urlopen(request, timeout=2).read()"]

USER 10001:10001

CMD ["fastapi", "run", "app/main.py", "--host", "0.0.0.0", "--port", "8000"]
