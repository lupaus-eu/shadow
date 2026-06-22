# TASK-004 Update Checkout Action

## Source Plan

This task comes from the developer-approved CI checkout action update plan.

The accepted plan updates GitHub Actions checkout from `actions/checkout@v4` to `actions/checkout@v5` to remove CI warnings caused by the older action runtime.

## Goal

Update `.github/workflows/ci.yml` to use `actions/checkout@v5`.

The existing `repository-baseline` CI job should keep the same behavior otherwise.

## Requirements

- Update `.github/workflows/ci.yml`.
- Change `uses: actions/checkout@v4` to `uses: actions/checkout@v5`.
- Do not add new CI jobs, install steps, caching, permissions, or dependency updates.
- Do not add an ADR because this does not change the project architecture or selected stack.

## Acceptance Criteria

- [ ] `.github/workflows/ci.yml` uses `actions/checkout@v5`.
- [ ] No remaining `actions/checkout@v4` references exist in `.github/workflows/`.
- [ ] The existing `repository-baseline` job behavior is otherwise unchanged.
- [ ] CI runs on pull requests and pushes to `main` as before.
- [ ] PR CI no longer emits the Node.js 20 deprecation warning from `actions/checkout@v4`.

## Out Of Scope

- Adding frontend or backend CI install, lint, test, typecheck, or build jobs.
- Adding workflow caching.
- Changing workflow permissions.
- Updating other GitHub Actions.
- Changing application code.

## Implementation Notes

- Use `actions/checkout@v5` exactly.
- Do not jump to a newer major version in this task.
- GitHub-hosted runners are expected to satisfy the `actions/checkout@v5` minimum runner requirement.

## Testing

Required:

- [ ] Workflow reference search
- [ ] Optional workflow syntax check if `actionlint` is available locally
- [ ] Remote PR CI verification

Not applicable:

- [ ] Frontend tests: no frontend code in scope.
- [ ] Backend tests: no backend code in scope.
- [ ] Integration tests: CI configuration maintenance only.
- [ ] Build: no build configuration or application code changes.
- [ ] Typecheck: no typed source changes.

Commands:

```bash
rg -n "actions/checkout@v4|actions/checkout@v5" .github/workflows
actionlint .github/workflows/ci.yml
```

## Documentation

- Add `tasks/TASK-004-update-checkout-action.md`.
- No ADR is required.

## Notes For AI Agent

- Lue `AGENTS.md`, `ARCHITECTURE.md`, `docs/decisions/ADR-001-tech-stack.md` ja tämä task ennen toteutusta.
- Toteuta vain tämän taskin scope.
- Älä lisää uusia riippuvuuksia.
- Kerro lopuksi mitä muutit ja miten tarkistit työn.
