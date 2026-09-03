# TASK-048 Frontend Route Code Splitting

## Source Plan

This task comes from the developer-approved plan for fixing Vite's production
build warning about JavaScript chunks larger than 500 kB.

The measured baseline is a single 881.06 kB minified JavaScript bundle
(266.60 kB gzip). The source map identifies Cytoscape as the largest individual
contributor, and `frontend/src/pages/Workspace.tsx` currently imports every
implemented workspace tab statically. The accepted plan uses route-level and
workspace-tab-level `React.lazy()`/dynamic `import()` boundaries as the primary
fix, with `Suspense` loading UI. A narrow Rollup `manualChunks` rule may be added
only if the measured lazy-loaded build still contains an oversized chunk.

## Goal

Reduce the JavaScript required for the initial Schatten frontend load and
remove Vite's chunk-size warning by loading workspace pages and implemented
workspace tabs only when their routes are rendered.

Keep existing URLs, authentication and authorization behavior, workspace
selection state, tab gating, and feature behavior unchanged while providing
accessible loading and failure states for deferred route code.

## Requirements

- Lazy-load the workspace page from `frontend/src/App.tsx` with a module-scope
  `React.lazy(() => import(...))` declaration.
- Lazy-load every implemented workspace tab from
  `frontend/src/pages/Workspace.tsx` with module-scope `React.lazy()`
  declarations:
  - Scenarios
  - Structure
  - Events
  - Metrics
  - Summary
  - Predictions
  - Customers
  - Users
- Add `Suspense` boundaries at the page-route and workspace-content loading
  seams. Keep the authenticated shell and workspace header/navigation visible
  while only the selected workspace tab is loading.
- Provide a lightweight, accessible loading fallback for deferred page and tab
  code.
- Add a route-level error boundary with a clear reload action for rejected
  dynamic imports. Do not expose sensitive error details in the UI.
- Preserve all current route paths, redirects, component props, selection
  prerequisites, admin-only Users behavior, and API behavior.
- Measure the production build after adding dynamic imports. Add
  `build.rollupOptions.output.manualChunks` only if an emitted chunk remains
  oversized or Cytoscape remains combined with unrelated route code.
- If manual chunking is required, use the smallest explicit package rule needed,
  such as a dedicated `cytoscape`/graph-vendor chunk. Do not create a blanket
  chunk for every `node_modules` dependency.
- Do not increase `build.chunkSizeWarningLimit` to hide the warning.
- Do not add new dependencies.

## Acceptance Criteria

- [ ] The production build emits separate asynchronous chunks for the workspace
      page and implemented workspace tabs instead of one application-wide
      JavaScript bundle.
- [ ] The initial entry path does not statically include workspace feature code.
- [ ] Cytoscape is not downloaded for Home, Login, Scenarios, or other
      non-Structure routes and is requested when the Structure route is opened.
- [ ] `pnpm build` completes without Vite's "Some chunks are larger than 500 kB"
      warning, and every emitted minified JavaScript chunk is below the configured
      500 kB warning threshold.
- [ ] The existing Home, Login, workspace default redirect, direct tab URLs,
      selection gating, and consultant/admin Users behavior remain unchanged.
- [ ] Page and tab chunk loading display an accessible loading state without
      unnecessarily replacing the persistent workspace shell.
- [ ] A rejected lazy import displays a non-sensitive error state with a working
      reload action.
- [ ] Frontend tests cover the changed asynchronous routing behavior, loading
      UI, and chunk-load failure UI.
- [ ] `pnpm lint`, `pnpm test`, and `pnpm build` pass.

## Out Of Scope

- Changing route URLs, navigation labels, authentication, authorization, or
  workspace selection behavior.
- Refactoring feature internals or API clients beyond changes required for lazy
  route loading.
- Changing frontend dependencies or package versions.
- Raising or disabling Vite's chunk-size warning.
- Adding speculative prefetching, service-worker caching, or broad bundle-budget
  infrastructure.
