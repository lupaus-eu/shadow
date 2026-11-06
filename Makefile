# Local development shortcuts (docs/architecture/docker.md).
# Values come from .env; see .env.example for the 8100-8199 port range.

COMPOSE ?= docker compose
LIKEC4 ?= npx --yes likec4@1.59.4
DBML_CLI ?= npx --yes -p @dbml/cli@10.2.0 dbml2sql
STRIPE_WEBHOOK_URL ?= http://localhost:8100/api/v1/billing/stripe/webhook
STRIPE_EVENTS ?= checkout.session.completed,customer.subscription.updated,customer.subscription.deleted,customer.subscription.pending_update_applied,customer.subscription.pending_update_expired,invoice.paid,invoice.payment_failed

.PHONY: help up down restart ps logs test test-backend test-frontend check-ports stripe-listen models c4 dbml

help: ## List the targets
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F ':.*## ' '{printf "  %-15s %s\n", $$1, $$2}'

up: ## Build and start the local stack in the background
	$(COMPOSE) up -d --build
	@echo "Shadow: http://localhost:8173  API: http://localhost:8100  Authentik: http://localhost:8190"

down: ## Stop the local stack (data volumes are kept)
	$(COMPOSE) down

restart: down up ## Stop and start the local stack

ps: ## Show service status
	$(COMPOSE) ps

logs: ## Follow logs (make logs SERVICE=backend)
	$(COMPOSE) logs -f $(SERVICE)

test: test-backend test-frontend ## Run backend and frontend checks

test-backend: ## Run backend tests against the local test database
	cd backend && ../.venv/bin/python -m pytest -q

test-frontend: ## Typecheck, build, unit and browser tests
	npm --prefix frontend run typecheck
	npm --prefix frontend run build
	npm --prefix frontend run test:unit
	cd frontend && npx playwright test

check-ports: ## Verify Compose ports stay inside 8100-8199
	python3 scripts/check-compose-ports.py

models: ## Validate the C4 model and the DBML schema (docs/architecture/c4, dbml)
	$(LIKEC4) validate docs/architecture/c4
	cd backend && ../.venv/bin/python -m pytest -q tests/test_dbml_model.py
	cd "$$(mktemp -d)" && $(DBML_CLI) "$(CURDIR)/docs/architecture/dbml/shadow.dbml" --postgres -o schema.sql

c4: ## Browse the C4 views at http://localhost:8176
	$(LIKEC4) start --port 8176 docs/architecture/c4

dbml: ## Regenerate docs/architecture/dbml/shadow.dbml from the migrated test database
	cd backend && UPDATE_DBML=1 ../.venv/bin/python -m pytest -q tests/test_dbml_model.py

stripe-listen: ## Forward Stripe test-mode webhooks to the local backend
	@set -a; . ./.env; set +a; stripe listen --api-key "$$STRIPE_SECRET_KEY" --forward-to $(STRIPE_WEBHOOK_URL) --events $(STRIPE_EVENTS)
