# shadow

Varjo:n inkarnaatio

Shadow on AI-first ohjelmistoprojekti.

## Aloita tästä

- [`AGENTS.md`](AGENTS.md): agenttien ohjeet ja säännöt
- [`CONTEXT.md`](CONTEXT.md): käsitteet ja sanasto
- [`FEATURE_WORKFLOW.md`](FEATURE_WORKFLOW.md): miten featuret speksataan
  (`.scratch/`: PRD → domain model → technical design → ticketit) ja toteutetaan
- [`docs/architecture/`](docs/architecture/README.md): järjestelmän dokumentaatio
  (yleiskuvaus, teknologiapino, deployment, domainit, käsitteet, datamalli, kaaviot)
- [`docs/adr/`](docs/adr/README.md): arkkitehtuuripäätökset
- [`docs/operations/`](docs/operations/README.md) ja [`docs/runbooks/`](docs/runbooks/README.md):
  paikallinen kehitys, testaus, QA ja tuotannon ajo
- [`docs/agents/`](docs/agents/): agenttityön ohjeet (definition of done, testaus, reititys)
- [`docs/archive/`](docs/archive/README.md): vanhat `tasks/`-taskit ja prosessidokumentit

## DEV ympäristön setup

```bash
git clone git@github.com:lupaus-eu/shadow.git
cd shadow
cp .env.example .env
```

Jos repository on jo alustettu paikallisesti:

```bash
git remote add origin git@github.com:lupaus-eu/shadow.git
git pull origin main
cp .env.example .env
```

Teknologiapino on päätetty tiedostossa `docs/adr/0001-tech-stack.md`.

Päätetty rakenne:

- frontend: React, TypeScript, Vite, pnpm, Vitest, ESLint, Prettier hakemistossa `frontend/`
- backend: Python, FastAPI, Pydantic, uv, pytest, pyright, Ruff hakemistossa `backend/`
- database: PostgreSQL
- ORM: SQLAlchemy
- authentication target: self-hosted Authentik as the identity provider, with
  backend-managed OIDC sign-in ([ADR-017](docs/adr/0017-use-self-hosted-authentik-for-identity.md));
  production identity is introduced by the SaaS plan
- local target: HTTPS Caddy -> Vite/FastAPI, application database and one worker
- production target: UpCloud Ubuntu 26.04 LTS with Docker/Compose, direct Caddy
  TLS and private PostgreSQL 18 in Docker; daily encrypted on-server backups
  in `/opt/postgres-backups` with 7-day retention required for initial release

[ADR-013](docs/adr/0013-shared-entra-local-https-deployment.md) records
the accepted amendment (its identity provider part is superseded by ADR-017).
TASK-059B implements the local HTTPS
runtime, TASK-059C implements the non-user reference seed and TASK-059D
implements the empty-users-table administrator bootstrap. TASK-059G implements
the production runtime (`docker-compose.production.yml`) and the operator
build/release, backup, restore and scheduler tooling in `deploy/`. TASK-059E
provides the integrated operator runbook
([docs/runbooks/production.md](docs/runbooks/production.md)) and disposable QA.
TASK-059H1-H3 replace the host Git checkout with a manual "Deploy to
production" GitHub Action, a manifest-verified receive and server `make`
commands in `deploy/Makefile`; there is no Git on the server. TASK-059F
performed the authorized setup and first production rollout (`v0.1.0`; see
[docs/operations/qa/FIRST-PRODUCTION-ROLLOUT.md](docs/operations/qa/FIRST-PRODUCTION-ROLLOUT.md)).
Volumes are not backups; release requires completed backup identifiers and
successful restore-rehearsal evidence. F activated the production backups on
2026-10-02.

## Optional Make Convenience

Repository root contains an optional Make interface for common local developer
workflows. It requires GNU Make, Docker Compose, uv and pnpm to be installed;
it does not install system tools or replace the direct commands documented
below.

```bash
make help
make install
make check
make dev-up
make dev-down
```

`make dev-up` creates a missing `.env` from `.env.example` and validates or
creates local TLS material for `app.localhost` and `id.app.localhost` without
overwriting valid material. It then starts PostgreSQL, applies migrations and
the idempotent development seed, and starts the backend, frontend, prediction
worker, platform worker, Mailpit, Authentik and Caddy against the ready schema. It uses
local Docker resources only. Production, provider mutation, release, rollback,
baseline, reset and destructive cleanup operations are intentionally not
available through the root Makefile; production server commands live in
`deploy/Makefile` and run on the host (see the runbook).

Frontendin voi ajaa Dockerissa:

```bash
docker compose --env-file .env up frontend local-caddy
```

Frontend dev on saatavilla osoitteessa `https://app.localhost`.

Backendin voi ajaa Dockerissa:

```bash
make dev-init
docker compose --env-file .env up backend local-caddy
```

Ensimmäinen setup luo myös gitignored local CA:n sovelluksen HTTPS-osoitteelle
`https://app.localhost` ja Authentikin osoitteelle `https://id.app.localhost`. CA pitää luottaa hostilla ennen browser-testausta;
tarkat trust- ja kirjautumisohjeet ovat
`docs/operations/local-development.md`:ssä.

