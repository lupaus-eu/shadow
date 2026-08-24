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
- authentication: backend-managed OIDC session; local Authentik, optional local
  Authentik-to-Entra federation and direct single-tenant Microsoft Entra ID in
  production
- local runtime: frontend, backend, application database and local-only
  Authentik in Docker contexts
- production-only deployment: one HTTPS origin through the frontend/Caddy
  service in Coolify Docker Compose (ADR-003/ADR-005)

Frontendin voi ajaa Dockerissa:

```bash
docker compose up frontend
```

Frontend dev on saatavilla osoitteessa `http://app.localhost:5173`.

Backendin voi ajaa Dockerissa:

```bash
scripts/setup-local-authentik.sh
docker compose --env-file .env --env-file .env.authentik.local up backend
```

Ensimmäinen setup luo myös gitignored local CA:n Authentikin HTTPS-osoitteelle
`https://auth.localhost:9443`. CA pitää luottaa hostilla ennen browser-testausta;
tarkat trust- ja optional Entra federation -ohjeet ovat
`docs/LOCAL-DEVELOPMENT.md`:ssä.

Backend on saatavilla osoitteessa `http://localhost:8000`.

Health endpoint:

```bash
curl --header 'Host: app.localhost:5173' http://localhost:8000/health
```

Käynnistä tietokanta ja aja kaikki puuttuvat migraatiot:

```bash
docker compose up -d database
uv run --env-file .env --project backend python backend/migrate.py up
```

Migraatiokäytännöt, rollback-komennot ja olemassa olevan tietokannan baseline
on kuvattu tiedostoissa `db/migrations/README.md` ja
`docs/LOCAL-DEVELOPMENT.md`.

Production frontend/backend images, automatic release migration, required
Entra/Coolify configuration, backup/approval gates, limited production smoke
and rollback workflow are documented in `docs/DEPLOYMENT.md`. Local and
production evidence uses `docs/qa/AUTHENTICATION-QA-CHECKLIST.md`. Deployment
runs migrations as a separate job; normal backend startup does not mutate the
schema. These instructions do not authorize a production deployment, Entra
resource change, tag operation, backup or restore.

Buildatun frontendin preview:

```bash
docker compose --profile preview up frontend-preview
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
