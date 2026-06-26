# TASK-012 Backend Runtime Scaffold

## Source Plan

Approved plan: create the first FastAPI backend runtime scaffold for Schatten before implementing domain CRUD behavior.

This task covers backend project setup, a health endpoint, strict Pydantic base models, database connection/session plumbing, Docker runtime wiring, basic tests and documentation updates.

## Goal

Add a runnable `backend/` application using the stack selected in ADR-001.

The backend must be ready for later domain tasks to add API routers and database-backed business logic without redefining project structure.

## Requirements

- Add a `backend/` Python project managed by `uv`.
- Use FastAPI for the application runtime.
- Use Pydantic for schemas and validation.
- Use SQLAlchemy for database engine/session setup.
- Use pytest for backend tests.
- Use pyright for backend type checking.
- Use Ruff for backend linting.
- Add a FastAPI health endpoint at `/health`.
- Add `StrictBaseModel`, a Pydantic `BaseModel` subclass with:
  - `ConfigDict(extra="forbid", populate_by_name=True)`
- Ensure Pydantic request/response classes inherit `StrictBaseModel` and use `Field`.
- Add database configuration that reads `DATABASE_URL`.
- Add database engine/session dependency wiring without implementing domain CRUD.
- Add a Docker Compose backend service connected to the local database.
- Keep frontend, backend and database as separate Docker services.
- Update documentation for backend setup, runtime and verification commands.

## Acceptance Criteria

- [ ] `backend/` contains a runnable FastAPI app with `/health`.
- [ ] `StrictBaseModel` exists and sets `ConfigDict(extra="forbid", populate_by_name=True)`.
- [ ] Pydantic request/response classes inherit `StrictBaseModel` and use `Field`.
- [ ] Database session/engine config reads `DATABASE_URL`.
- [ ] Docker Compose has backend service connected to database.
- [ ] Frontend dev proxy can target backend container.
- [ ] `docs/LOCAL-DEVELOPMENT.md`, `README.md`, and CI docs reflect backend commands.

## Out Of Scope

- Users CRUD.
- Organisations CRUD.
- Scenario or org state API behavior.
- Metamodel copy behavior.
- Schema migrations.
- Authentication or authorization.
- Microsoft Entra ID integration.
- Production deployment.
- Choosing a migration framework.

## Implementation Notes

- Read `AGENTS.md`, `ARCHITECTURE.md`, `docs/decisions/ADR-001-tech-stack.md`, `docs/TESTING.md`, `docs/LOCAL-DEVELOPMENT.md` and this task before implementation.
- Keep route handlers thin from the beginning.
- Keep the initial route surface limited to `/health`.
- Do not add new backend dependencies outside the ADR-001 backend stack without approval.
- Prefer a simple app package structure that later domain tasks can extend under `backend/app/`.
- The database connection may be configured and testable without requiring the database to be available during unit tests.
- If Docker runtime or CI commands require backend package install commands, document them.

## Testing

Required:

- [ ] Backend tests
- [ ] Manual verification
- [ ] Lint
- [ ] Typecheck

Not applicable:

- [ ] Frontend tests: no frontend application behavior changes expected.
- [ ] Integration tests: no domain API or database read/write behavior yet.
- [ ] Build: no backend production image build required unless added by implementation.

Commands:

```bash
cd backend
uv run ruff check .
uv run pytest
uv run pyright
```

Manual verification:

```bash
docker compose up backend
curl http://localhost:8000/health
```

## Documentation

Update:

- `README.md`
- `docs/LOCAL-DEVELOPMENT.md`
- `docs/TESTING.md`, if backend command guidance changes
- `.github/workflows/ci.yml`, if CI baseline is expanded for backend checks
- `.env.example`, if backend-specific environment variables are added or clarified

No ADR is required because ADR-001 already selects the backend technology stack.

## Notes For AI Agent

- Lue `AGENTS.md`, `ARCHITECTURE.md`, `docs/decisions/ADR-001-tech-stack.md`, `docs/TESTING.md`, `docs/LOCAL-DEVELOPMENT.md` ja tämä task ennen toteutusta.
- Toteuta vain tämän taskin scope.
- Älä lisää uusia riippuvuuksia ilman hyväksyntää.
- Lisää testit, kun muutos koskee sovelluskoodia.
- Jos toteutus vaatii arkkitehtuurimuutoksen, pysähdy ja ehdota ADR:ää ennen koodausta.
- Kerro lopuksi mitä muutit ja miten tarkistit työn.
