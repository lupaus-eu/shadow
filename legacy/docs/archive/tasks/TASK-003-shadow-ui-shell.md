# TASK-003 Shadow UI Shell

## Source Plan

This task comes from the developer-approved "Shadow UI Shell Plan".

The accepted plan creates the first Shadow frontend UI shell: a React/Vite app with an organisation start page, a workspace header, six tab routes, empty tab states, design tokens, and frontend tests.

## Goal

Build the initial Shadow frontend in `frontend/`.

The UI must provide organisation selection and creation at `/`, and a main workspace under `/shadow/:orgId/:tabSignature` after an organisation is selected.

## Requirements

- Scaffold React + TypeScript + Vite frontend using pnpm, ESLint, Vitest, and Testing Library.
- Add typed organisation API client for `GET /api/v1/organisations` and `POST /api/v1/organisations`.
- Add home page with load, empty, error, select, create, and open-organisation states.
- Add workspace layout with fixed header, app name, tab bar, and read-only organisation/scenario/org state indicators.
- Add six enabled tabs with exact signatures: `org-states`, `graph`, `events`, `metrics`, `summary`, `analysis`.
- Add consistent empty states for all tabs.
- Add separate design-token CSS file for palette, spacing, radius, shadow, motion, fonts, and type scale.

## Acceptance Criteria

- [ ] `/` renders organisation selection and creation UI.
- [ ] `/shadow/:orgId` redirects to `/shadow/:orgId/org-states`.
- [ ] All six tab links use the required URL signatures.
- [ ] Active tab is derived from the URL.
- [ ] Header shows `Shadow`, organisation, scenario `None`, and org state `None`.
- [ ] Frontend tests cover home page, redirect, tab URLs, active tab, and header indicators.
- [ ] `pnpm lint`, `pnpm test`, and `pnpm build` pass.

## Out Of Scope

- Backend endpoint implementation.
- Authentication and authorization.
- Real scenario, structure, event, metric, summary, or analysis content.
- Database schema or migrations.
- Docker/CI changes unless separately requested.

## Implementation Notes

- Keep the task scoped to `frontend/`.
- Store runtime organisation data only through the API contract, not hardcoded dummy data.
- Test mocks may define sample organisations inside tests.
- Browser `sessionStorage` may be used only as a display fallback for the selected organisation name.
- If the task is created after implementation, record it as the source-of-scope task for the existing frontend shell work rather than changing the implementation.

## Testing

Required:

- [ ] Frontend tests
- [ ] Manual verification
- [ ] Lint
- [ ] Build
- [ ] Typecheck via `pnpm build`

Not applicable:

- [ ] Backend tests: no backend code in scope.
- [ ] Integration tests: backend endpoints are contract-only in this task.
- [ ] Database tests: no schema or migration changes.

Commands:

```bash
cd frontend
pnpm lint
pnpm test
pnpm build
```

## Documentation

- Add `docs/archive/tasks/TASK-003-shadow-ui-shell.md`.
- No ADR is required because ADR-001 already decides the frontend stack.
- Update `README.md` or `docs/operations/local-development.md` only if the task also documents how to run the new frontend scaffold.

## Notes For AI Agent

- Lue `AGENTS.md`, `docs/architecture/overview.md`, `docs/adr/0001-tech-stack.md` ja tämä task ennen toteutusta.
- Toteuta vain tämän taskin scope.
- Älä lisää uusia riippuvuuksia ilman hyväksyntää.
- Lisää testit, kun muutos koskee sovelluskoodia.
- Jos et lisää testejä sovelluskoodin muutokselle, perustele miksi.
- Kerro lopuksi mitä muutit ja miten tarkistit työn.
