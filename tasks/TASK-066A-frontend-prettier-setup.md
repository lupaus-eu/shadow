# TASK-066A Frontend Prettier Setup

## Source Plan

Developer-approved plan (2026-10-19) to set a maximum line width for frontend
TypeScript files. `frontend/src/features/predictions/PredictionsTab.tsx` and
other components have JSX lines that are hard to read; the longest is 2,898
characters (`PredictionsTab.tsx:731`). About 24,000 lines in `frontend/src` contain
539 lines longer than 100 characters, mostly in `PredictionsTab.tsx`,
`CustomersTab.tsx`, `SummaryTab.tsx` and their tests.

The frontend has no formatter and no line-length rule. The backend already
limits lines to 88 characters with Ruff (`backend/pyproject.toml`).

The developer approved:

- Prettier as a new frontend dev dependency, with a print width of 100
  characters. ESLint's `max-len` only reports long lines and cannot rewrap
  nested JSX.
- Two tasks: this task adds the tooling, and TASK-066B reformats the whole
  frontend in one mechanical commit and adds the CI check.
- No separate `max-len` lint rule for lines Prettier cannot break.

Amended 2026-10-19 before implementation: the developer extended the
formatter scope from `.ts`, `.tsx` and `.js` files to also cover the
frontend's CSS, HTML and JSON files.

Amended 2026-10-19 after the first AI review: the developer extended the
documentation updates to `ARCHITECTURE.md` and `docs/TESTING.md`, so every
tech-stack and tool list names Prettier.

## Goal

Add Prettier to the frontend with settings that match the current code style,
so TASK-066B changes mostly line wrapping and whitespace rather than code style. Record the decision in
the tech stack documentation. This task does not reformat existing code and
does not add the CI check, because the check would fail until TASK-066B.

## Requirements

### Dependency

- Add `prettier` to `frontend/package.json` `devDependencies` with an exact
  version (no `^` or `~`), the latest stable 3.x release that is at least two
  weeks old at implementation time. Prettier recommends exact versions
  because its output can change between releases.
- Update `frontend/pnpm-lock.yaml` with `pnpm add --save-dev --save-exact`.
- No other new dependencies. `eslint-config-prettier` is not needed, because
  the current ESLint presets (`@eslint/js` recommended, `typescript-eslint`
  recommended, React hooks and React refresh) contain no formatting rules.

### Configuration

- Add `frontend/.prettierrc.json`:

  ```json
  {
    "printWidth": 100,
    "semi": true,
    "singleQuote": false,
    "trailingComma": "none",
    "arrowParens": "always"
  }
  ```

  These match the existing code: double quotes, semicolons, no trailing
  commas and parenthesised arrow parameters. Keep Prettier's defaults for all
  other options.
- Add `frontend/.prettierignore` with at least `dist`, `.vite`, `.pnpm-store`
  and `node_modules`.
- Add these scripts to `frontend/package.json`:

  ```json
  "format": "prettier --write \"**/*.{ts,tsx,js,css,html,json}\"",
  "format:check": "prettier --check \"**/*.{ts,tsx,js,css,html,json}\""
  ```

  The pattern covers:

  - TypeScript and JavaScript: `src/`, `eslint.config.js`, `vite.config.ts`
    and `localCsp.test.ts`
  - CSS: `src/styles/*.css`
  - HTML: `index.html`
  - JSON: `package.json`, `tsconfig.json`, `tsconfig.app.json`,
    `tsconfig.node.json`, and `.prettierrc.json` itself

  YAML (including `pnpm-lock.yaml`) and Markdown are not formatted. Use an
  explicit extension list rather than `prettier .`, so new file types are not
  formatted without a decision.

### Editor Line Length

- Add a root `.editorconfig` that sets only line length:

  ```ini
  root = true

  [*.{ts,tsx,js,css,html,json}]
  max_line_length = 100

  [*.py]
  max_line_length = 88
  ```

  Prettier also reads `.editorconfig`; `.prettierrc.json` takes precedence and
  both set 100. Do not add indentation or newline settings, so other files and
  editors are unaffected.

### No Reformatting

- Do not run `pnpm format` on the existing code in a committed change. The
  only changes outside the new configuration files are `package.json`, the
  lockfile and the documentation listed below.
- Do not add `pnpm format:check` to CI or to the root `Makefile`. TASK-066B
  adds both after the reformat.

### Compatibility Check

Before committing, run a temporary full reformat to confirm that TASK-066B is
safe, then discard it:

1. Run `pnpm format` in `frontend/`.
2. Run `pnpm lint`, `pnpm test` and `pnpm build` on the formatted code.
3. Record the number of changed files and the diff size, both in total and
   per file type (TypeScript/JavaScript, CSS, HTML, JSON), and the number of
   lines still longer than 100 characters (see Testing).
