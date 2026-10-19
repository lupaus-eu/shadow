# TASK-066B Frontend Prettier Format And CI Check

## Source Plan

Developer-approved plan (2026-10-19) to set a maximum line width for frontend
TypeScript files; see `tasks/TASK-066A-frontend-prettier-setup.md` for the
background. TASK-066A adds Prettier with a print width of 100, the `format`
and `format:check` scripts and the documentation of the tool, without changing
existing code.

The developer approved:

- Reformatting the whole frontend in one mechanical commit, rather than one
  directory at a time.
- Adding the CI `format:check` step in this task, after the reformat, so CI
  never fails on unformatted code.
- No separate `max-len` lint rule for lines Prettier cannot break.

Amended 2026-10-19 before implementation: the developer extended the
formatter scope to also cover the frontend's CSS, HTML and JSON files.

## Goal

Format every frontend `.ts`, `.tsx`, `.js`, `.css`, `.html` and `.json` file
covered by the TASK-066A scripts, and make CI fail on unformatted files from
then on. Long JSX
lines such as `PredictionsTab.tsx:731` (2,898 characters) are wrapped to at
most 100 characters wherever Prettier can break them.

## Requirements

### Prerequisite

- TASK-066A is merged to `main`. Start this branch from the latest `main`.

### Reformat

- Run `pnpm format` in `frontend/` and commit only its output as one commit,
  for example `style(frontend): format with Prettier`. No hand edits, renames
  or other changes in that commit.
- The reformat covers TypeScript, JavaScript, `src/styles/*.css`,
  `index.html`, `package.json` and the `tsconfig*.json` files, as defined by
  the TASK-066A scripts.
- Make the CI, `Makefile` and documentation changes below in a separate,
  later commit, so the reformat commit can be checked on its own.
- Do not change `.prettierrc.json`, `.prettierignore` or the Prettier version.
  If the output is unacceptable, stop and report it instead of changing the
  configuration.
- Just before opening the PR and before each later push, rebase on
  `origin/main`. Then run `pnpm format` again so code merged meanwhile is also
  formatted. Resolve conflicts by taking the incoming code and re-running
  `pnpm format`, never by formatting by hand.

### CI Check

- In `.github/workflows/ci.yml`, job `frontend-checks`, add a step after
  "Install frontend dependencies" and before "Lint frontend":

  ```yaml
      - name: Check frontend formatting
        working-directory: frontend
        run: pnpm format:check
  ```

- No other CI changes.

### Makefile

- In the root `Makefile`, add:
  - `frontend-format`: `cd frontend && pnpm format`
  - `frontend-format-check`: `cd frontend && pnpm format:check`
- Add `frontend-format-check` as the first dependency of `frontend-check`, and
  list both new targets in `make help` in the same style as the existing
  frontend targets.

### Git Blame

The repository uses squash merges, so the reformat commit's SHA on `main` is
only known after this PR is merged. Ignoring it in `git blame` is therefore a
follow-up after merging:

- After the developer squash-merges this PR, open a small follow-up PR,
  `chore/TASK-066B-blame-ignore-revs`, that adds a root
  `.git-blame-ignore-revs` file containing the squash commit's full SHA with a
  comment line naming TASK-066B.
- GitHub reads this file automatically. Document the local opt-in
  `git config blame.ignoreRevsFile .git-blame-ignore-revs` in
  `CONTRIBUTING.md` in the same follow-up PR.
- The squash commit also contains this task's CI, `Makefile` and
  documentation lines; it's acceptable that `git blame` skips them too.

## Acceptance Criteria

- [ ] The reformat commit contains only `pnpm format` output. Checking it out
      and running `pnpm format` again changes nothing.
- [ ] `pnpm format:check` passes on the branch head after the final rebase.
- [ ] `PredictionsTab.tsx` and every other formatted file have no lines
      longer than 100 characters, except for lines Prettier cannot break
      (long string literals, template literals, `className` strings, long
      CSS values and comments). The PR lists the remaining count by file.
- [ ] No behaviour change: `pnpm lint`, `pnpm test` and `pnpm build` pass,
      and no test is changed except for formatting.
- [ ] The built CSS and `index.html` in `dist/` are compared before and after
      the reformat, and the PR reports any difference with its cause.
- [ ] The local app renders as before in a quick visual check of the main
      tabs, including Predictions.
- [ ] The CI `frontend-checks` job runs `pnpm format:check` before lint and
      passes on the PR.
- [ ] `make frontend-check` runs the format check, and `make help` lists
      `frontend-format` and `frontend-format-check`.
- [ ] The documentation below lists `pnpm format:check` with the frontend
      checks.
- [ ] After merge, the follow-up PR adds the squash commit to
      `.git-blame-ignore-revs` and documents the local Git setting.

## Out Of Scope

