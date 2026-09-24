# schatten

Varjo:n inkarnaatio

Schatten on AI-first ohjelmistoprojekti.

## Aloita tästä

Päivittäisessä työssä riittää yleensä:

1. `AGENTS.md`
2. `CONTRIBUTING.md`
3. relevantti `tasks/TASK-*.md`

Käytännön lukupolku:

- `README.md`: miten aloitan
- `CONTRIBUTING.md`: miten teen työn
- `docs/AI-DEVELOPMENT-WORKFLOW.md`: tarkempi prosessi tarvittaessa
- `tasks/TASK-*.md`: mitä oikeasti tehdään
- `AI-FIRST-ENGINEERING-HANDBOOK.md`: taustalla oleva käsikirja, jota ei tarvitse lukea joka kerta kokonaan

Lue lisäksi tarpeen mukaan:

- `ARCHITECTURE.md`, kun muutos koskee rakennetta tai järjestelmän osia
- `docs/domains/DOMAIN.md`, kun muutos koskee domainia tai datan omistajuutta
- `docs/concepts/CONCEPTS.md`, kun muutos koskee liiketoimintakäsitettä
- `docs/data/DATA-MODEL.md`, kun muutos koskee dataa tai tietokantaa
- `docs/TESTING.md`, kun muutos koskee sovelluskoodia tai testejä
- `docs/DEPLOYMENT.md`, kun muutos koskee imageä, migraatiojobia tai deploymentia
- `docs/AI-DEVELOPMENT-WORKFLOW.md`, kun haluat tarkemman workflow-ohjeen
- `AI-FIRST-ENGINEERING-HANDBOOK.md`, kun tarvitset koko projektin kehityskäsikirjan

## DEV ympäristön setup

```bash
git clone git@github.com:reflector-oy/schatten.git
cd schatten
cp .env.example .env
```

Jos repository on jo alustettu paikallisesti:

```bash
git remote add origin git@github.com:reflector-oy/schatten.git
git pull origin main
cp .env.example .env
```

Teknologiapino on päätetty tiedostossa `docs/decisions/ADR-001-tech-stack.md`.

Päätetty rakenne:

- frontend: React, TypeScript, Vite, pnpm, Vitest, ESLint hakemistossa `frontend/`
- backend: Python, FastAPI, Pydantic, uv, pytest, pyright, Ruff hakemistossa `backend/`
- database: PostgreSQL
- ORM: SQLAlchemy
- authentication target: backend-managed direct single-tenant Entra in development
  and production, sharing the existing registration with separate secrets
- local target: HTTPS Caddy -> Vite/FastAPI, application database and one worker
- production target: UpCloud Ubuntu 26.04 LTS with Docker/Compose, direct Caddy
  TLS and private PostgreSQL 18 in Docker; daily encrypted on-server backups
  in `/opt/postgres-backups` with 7-day retention required for initial release

[ADR-013](docs/decisions/ADR-013-shared-entra-local-https-deployment.md) records
the accepted amendment. TASK-059B implements the local HTTPS/direct-Entra
runtime; the existing production adapter remains until G. Seed/bootstrap,
integrated QA and rollout are pending C/D/E/F/G.
Volumes are not backups; release requires completed backup identifiers and
successful restore-rehearsal evidence. Backup setup remains pending G/E/F.

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

`make dev-up` creates a missing `.env`, privately collects missing direct-Entra
configuration into ignored `.env.entra.local`, and validates or creates local
application TLS without overwriting valid material. It then starts the local
prerequisites, applies migrations and the idempotent development seed, and
starts Caddy, API, prediction worker and Vite against the ready schema. It uses
local Docker resources only. Production, provider mutation, release, rollback,
baseline, reset and destructive cleanup operations are intentionally not
available through Make.

Frontendin voi ajaa Dockerissa:

```bash
docker compose --env-file .env --env-file .env.entra.local up frontend local-caddy
```

Frontend dev on saatavilla osoitteessa `https://app.localhost`.

Backendin voi ajaa Dockerissa:

```bash
make dev-init
docker compose --env-file .env --env-file .env.entra.local up backend local-caddy
```

Ensimmäinen setup luo myös gitignored local CA:n sovelluksen HTTPS-osoitteelle
`https://app.localhost`. CA pitää luottaa hostilla ennen browser-testausta;
tarkat trust-, direct-Entra- ja local-admin-ohjeet ovat
`docs/LOCAL-DEVELOPMENT.md`:ssä.

FastAPIlla ei ole host-published porttia; Caddy reitittää API:n osoitteessa
`https://app.localhost/api`.

Prediction worker käynnistyy full-stack-komennon mukana erillisenä
`prediction-worker`-palveluna. Sillä ei ole julkaistua porttia eikä OIDC-
asetuksia. Sen tila näkyy komennolla
`docker compose --env-file .env --env-file .env.entra.local ps prediction-worker`; tarkemmat käyttö- ja QA-ohjeet ovat
`docs/LOCAL-DEVELOPMENT.md`:ssä ja
`docs/qa/PREDICTION-WORKER-RUNTIME-QA.md`:ssä.

Health endpoint:

```bash
curl --cacert /path/printed/by/setup-local-app-tls.sh/ca.crt \
  https://app.localhost/health
```

Käynnistä tietokanta ja aja kaikki puuttuvat migraatiot:

```bash
docker compose --env-file .env --env-file .env.entra.local up -d database
uv run --env-file .env --project backend python backend/migrate.py up
```

Migraatiokäytännöt, rollback-komennot ja olemassa olevan tietokannan baseline
on kuvattu tiedostoissa `db/migrations/README.md` ja
`docs/LOCAL-DEVELOPMENT.md`.

Production frontend/backend images, the same-backend-image prediction worker,
automatic release migration, required
direct-Entra/UpCloud configuration, manual approval gates, limited production smoke
and rollback workflow are documented in `docs/DEPLOYMENT.md`. Local and
production evidence uses `docs/qa/AUTHENTICATION-QA-CHECKLIST.md`. Deployment
runs migrations as a separate job; normal backend startup does not mutate the
schema. These instructions do not authorize a production deployment, Entra
resource change, tag operation, backup or restore.

Buildatun frontendin preview:

```bash
docker compose --env-file .env --env-file .env.entra.local --profile preview up frontend-preview
```

Preview on saatavilla osoitteessa `http://localhost:4173`.

Backendin oletustarkistukset:

```bash
cd backend
uv run ruff check .
uv run pytest
uv run pyright
```

## Kehitysworkflow

```text
Idea -> AI Implementation Plan -> Developer Approval -> Task(s) -> Branch -> AI Implementation -> Review -> Pull Request -> Developer Merge
```

Katso tarkempi ohje:

- `CONTRIBUTING.md`
- `docs/AI-DEVELOPMENT-WORKFLOW.md`