- Backend, database, deployment topology, domain model, concept model, or
  architecture changes.

## Implementation Notes

Primary files expected to change:

- `frontend/src/App.tsx`
- `frontend/src/pages/Workspace.tsx`
- `frontend/src/App.test.tsx`
- a small reusable loading/error-boundary component and its test, if clearer
  than keeping those elements alongside the routes
- `frontend/src/styles/*.css` only if the loading or error state needs styling
- `frontend/vite.config.ts` only if the measured post-lazy-load build still
  requires explicit manual chunking

Declare lazy components at module scope so React retains component identity.
The imported feature modules already provide default component exports suitable
for `React.lazy()`.

Use two meaningful `Suspense` seams instead of placing a boundary around every
component:

1. authenticated page-route content for the lazy Workspace page
2. workspace content for the selected lazy tab

`Suspense` in this task covers deferred component code. Existing feature data
loading performed in effects continues to use the features' existing loading
and error states.

After implementing lazy routes, inspect the normal `pnpm build` output before
editing Vite configuration. If Cytoscape still causes the Structure chunk to
exceed the limit, isolate only that package with an explicit manual chunk. A
broad `node_modules` vendor rule could pull Cytoscape into a shared eager chunk
and defeat the intended route boundary.

No ADR is required because this task uses the React and Vite stack already
accepted by ADR-001 and does not change a system architecture boundary.

References:

- `ARCHITECTURE.md`
- `docs/decisions/ADR-001-tech-stack.md`
- `docs/TESTING.md`
- [React `lazy`](https://react.dev/reference/react/lazy)
- [React `Suspense`](https://react.dev/reference/react/Suspense)
- [Rollup `output.manualChunks`](https://rollupjs.org/configuration-options/#output-manualchunks)

## Testing

Required:

- [ ] Frontend unit/component tests
- [ ] Manual browser verification
- [ ] Lint
- [ ] Build
- [ ] Typecheck through `pnpm build`

Not applicable:

- [ ] Backend tests: no backend code or API contract changes are in scope.
- [ ] Integration tests: no external integration boundary changes are in scope.
- [ ] Database tests: no schema or migration changes are in scope.

Automated tests must retain the existing direct-route, redirect, tab-gating,
and role-aware navigation coverage. Update asynchronous assertions where lazy
module resolution makes rendering asynchronous. Add focused coverage for the
route loading fallback and lazy-import error boundary without weakening the
existing feature assertions.

Commands:

```bash
cd frontend
pnpm lint
pnpm test
pnpm build
```

Manual verification in browser developer tools:

1. Open Home/Login and confirm workspace and Cytoscape chunks are not requested.
2. Open the Scenarios route and confirm the Structure/Cytoscape chunks are not
   requested.
3. Navigate to Structure and confirm its deferred code and Cytoscape are
   requested at that point.
4. Navigate away and back to Structure and confirm the loaded chunks are reused.
5. Exercise direct URLs and the consultant/admin Users route behavior.

Record the before/after minified and gzip sizes from the Vite build output in
the implementation summary or PR.

## Documentation

- Add this task specification as the permanent scope source.
- No architecture, domain, concept, data, database, deployment, or diagram
  documentation changes are expected.
- Update general frontend documentation only if implementation changes a
  documented command or runtime behavior; no such change is currently planned.

## Notes For AI Agent

- Read `AGENTS.md`, this task, `ARCHITECTURE.md`,
  `docs/decisions/ADR-001-tech-stack.md`, and `docs/TESTING.md` before
  implementation.
- Implement only the scope defined in this task.
- Do not add dependencies or change package versions.
- Apply route-level lazy loading and measure the build before considering
  `manualChunks`.
- Do not silence the warning by changing `chunkSizeWarningLimit`.
- Preserve authentication, authorization, workspace selection, and route
  behavior.
- Add or update tests for application-code changes.
- Report exact before/after bundle sizes and every verification command run.
