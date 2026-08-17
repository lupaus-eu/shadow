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
- authentication: Microsoft Entra ID
- local runtime: frontend, backend ja database omissa Docker-konteissaan
- staging and production deployment: Coolify Docker Compose (ADR-003)

Frontendin voi ajaa Dockerissa:

```bash
docker compose up frontend
```

Frontend dev on saatavilla osoitteessa `http://localhost:5173`.

Backendin voi ajaa Dockerissa:

```bash
docker compose up backend
```

Backend on saatavilla osoitteessa `http://localhost:8000`.

Health endpoint:

```bash
curl --header 'Host: localhost:5173' http://localhost:8000/health
```

Käynnistä tietokanta ja aja kaikki puuttuvat migraatiot:

```bash
docker compose up -d database
uv run --project backend python backend/migrate.py up
```

Migraatiokäytännöt, rollback-komennot ja olemassa olevan tietokannan baseline
on kuvattu tiedostoissa `db/migrations/README.md` ja
`docs/LOCAL-DEVELOPMENT.md`.

Production-image, automaattinen release migration ja Coolify-konfiguraatio on
kuvattu tiedostossa `docs/DEPLOYMENT.md`. Deployment ajaa migraatiot erillisenä
jobina; backendin normaali startup ei muuta skeemaa.

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
