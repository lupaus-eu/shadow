# TASK-020 Remove Backend TestClient httpx Deprecation Warning

## Source Plan

Approved plan: remove the backend pytest warning raised by
`fastapi.testclient` / `starlette.testclient` by aligning the backend test
environment with Starlette's expected client dependency, while keeping the
current API test approach intact.

## Goal

Remove the current backend test warning:

`StarletteDeprecationWarning: Using httpx with starlette.testclient is deprecated; install httpx2 instead.`

The change should be limited to the backend test and development environment.
The current FastAPI application behavior and the existing `TestClient`-based API
tests should continue to work without a broader test-stack refactor.

## Requirements

- Add `httpx2>=2.0.0` to backend development dependencies.
- Update `backend/uv.lock` so the backend test environment resolves `httpx2`.
- Keep the existing `fastapi.testclient.TestClient` usage in backend tests.
- Do not refactor the API tests to async tests or a custom `httpx` client.
- Add a regression test that fails if importing `fastapi.testclient` emits the
  same deprecation warning again.
- Keep the change scoped to the backend test toolchain.
- Do not change backend API behavior, schemas, routes, or domain logic.
- Do not add unrelated dependency updates.

## Acceptance Criteria

- [ ] `backend/pyproject.toml` includes `httpx2` in backend development dependencies.
- [ ] `backend/uv.lock` resolves `httpx2` for the backend environment.
- [ ] Existing backend API tests still use `fastapi.testclient.TestClient`.
- [ ] A regression test exists for the deprecated import-warning path.
- [ ] `cd backend && uv run pytest -q` passes without the current `StarletteDeprecationWarning`.
- [ ] `cd backend && uv run ruff check .` passes.
- [ ] `cd backend && uv run pyright` passes.
- [ ] No backend runtime API behavior changes as part of this task.

## Out Of Scope

- Replacing `TestClient` with a different testing approach.
- Refactoring the backend test suite structure.
- Broad cleanup of `fastapi[standard]` or unrelated backend dependencies.
- Frontend changes.
- Database, migration, authentication, or authorization changes.
- CI workflow redesign.

## Implementation Notes

Read these before implementation:

```text
AGENTS.md
docs/architecture/overview.md
docs/adr/0001-tech-stack.md
docs/operations/testing.md
backend/pyproject.toml
backend/tests/test_users_organisations_api.py
```

Current observed behavior:

- `cd backend && uv run pytest -q` passes, but leaves one warning.
- The warning is triggered by importing `fastapi.testclient`, which re-exports
  `starlette.testclient.TestClient`.
- In the current resolved environment, Starlette prefers `httpx2` and warns when
  it falls back to `httpx`.

Expected implementation shape:

- Treat this as a minimal compatibility fix for the backend test environment.
- Prefer a small regression test that runs the import in a subprocess with
  warnings promoted to errors, so the task protects against the warning coming
  back later.
- Keep the test surface small and avoid changing endpoint tests unless required
  by the dependency update.

This task includes an approved backend development dependency addition:
`httpx2`.

No ADR is expected because this does not change the project architecture or
technology choices. It is a scoped test-environment compatibility fix.

## Testing

Required:

- [ ] Backend tests
- [ ] Integration tests
- [ ] Manual verification
- [ ] Lint
- [ ] Typecheck

Not applicable:

- [ ] Frontend tests: no frontend changes.
- [ ] Build: no production build behavior changes expected.

Commands:

```bash
cd backend
uv run ruff check .
uv run pytest -q
uv run pyright
```

Manual verification should confirm:

- the backend pytest run no longer shows the current `StarletteDeprecationWarning`
- the existing `TestClient`-based tests still pass after the dependency change

## Documentation

Update documentation only if needed for the implemented change.

Possible targets:

- `backend/README.md`
- `docs/operations/testing.md`

No documentation update is required if the existing commands and workflow remain
accurate.

## Notes For AI Agent

- Read `AGENTS.md` and `docs/architecture/overview.md` before implementation.
- Read the relevant ADR before changing backend tooling behavior.
- Implement only the scope defined in this task.
- Do not add unrelated dependencies or perform dependency upgrades outside this fix.
- Keep the current `TestClient` testing approach unless the task requirements force a smaller compatible adjustment.
- Add or update tests based on the regression risk.
- Report exactly what changed and which verification commands were run.
