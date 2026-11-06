# TASK-014 Users And Organisations Backend CRUD

## Source Plan

Approved plan: implement thin FastAPI CRUD routes for users and organisations after the backend scaffold exists.

This task adds domain API structure and service-layer business logic for users and organisations.

## Goal

Implement backend CRUD operations for users and organisations using thin routes and separate service files.

Domain code should live under API version directories so later routes can be added consistently.

## Requirements

- Add separate domain directories under `backend/app/api/v1/`:
  - `users/`
  - `organisations/`
  - `org_states/`
  - `org_twin_structure/`
- Keep route handlers thin.
- Put business logic in separate service files.
- Implement users CRUD:
  - list
  - get
  - create
  - patch
  - soft delete
- Implement organisations CRUD:
  - list
  - get
  - create
  - patch
  - soft delete
- Use Pydantic classes that inherit `StrictBaseModel`.
- Use `Field` from Pydantic for class fields.
- Use SQLAlchemy for database reads/writes.
- Exclude soft-deleted rows from normal reads.
- Return frontend-compatible organisation DTOs.
- Reject duplicate active organisation names with HTTP 409.

## Acceptance Criteria

- [ ] Add separate domain directories under `backend/app/api/v1/`: `users/`, `organisations/`, `org_states/`, `org_twin_structure/`.
- [ ] Routes call services; business logic is not embedded in route handlers.
- [ ] Users CRUD supports list, get, create, patch, and soft delete.
- [ ] Organisations CRUD supports list, get, create, patch, and soft delete.
- [ ] Organisation API returns frontend-compatible `{ id, name }`, where `id` is the stable `organisation_key`.
- [ ] Organisation create rejects duplicate active names with HTTP 409.
- [ ] Soft-deleted rows are excluded from normal reads.
- [ ] No Entra ID authentication/authorization is added in this task; audit user columns remain nullable until auth exists.

## Out Of Scope

- Backend runtime scaffold.
- Schema changes.
- Scenario CRUD.
- Org state CRUD.
- Default organisation scenario/state creation.
- Metamodel copy behavior.
- Frontend changes.
- Authentication or authorization.

## Implementation Notes

- Depends on `TASK-012 Backend Runtime Scaffold`.
- Depends on `TASK-013 Core Schema And Domain Documentation Updates` if the duplicate-name check is database-enforced there.
- Read relevant backend scaffold docs and this task before implementation.
- Use stable text keys in external API paths/responses rather than exposing bigint primary keys.
- Keep audit user fields nullable until authentication exists.
- Generate stable organisation keys server-side.

## Testing

Required:

- [ ] Backend tests
- [ ] Integration tests
- [ ] Manual verification
- [ ] Lint
- [ ] Typecheck

Not applicable:

- [ ] Frontend tests: no frontend changes in this task.
- [ ] Build: no frontend build changes.

Commands:

```bash
cd backend
uv run ruff check .
uv run pytest
uv run pyright
```

Manual verification should cover:

- create/list/get/update/delete user
- create/list/get/update/delete organisation
- duplicate active organisation name returns 409
- soft-deleted records do not appear in list endpoints

## Documentation

Update backend API documentation or local development notes if endpoint usage or commands are documented.

## Notes For AI Agent

- Toteuta vain tämän taskin scope.
- Älä lisää scenario-, org state- tai metamodel-default behavioria tässä taskissa.
- Lisää testit muutoksen riskin mukaan.
- Kerro lopuksi mitä muutit ja miten tarkistit työn.
