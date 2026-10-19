# ADR-001: Tech Stack

Status: Accepted

Date: 2026-06-18

---

# Context

Schatten-projekti on bootstrap-vaiheessa ja tarvitsee sitovan teknologiapäätöksen ennen sovellusrungon, paikallisen kehitysympäristön, CI:n ja ensimmäisten feature-taskien toteutusta.

Päätöksen pitää antaa AI-agenteille selkeä oletus siitä, mihin hakemistoihin frontend, backend ja tietokanta kuuluvat sekä millä työkaluilla kehitys, testaus ja deployment aloitetaan.

---

# Decision

Projektin teknologiapino on:

- Frontend: React, TypeScript, Vite
- Frontend package manager: pnpm
- Frontend test framework: Vitest
- Frontend linting: ESLint
- Frontend formatting: Prettier, print width 100 (TASK-066A)
- Frontend hakemisto: `./frontend`
- Backend: Python, FastAPI
- Backend validation and schemas: Pydantic
- Backend package ja tool runner: uv
- Backend unit tests: pytest
- Backend type checking: pyright
- Backend linting: Ruff
- Backend hakemisto: `./backend`
- Database: PostgreSQL
- ORM: SQLAlchemy
- Authentication: Microsoft Entra ID
- Local runtime: Docker containers
- Deployment: Railway initial stagingiin; deployment target voi muuttua myöhemmin

Frontend, backend ja tietokanta ajetaan kukin omassa Docker-kontissaan.

---

# Options Considered

Harkitut tai WIP-dokumenteissa mainitut vaihtoehdot:

- Next.js / React / TypeScript
- React / TypeScript / Vite
- Node.js / TypeScript backend
- Python / FastAPI backend
- Pydantic
- PostgreSQL
- Drizzle ORM
- SQLAlchemy
- ESLint
- Ruff
- Docker
- GitHub Actions
- Railway stagingiin
- UpCloud tai Scaleway myöhempään tuotantoon

---

# Consequences

Tämä päätös mahdollistaa:

- frontend- ja backend-työn erottamisen selkeisiin hakemistoihin
- paikallisen kehitysympäristön rakentamisen Docker Composella
- CI-putken rakentamisen pnpm-, uv-, pytest-, pyright-, Vitest-, Vite-, ESLint-, Prettier- ja Ruff-komentojen ympärille
- PostgreSQL- ja SQLAlchemy-pohjaisen tietokantakerroksen suunnittelun
- FastAPI- ja Pydantic-pohjaisen API-validoinnin suunnittelun
- Entra ID -autentikoinnin suunnittelun backendin luotettavan authorization-kerroksen kanssa

Rajoitteet:

- Frontend ei saa ohittaa backendin authorization- tai validointilogiikkaa.
- Backend on järjestelmän luotettava sovelluskerros.
- SQLAlchemy on ORM-päätös, mutta migraatiotyökalu päätetään erikseen.
- Railway on alkuvaiheen staging-päätös eikä lukitse pysyvää production-hostingia.

Dokumentoitavat komennot täsmentyvät, kun `frontend/` ja `backend/` alustetaan. Odotettu perusmuoto on:

```bash
cd frontend
pnpm lint
pnpm test
pnpm build

cd backend
uv run ruff check .
uv run pytest
uv run pyright
```

---

# Follow-Up

- Päivitä `ARCHITECTURE.md`.
- Päivitä `AGENTS.md`.
- Päivitä `docs/LOCAL-DEVELOPMENT.md`.
- Päivitä `docs/TESTING.md`.
- Päivitä CI-putki, kun sovellusrungot on alustettu.
- Luo tarvittaessa erilliset ADR:t migraatiotyökalusta, autentikoinnin tarkasta token/session-mallista ja production deploymentista.