4. Run `pnpm format` a second time and confirm it changes nothing.
5. Discard the reformat (commit this task's own changes first) and confirm
   `git status` is clean.

Report these results in the PR so TASK-066B has a size estimate.

## Acceptance Criteria

- [ ] `prettier` is an exact-version dev dependency, and `pnpm install
      --frozen-lockfile` succeeds.
- [ ] `.prettierrc.json`, `.prettierignore` and the `format` and
      `format:check` scripts exist as specified.
- [ ] The root `.editorconfig` sets `max_line_length` to 100 for
      `*.{ts,tsx,js,css,html,json}` and 88 for `*.py`, and nothing else.
- [ ] No existing `.ts`, `.tsx`, `.js`, `.css` or `.html` file is changed,
      and `package.json` changes only by the new dependency and scripts.
- [ ] CI and the root `Makefile` are unchanged.
- [ ] The temporary reformat passes lint, tests and build, a second
      `pnpm format` run changes nothing, and the PR reports its file count
      and diff size per file type and the remaining lines over 100
      characters.
- [ ] `pnpm lint`, `pnpm test` and `pnpm build` pass on the committed branch.
- [ ] The documentation below records Prettier as the frontend formatter.

## Out Of Scope

- Reformatting existing code (TASK-066B).
- The CI `format:check` step, `Makefile` targets and check-command
  documentation (TASK-066B).
- `.git-blame-ignore-revs` (TASK-066B).
- An ESLint `max-len` rule or `@stylistic` plugin. The developer decided not
  to add one.
- Formatting YAML or Markdown.
- Pre-commit hooks, `lint-staged` or editor format-on-save settings.
- Splitting large components such as `PredictionsWorkspace` into smaller
  ones. That needs its own task.
- Backend formatting changes.

## Implementation Notes

Read before implementation:

```text
AGENTS.md
ARCHITECTURE.md
docs/decisions/ADR-001-tech-stack.md
docs/TESTING.md
```

- Adding a dev-only tool is an amendment to ADR-001's tooling list, not a new
  architecture decision, so no new ADR is needed.
- The frontend source has no `eslint-disable`, `@ts-expect-error`,
  `@ts-ignore` or `prettier-ignore` comments, so rewrapping cannot move a
  line-specific directive away from its line.
- `frontend/Dockerfile` and `frontend/.dockerignore` need no change. The
  production image runs `pnpm build`, not Prettier.
- `localCsp.test.ts` hashes Vite's inline React-refresh preamble, not
  `index.html`, so formatting `index.html` does not affect the local CSP hash.
- Prettier formats `package.json` the same way as `JSON.stringify` with two
  spaces, which matches what pnpm writes, so later `pnpm add` runs keep it
  formatted.
- Prettier formats the `tsconfig*.json` files with its `json` parser, which
  keeps comments and never adds trailing commas, so they stay valid
  TypeScript configuration.

## Testing

Required:

- [ ] Lint
- [ ] Frontend tests
- [ ] Build
- [ ] Temporary reformat check described above

Not applicable:

- [ ] Backend tests and manual browser verification. Reason: tooling and
      documentation only; no application code changes.

```bash
cd frontend
pnpm install --frozen-lockfile
pnpm lint
pnpm test
pnpm build

# Temporary reformat check, with this task's changes committed first
pnpm format
pnpm lint && pnpm test && pnpm build
git diff --stat -- . | tail -1
for ext in ts tsx js css html json; do
  echo "$ext: $(git diff --shortstat -- "*.$ext")"
done
find . \( -name node_modules -o -name dist -o -name .pnpm-store \) -prune -o \
  -type f \( -name '*.ts' -o -name '*.tsx' -o -name '*.js' -o -name '*.css' \
  -o -name '*.html' -o -name '*.json' \) -print | xargs awk 'length > 100' | wc -l
git add -A -- .                # stage the first run
pnpm format
git diff --quiet -- . && echo "stable" || echo "second run changed files"
git reset -q -- . && git checkout -- .
git status --short             # expect no changes

cd ..
python3 scripts/ai_review_records.py validate
```

## Documentation

- `docs/decisions/ADR-001-tech-stack.md`: add `Frontend formatting: Prettier,
  print width 100 (TASK-066A)` to the Decision list after `Frontend linting:
  ESLint`, and add Prettier to the list of CI tools in Consequences.
- `AGENTS.md`, `ARCHITECTURE.md` and `README.md`: add Prettier to the
  frontend line in the tech stack (`React, TypeScript, Vite, pnpm, Vitest,
  ESLint, Prettier`). In `ARCHITECTURE.md`, also add `Prettier` after
  `ESLint` in the Frontend section's technology list.
- `docs/TESTING.md`: add `frontend formatting: Prettier` after `frontend
  linting: ESLint` in the list of tools decided in ADR-001.
- Do not add `pnpm format:check` to command lists yet. TASK-066B does that
  together with the CI step.

## Notes For AI Agent

- Use the branch `chore/TASK-066A-frontend-prettier-setup`.
- Save the redacted Step 13 review record under `docs/ai-reviews/TASK-066A/`.
- Report all changed files, the Prettier version, every verification command
  run and the temporary reformat results.
- If the temporary reformat breaks lint, tests or build, or if a second run
  is not stable, stop and report it instead of changing the configuration
  outside this specification.