FastAPIlla ei ole host-published porttia; Caddy reitittää API:n osoitteessa
`https://app.localhost/api`.

Prediction worker käynnistyy full-stack-komennon mukana erillisenä
`prediction-worker`-palveluna. Sillä ei ole julkaistua porttia eikä OIDC-
asetuksia. Sen tila näkyy komennolla
`docker compose --env-file .env ps prediction-worker`; tarkemmat käyttö- ja QA-ohjeet ovat
`docs/operations/local-development.md`:ssä ja
`docs/operations/qa/PREDICTION-WORKER-RUNTIME-QA.md`:ssä.

Health endpoint:

```bash
curl --cacert /path/printed/by/setup-local-app-tls.sh/ca.crt \
  https://app.localhost/health
```

Käynnistä tietokanta ja aja kaikki puuttuvat migraatiot:

```bash
docker compose --env-file .env up -d database
uv run --env-file .env --project backend python backend/migrate.py up
```

Migraatiokäytännöt, rollback-komennot ja olemassa olevan tietokannan baseline
on kuvattu tiedostoissa `db/migrations/README.md` ja
`docs/operations/local-development.md`.

Production frontend/backend images, the same-backend-image prediction worker,
automatic release migration, required
UpCloud configuration, manual approval gates, limited production smoke
and rollback workflow are documented in `docs/architecture/deployment.md`. Local and
production evidence uses `docs/operations/qa/AUTHENTICATION-QA-CHECKLIST.md`. Deployment
runs migrations as a separate job; normal backend startup does not mutate the
schema. These instructions do not authorize a production deployment, identity
provider change, tag operation, backup or restore.

Buildatun frontendin preview:

```bash
docker compose --env-file .env --profile preview up frontend-preview
```

Preview on saatavilla osoitteessa `http://localhost:4173`.

Backendin oletustarkistukset:

```bash
cd backend
uv run ruff check .
uv run pytest
uv run pyright
```

## Connect an AI client

Shadow itself never calls an LLM: you chat in your own MCP client on your
own AI subscription, and the client proposes changes as change sets that a
person applies or rejects in the Metrics tab or, with
`MCP_CHANGE_SET_REVIEW_ENABLED`, in the chat by approving the client's apply
or reject call ([ADR-015](docs/adr/0015-ai-via-mcp.md)). The feature
is behind `MCP_ENABLED` (off by default); when it is on, the Metrics tab's AI panel
Connect section shows these steps for the current Shadow. Production has
had it on, with the change-set review, since 2026-11-03 (`v0.2.0`;
[runbook section 14](docs/runbooks/production.md#14-ai-via-mcp-enable-disable-offboarding-and-incidents));
local and production evidence is in [the QA checklist](docs/operations/qa/AI-MCP-QA-CHECKLIST.md).

Shadow has one MCP server, `https://shadow.lupaus.eu/api/mcp`, which you
connect and authorize once; the tools it lists depend on your role.

- Claude Code: install the Shadow plugin, which adds the Shadow MCP server
  `https://shadow.lupaus.eu/api/mcp` and the Shadow skills (needs read
  access to this repository):

  ```text
  /plugin marketplace add lupaus-eu/shadow
  /plugin install shadow@shadow
  ```

  Then run `/mcp`, select the Shadow server, authenticate and approve the
  access in Shadow. Keep `apply_change_set` and `reject_change_set` on
  "ask": in auto mode, or once these tools are allowed without asking, Claude
  Code applies and rejects without asking you.
  Reconnect with `/mcp` after a Shadow release that changes tool results.
- claude.ai and Claude Desktop: add the URL as one custom connector
  (Settings, Connectors), and upload the two skill zips from the Connect
  section under Customize, Skills (code execution must be on).
- Other MCP clients: add the URL and use the MCP prompts `model_building` and
  `timeseries_generation`, which carry the same skill text. The client's
  OAuth callback must be on the redirect URI allowlist
  (`MCP_OAUTH_REDIRECT_URIS`); by default only the claude.ai and claude.com
  callbacks and `http://localhost:{port}/callback` are allowed.

Before TASK-074 (ADR-015 amendment of 2026-11-03) Shadow had separate read
and write servers. After the release that brings TASK-074 to production,
remove the two old connectors (or the old plugin servers) and add the one
above, download the skill zips again and replace the uploaded skills, and
update the Claude Code plugin to version 0.3.0.

The skills live in `backend/app/mcp/plugin/skills/`. Local use against
`https://app.localhost` is described in
[docs/operations/local-development.md](docs/operations/local-development.md).

## Kehitysworkflow

```text
Idea -> PRD (.scratch) -> grillaus ja hyväksyntä -> domain model -> technical design -> ticketit
     -> AI-toteutus ticket kerrallaan -> AI review -> human review -> merge -> hyväksytty julkaisu
```

Katso [`FEATURE_WORKFLOW.md`](FEATURE_WORKFLOW.md) ja [`CONTRIBUTING.md`](CONTRIBUTING.md).