- Changing the Prettier configuration, version or file patterns from
  TASK-066A.
- Breaking lines that Prettier leaves long, by hand or with an ESLint
  `max-len` rule. The developer decided not to add such a rule.
- Formatting YAML or Markdown.
- Pre-commit hooks, `lint-staged` or editor format-on-save settings.
- Splitting large components such as `PredictionsWorkspace`, or any other
  structural refactoring. That needs its own task, so the structural diff
  stays separate from this whitespace diff.
- Updating the check commands in existing task files under `tasks/`; they
  record the work as it was done.

## Implementation Notes

Read before implementation:

```text
AGENTS.md
ARCHITECTURE.md
docs/decisions/ADR-001-tech-stack.md
docs/TESTING.md
tasks/TASK-066A-frontend-prettier-setup.md
```

- TASK-066A's PR reports the expected size of the reformat. The diff will be
  far larger than the recommended 500 reviewable lines. The developer accepted
  this for a generated diff; the review checks that the reformat commit is
  pure formatter output and reviews the separate CI, `Makefile` and
  documentation commit normally.
- Open frontend branches will conflict with this change. Merge it when few
  frontend branches are open. After it is merged, those branches rebase onto
  `main` and run `pnpm format`.
- Count the remaining lines over 100 characters with:

  ```bash
  cd frontend
  find . \( -name node_modules -o -name dist -o -name .pnpm-store \) -prune -o \
    -type f \( -name '*.ts' -o -name '*.tsx' -o -name '*.js' -o -name '*.css' \
    -o -name '*.html' -o -name '*.json' \) -print \
    | xargs awk 'length > 100 { n[FILENAME]++ } END { for (f in n) print n[f], f }' \
    | sort -rn
  ```

- CSS and HTML formatting only changes whitespace, line breaks and quote
  style, so the minified build output should be the same. Compare it to
  catch an unexpected change:

  ```bash
  cd frontend
  git checkout <commit before the reformat>
  pnpm build && cp -r dist ../../dist-before   # outside the repository
  git checkout <reformat commit>
  pnpm build
  diff <(cat ../../dist-before/assets/*.css) <(cat dist/assets/*.css)
  diff ../../dist-before/index.html dist/index.html
  ```

  `dist/index.html` names hashed asset files, so a JavaScript change from JSX
  whitespace can change those names without being a CSS or HTML difference.
  JavaScript output is not compared, because Prettier can rewrite JSX
  whitespace in forms that compile differently but render the same. Delete
  the copied directory afterwards.

## Testing

Required:

- [ ] Lint
- [ ] Frontend tests
- [ ] Build
- [ ] Format check
- [ ] Manual verification: CI runs the format check step on the PR, and the
      local app renders as before (see Acceptance Criteria).

Not applicable:

- [ ] Backend tests. Reason: formatting-only change to frontend files; no
      backend change.

```bash
cd frontend
pnpm install --frozen-lockfile
pnpm format:check
pnpm lint
pnpm test
pnpm build

# Reformat commit is pure formatter output
git checkout <reformat commit>
pnpm format && git diff --quiet && echo "pure formatter output"
git checkout -

cd ..
make frontend-check
python3 scripts/ai_review_records.py validate
```

## Documentation

Add `pnpm format:check` before `pnpm lint` in the frontend check commands of:

- `docs/AI-DEVELOPMENT-WORKFLOW.md` (step 8, and add `Format check` before
  `Lint` in the step 12 minimum CI pipeline)
- `docs/TESTING.md` (general frontend command blocks only, not the
  feature-specific ones that list a test subset)
- `CONTRIBUTING.md`
- `AI-FIRST-ENGINEERING-HANDBOOK.md`
- `docs/decisions/ADR-001-tech-stack.md` (the expected commands block)
- `tasks/TASK-TEMPLATE.md` and `.github/PULL_REQUEST_TEMPLATE.md` (add a
  `Format check` checkbox to the Testing lists)

Also add one sentence to `docs/TESTING.md` or `CONTRIBUTING.md`: run
`pnpm format` (or `make frontend-format`) before committing frontend changes;
CI rejects unformatted `.ts`, `.tsx`, `.js`, `.css`, `.html` and `.json` files
in `frontend/`.

## Notes For AI Agent

- Use the branch `chore/TASK-066B-frontend-prettier-format`.
- Save the redacted Step 13 review record under `docs/ai-reviews/TASK-066B/`.
  Review the CI, `Makefile` and documentation commit normally. For the
  reformat commit, record the purity check and its result instead of
  reviewing it line by line.
- Report all changed files outside `frontend/src`, the diff size of the
  reformat commit per file type, the build output comparison, every verification command run and the remaining lines
  over 100 characters by file.
- Do not open the `.git-blame-ignore-revs` follow-up PR until the developer
  has merged this PR.
