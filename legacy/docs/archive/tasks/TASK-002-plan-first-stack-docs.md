# TASK-002 Plan First Stack Docs

## Source Plan

This task comes from the developer-approved documentation plan to make tasks the durable source of implementation scope, introduce an AI implementation plan step before task creation, and record the finalized project technology stack.

The accepted plan also decided that GitHub Issues are not used for work intake, that the developer performs the final merge to `main`, and that the stack includes React, TypeScript, Vite, pnpm, Vitest, ESLint, Python, FastAPI, Pydantic, uv, pytest, pyright, Ruff, PostgreSQL, SQLAlchemy, Microsoft Entra ID, Docker containers, and Railway for initial staging.

## Goal

Update the project documentation so the development workflow starts with an idea, then an AI-generated implementation plan, then developer approval, then one or more task files. The task files must become the persistent scope source for AI implementation.

Also update the architecture and stack documentation so the decided frontend, backend, database, authentication, testing, linting, container, and initial staging deployment choices are visible to humans and AI agents.

## Requirements

- Replace Issue-based workflow guidance with plan-first, task-based guidance.
- Document that the developer, not the AI agent, performs the squash merge to `main`.
- Update ADR-001 to accepted and record the finalized stack.
- Update architecture, local development, testing, README, contributing, agent, handbook, database, task, and PR documentation to match ADR-001.
- Remove GitHub Issue templates because Issues are not used for work intake.
- Update the workflow diagram source and regenerated SVG.

## Acceptance Criteria

- [ ] Workflow docs describe `Idea -> AI Implementation Plan -> Developer Approval -> Task(s) -> Branch -> AI Implementation -> Review -> Pull Request -> Developer Merge`.
- [ ] `docs/archive/process/AI-DEVELOPMENT-WORKFLOW.md` section 15 states that the developer merges approved PRs to `main` and the AI agent does not merge.
- [ ] ADR-001 is accepted and lists the finalized stack, including Pydantic, ESLint, Ruff, SQLAlchemy, PostgreSQL, Entra ID, Docker containers, and Railway initial staging.
- [ ] Task and PR templates reference task files only and do not require GitHub Issue links.
- [ ] GitHub Issue templates are removed.
- [ ] Workflow PlantUML and generated SVG reflect the plan-first workflow.
- [ ] Documentation verification confirms no stale Issue-first workflow guidance remains.

## Out Of Scope

- Creating the actual `frontend/` or `backend/` application scaffolds.
- Adding Docker Compose, CI implementation, package manifests, dependencies, or runtime code.
- Selecting database migration tooling.
- Implementing Entra ID authentication.
- Opening or merging the PR.

## Implementation Notes

Relevant files include:

```text
AGENTS.md
docs/architecture/overview.md
docs/archive/process/AI-FIRST-ENGINEERING-HANDBOOK.md
docs/archive/process/CONTRIBUTING.md
README.md
.github/PULL_REQUEST_TEMPLATE.md
docs/archive/process/AI-DEVELOPMENT-WORKFLOW.md
docs/operations/local-development.md
docs/operations/testing.md
docs/architecture/data/DATABASE.md
docs/adr/0001-tech-stack.md
docs/adr/_legacy-template.md
docs/architecture/diagrams/ai-first-pr-workflow.puml
docs/architecture/diagrams/generated/ai-first-pr-workflow.svg
db/init/README.md
db/migrations/README.md
docs/archive/tasks/TASK-TEMPLATE.md
```

Delete:

```text
.github/ISSUE_TEMPLATE/bug.yml
.github/ISSUE_TEMPLATE/feature.yml
```

Render `docs/architecture/diagrams/generated/ai-first-pr-workflow.svg` from the PlantUML source after changing the workflow diagram.

## Testing

Required:

- [ ] Documentation review
- [ ] Stale Issue-first wording search
- [ ] Stack decision wording search
- [ ] Workflow SVG regenerated

Not applicable:

- [ ] Frontend tests: documentation-only change with no frontend application code.
- [ ] Backend tests: documentation-only change with no backend application code.
- [ ] Integration tests: documentation-only change.
- [ ] Build: documentation-only change with no application scaffold.
- [ ] Typecheck: documentation-only change with no application scaffold.

Commands:

```bash
rg -n -i "issue" shadow --glob '!docs/architecture/concepts/INVOICE.md'
rg -n "GitHub Issue|Issue ->|Issue Context|ISSUE-|Closes #|Related Issue|related issue|issue/task|good-first-issue|Select Or Create|Create Or Pick Issue|Give Issue|npm run|npm test|npm install|stack TBD|database stack TBD|teknologiapino on vielä|Teknologiapino on vielä" shadow
rg -n "Pydantic|ESLint|Ruff|ruff check|pnpm lint|\\[ \\] Lint" shadow
docker run --rm -v /home/j/workspace/reflector/shadow/docs/diagrams:/work plantuml/plantuml -tsvg /work/ai-first-pr-workflow.puml -o /work/generated
```

## Documentation

Update the documentation files listed in Implementation Notes.

## Notes For AI Agent

- Lue `AGENTS.md`, `docs/architecture/overview.md`, `docs/adr/0001-tech-stack.md` ja tämä task ennen toteutusta.
- Toteuta vain tämän taskin scope.
- Älä lisää sovelluskoodia tai uusia riippuvuuksia.
- Älä muuta tuotantoympäristöä.
- Älä mergaa main-haaraan.
- Kerro lopuksi mitä muutit ja miten tarkistit työn.
