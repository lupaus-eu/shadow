SHELL := /bin/sh

.DEFAULT_GOAL := help

COMPOSE := docker compose --env-file .env
COMPOSE_LOCAL := $(COMPOSE) --env-file .env.entra.local
MIGRATE := uv run --env-file .env --project backend python backend/migrate.py up
SEED := $(COMPOSE_LOCAL) exec -T database sh -c 'psql -v ON_ERROR_STOP=1 -U "$$POSTGRES_USER" -d "$$POSTGRES_DB"' < db/init/002_seed_development_data.sql
LOCAL_INIT := if [ ! -f .env.entra.local ] || ! grep -q '^OIDC_CLIENT_SECRET=' .env.entra.local; then scripts/setup-local-entra.sh; fi; scripts/setup-local-app-tls.sh

.PHONY: \
	help \
	install backend-install frontend-install \
	check backend-check backend-lint backend-test backend-typecheck \
	frontend-check frontend-format frontend-format-check frontend-lint frontend-test frontend-build \
	dev-init db-up migrate seed dev-up dev-down preview-up \
	diagrams local-verify authentik-verify sign-in-verify authentik-apply provision-local-admin

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
		'  frontend-check      Run frontend format check, lint, tests, and build' \
		'  frontend-format     Format frontend files with Prettier' \
		'  frontend-format-check  Check frontend formatting with Prettier' \
		'' \
		'Local development (uses local Docker resources only):' \
		'  dev-init            Create missing private direct-Entra configuration and local TLS material' \
		'  db-up               Start the local application database' \
		'  migrate             Apply pending migrations (requires the local database)' \
		'  seed                Apply migrations and the dev seed (requires dev-init and database)' \
		'  dev-up              Initialize and start the full local development stack' \
		'  dev-down            Stop the local stack; retain volumes and data' \
		'  preview-up          Start the local frontend preview container' \
		'' \
		'Local verification:' \
		'  diagrams            Render the default PlantUML diagram' \
		'  local-verify        Verify local Caddy/direct-Entra Compose configuration' \
		'  authentik-verify    Verify the local Authentik setup (sign-in, MFA, tokens)' \
		'  sign-in-verify      Verify signing in to Shadow through Authentik end to end' \
		'  authentik-apply     Reapply the Authentik blueprints even if nothing changed' \
		'  provision-local-admin  Interactively pre-provision a designated local Entra admin' \
		'' \
		'Production, Entra, release, rollback, baseline, reset, and cleanup operations' \
		'are intentionally not available through this Makefile. Production server' \
		'commands are in deploy/Makefile, run on the host from the verified source copy:' \
		'  make -C /opt/apps/shadow-sources/<commit>/deploy help' \
		'See docs/runbooks/production.md.'

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

frontend-format:
	cd frontend && pnpm format

frontend-format-check:
	cd frontend && pnpm format:check

frontend-lint:
	cd frontend && pnpm lint

frontend-test:
	cd frontend && pnpm test

frontend-build:
	cd frontend && pnpm build

frontend-check: frontend-format-check frontend-lint frontend-test frontend-build

check: backend-check frontend-check

dev-init:
	@set -ex; \
	if [ ! -f .env ]; then cp .env.example .env; fi; \
	$(LOCAL_INIT)

db-up:
	$(COMPOSE_LOCAL) up -d database

migrate:
	$(MIGRATE)

seed:
	@set -ex; \
	$(MIGRATE); \
	$(SEED)

dev-up:
	@set -ex; \
	if [ ! -f .env ]; then cp .env.example .env; fi; \
	$(LOCAL_INIT); \
	$(COMPOSE_LOCAL) up -d database; \
	$(MIGRATE); \
	$(SEED); \
	$(COMPOSE_LOCAL) up -d prediction-worker mailpit authentik-server authentik-worker worker backend frontend local-caddy

dev-down:
	$(COMPOSE_LOCAL) down

preview-up:
	$(COMPOSE_LOCAL) --profile preview up frontend-preview

diagrams:
	$(COMPOSE_LOCAL) --profile docs build diagram-renderer
	$(COMPOSE_LOCAL) --profile docs run --rm diagram-renderer

authentik-apply:
	$(COMPOSE_LOCAL) run --rm -e AUTHENTIK_CONFIG_FORCE=true authentik-config-init

authentik-verify:
	python3 scripts/verify-authentik-local.py

sign-in-verify:
	python3 scripts/verify-local-sign-in.py

local-verify:
	scripts/verify-local-direct-entra-config.sh

provision-local-admin:
	cd backend && uv run --env-file ../.env --env-file ../.env.entra.local python -m app.provision_local_admin
