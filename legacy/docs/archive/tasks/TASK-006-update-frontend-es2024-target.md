# TASK-006 Update Frontend ES2024 Target

## Source Plan

Approved plan: update the frontend TypeScript app and node configuration targets from their current ES versions to ES2024.

The plan covers:

- `frontend/tsconfig.app.json`
- `frontend/tsconfig.node.json`

## Goal

Align the frontend TypeScript compiler target and library declarations on ES2024 for both browser application code and Node/Vite configuration code.

This keeps the frontend TypeScript configuration current while preserving the existing React, Vite, Vitest, ESLint and pnpm stack selected in ADR-001.

## Requirements

- Update `frontend/tsconfig.app.json` to use `ES2024` for `compilerOptions.target`.
- Update `frontend/tsconfig.app.json` to use `ES2024` in `compilerOptions.lib` while preserving `DOM` and `DOM.Iterable`.
- Update `frontend/tsconfig.node.json` to use `ES2024` for `compilerOptions.target`.
- Update `frontend/tsconfig.node.json` to use `ES2024` in `compilerOptions.lib`.
- Keep the existing module, module resolution, JSX, strictness and test-related settings unchanged unless validation proves a change is required.

## Acceptance Criteria

- [ ] `frontend/tsconfig.app.json` has `"target": "ES2024"`.
- [ ] `frontend/tsconfig.app.json` has `"lib": ["ES2024", "DOM", "DOM.Iterable"]`.
- [ ] `frontend/tsconfig.node.json` has `"target": "ES2024"`.
- [ ] `frontend/tsconfig.node.json` has `"lib": ["ES2024"]`.
- [ ] Frontend lint, tests and build pass.
- [ ] No new dependencies are added.
- [ ] No backend, database, authentication, deployment or architecture changes are introduced.

## Out Of Scope

- Updating to ES2025.
- Changing the project TypeScript version.
- Changing Vite, React, Vitest, ESLint or pnpm versions.
- Adding a new frontend typecheck script.
- Changing backend code or backend tooling.
- Changing database schema, migrations or seed data.
- Changing deployment or CI behavior.

## Implementation Notes

- This task is a small frontend configuration maintenance change.
- ADR-001 keeps React, TypeScript, Vite, pnpm, Vitest and ESLint as the frontend stack.
- TypeScript 5.9.3 supports `ES2024` as a valid `target` and `lib` value in this workspace.
- Do not add `build.target` to `frontend/vite.config.ts` unless the implementation explicitly needs bundled browser output to be pinned to ES2024. If that need appears, keep the change minimal and document why.
- No ADR is expected because this does not change the selected architecture or technology stack.

## Testing

Required:

- [x] Frontend tests
- [ ] Backend tests
- [ ] Integration tests
- [x] Manual verification
- [x] Lint
- [x] Build
- [ ] Typecheck

Not applicable:

- [x] Backend tests: no backend code changes.
- [x] Integration tests: no cross-service behavior changes.
- [x] Typecheck: frontend currently has no separate typecheck script; `pnpm build` runs `tsc -b`.

Commands:

```bash
cd frontend
pnpm lint
pnpm test
pnpm build
```

Manual verification:

- Inspect both TypeScript config files and confirm only the intended ES target/lib values changed.

## Documentation

No documentation updates are expected beyond this task file.

## Notes For AI Agent

- Lue `AGENTS.md`, `docs/architecture/overview.md`, `docs/adr/0001-tech-stack.md`, `docs/operations/testing.md` ja tämä task ennen toteutusta.
- Toteuta vain tämän taskin scope.
- Älä lisää uusia riippuvuuksia ilman hyväksyntää.
- Älä muuta arkkitehtuuria tai luo ADR:ää tätä muutosta varten, ellei toteutuksessa ilmene odottamaton arkkitehtuurivaikutus.
- Lisää testejä ei tarvita, koska muutos koskee vain TypeScript-konfiguraation target/lib-arvoja.
- Kerro lopuksi mitä muutit ja miten tarkistit työn.
