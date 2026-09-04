SHELL := /bin/sh

.DEFAULT_GOAL := help

COMPOSE := docker compose --env-file .env
COMPOSE_LOCAL := $(COMPOSE) --env-file .env.authentik.local
MIGRATE := uv run --env-file .env --project backend python backend/migrate.py up
SEED := $(COMPOSE_LOCAL) exec -T database sh -c 'psql -v ON_ERROR_STOP=1 -U "$$POSTGRES_USER" -d "$$POSTGRES_DB"' < db/init/002_seed_development_data.sql
AUTHENTIK_INIT := if [ ! -f .env.authentik.local ]; then scripts/setup-local-authentik.sh; else scripts/setup-local-authentik-tls.sh; fi

.PHONY: \
	help \
	install backend-install frontend-install \
	check backend-check backend-lint backend-test backend-typecheck \
	frontend-check frontend-lint frontend-test frontend-build \
	dev-init db-up migrate seed dev-up dev-down preview-up \
	diagrams auth-smoke auth-verify

help:
	@printf '%s\n' \
		'Usage: make <target>' \
		'' \
		'Installation (explicit; checks do not install dependencies):' \
		'  install             Install backend and frontend dependencies' \
		'  backend-install     Run uv sync in backend/' \
		'  frontend-install    Run pnpm install --frozen-lockfile in frontend/' \
		'' \
		'Validation:' \
		'  check               Run all backend and frontend checks' \
		'  backend-check       Run backend lint, tests, and typecheck' \
		'  frontend-check      Run frontend lint, tests, and build' \
		'' \
		'Local development (uses local Docker resources only):' \
		'  dev-init            Create missing local configuration; reuse existing Authentik secrets' \
		'  db-up               Start the local application database' \
		'  migrate             Apply pending migrations (requires the local database)' \
		'  seed                Apply migrations and the dev seed (requires dev-init and database)' \
		'  dev-up              Initialize and start the full local development stack' \
		'  dev-down            Stop the local stack; retain volumes and data' \
		'  preview-up          Start the local frontend preview container' \
		'' \
		'Local verification:' \
		'  diagrams            Render the default PlantUML diagram' \
		'  auth-smoke          Run the local Authentik discovery/JWKS smoke' \
		'  auth-verify         Verify local Authentik and Compose configuration' \
		'' \
		'Production, Entra, release, rollback, baseline, reset, and cleanup operations' \
		'are intentionally not available through Make. See the documented direct commands.'

backend-install:
	cd backend && uv sync

frontend-install:
	cd frontend && pnpm install --frozen-lockfile

install: backend-install frontend-install

backend-lint:
	cd backend && uv run ruff check .

backend-test:
	cd backend && uv run pytest

backend-typecheck:
	cd backend && uv run pyright

backend-check: backend-lint backend-test backend-typecheck

frontend-lint:
	cd frontend && pnpm lint

frontend-test:
	cd frontend && pnpm test

frontend-build:
	cd frontend && pnpm build

frontend-check: frontend-lint frontend-test frontend-build

check: backend-check frontend-check

dev-init:
	@set -ex; \
	if [ ! -f .env ]; then cp .env.example .env; fi; \
	$(AUTHENTIK_INIT)

db-up:
	$(COMPOSE) up -d database

migrate:
	$(MIGRATE)

seed:
	@set -ex; \
	$(MIGRATE); \
	$(SEED)

dev-up:
	@set -ex; \
	if [ ! -f .env ]; then cp .env.example .env; fi; \
	$(AUTHENTIK_INIT); \
	$(COMPOSE_LOCAL) up -d database authentik-database authentik-server authentik-worker authentik-tls; \
	$(MIGRATE); \
	$(SEED); \
	$(COMPOSE_LOCAL) up -d

dev-down:
	$(COMPOSE_LOCAL) down

preview-up:
	$(COMPOSE) --profile preview up frontend-preview

diagrams:
	$(COMPOSE) --profile docs build diagram-renderer
	$(COMPOSE) --profile docs run --rm diagram-renderer

auth-smoke:
	scripts/smoke-local-authentik.sh

auth-verify:
	scripts/verify-local-authentik-config.sh
