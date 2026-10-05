# TASK-060 Update Node 24 Setup Actions

## Source Plan

Developer-approved CI maintenance. PR CI warns that `actions/setup-python@v5`
and `astral-sh/setup-uv@v6` target the deprecated Node.js 20 runtime and are
forced onto Node.js 24.

## Goal

Update `.github/workflows/ci.yml` to `actions/setup-python@v6` and
`astral-sh/setup-uv@v7`, which run on `node24`, without changing CI behavior.

## Requirements

- Change `uses: actions/setup-python@v5` to `uses: actions/setup-python@v6`.
- Change `uses: astral-sh/setup-uv@v6` to `uses: astral-sh/setup-uv@v7`.
- Keep the existing inputs: `python-version-file: backend/.python-version`,
  `enable-cache: true`, `cache-dependency-glob: backend/uv.lock`.
- No new jobs, caching, permissions or dependency changes. No ADR.

## Acceptance Criteria

- [ ] No `actions/setup-python@v5` or `astral-sh/setup-uv@v6` remain in `.github/workflows/`.
- [ ] `backend-checks` installs the same Python version and uv dependencies and passes.
- [ ] PR CI no longer emits the Node.js 20 deprecation warning for these actions.

## Out Of Scope

- Other actions (`actions/checkout@v5` and `actions/setup-node@v5` already run on Node 24).
- Application code, Python or uv version changes.

## Testing

Not applicable: frontend/backend tests (no application code change).

Documentation-free CI change: verify through the PR's CI run and confirm the
warning is gone from the `backend-checks` annotations.

## Documentation

No documentation describes the setup action versions; no documentation change.
