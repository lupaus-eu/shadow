# Testing

Tämä dokumentti kuvaa projektin testauskäytännön ihmisille ja AI-agenteille.

Status: frontend and backend test tooling configured

Testityökalut on päätetty ADR-001:ssä:

- frontend: Vitest
- frontend linting: ESLint
- backend: pytest
- backend type checking: pyright
- backend linting: Ruff

---

# Principle

Jokaisessa sovelluskoodin muutoksessa pitää tehdä jompikumpi:

1. lisää tai päivitä relevantit testit
2. perustele miksi testejä ei lisätty

AI-agentti ei saa jättää testausta hiljaisesti tekemättä.

---

# What To Test

## Documentation-only Change

Required:

- tarkista Markdown ja linkit kohtuullisesti
- aja saatavilla oleva dokumentti- tai baseline-tarkistus, jos sellainen on olemassa

Tests may be marked not applicable.

## Small UI Or API Change

Expected:

- unit tests for changed logic
- manual verification for visible behavior
- update snapshots or component tests if project uses them

## Domain Logic Change

Expected:

- unit tests for domain rules
- edge cases for validation and lifecycle rules
- tests for failure paths

Also check:

- relevant domain document
- relevant concept document

## Database Or Migration Change

Expected:

- migration script in `db/migrations/`
- test or documented verification that migration applies cleanly
- data model documentation update when logical model changes
- database documentation update when physical schema changes

Also update when relevant:

- `docs/data/DATA-MODEL.md`
- `docs/data/DATABASE.md`
- `docs/diagrams/db-physical-schema.puml`
- `docs/diagrams/generated/db-physical-schema.svg`

## Integration Change

Expected:

- unit tests around adapter boundaries
- integration tests when a local or test service is available
- mocked failure cases
- documented manual verification if full integration testing is not possible

## Security-Sensitive Change

Expected:

- tests for authorization checks
- tests for invalid input
- tests for forbidden access
- regression tests for the security boundary

Examples:

- authentication
- authorization
- permissions
- tenant or organization boundaries
- file upload
- SQL or query construction
- secrets handling

---

# Test Levels

Use the lightest useful test level.

## Unit Tests

Use for:

- pure logic
- validation
- domain rules
- formatting/parsing
- small service functions

Frontend unit tests use Vitest.

Backend unit tests use pytest.

Frontend linting uses ESLint.

Backend linting uses Ruff.

## Integration Tests

Use for:

- API endpoint behavior
- database reads/writes
- cross-module flows
- adapter boundaries

## End-to-End Tests

Use only for critical user flows.

Examples:

- registration
- login
- document upload
- payment or billing flow
- permission-sensitive workflow

Do not add broad E2E coverage by default. Keep E2E tests focused.

## Manual Verification

Manual verification is acceptable when:

- the project has no test stack yet
- the behavior is visual
- external systems are not available locally
- the change is documentation-only

Manual verification must be described in the PR.

---

# Task Testing Section

Every task should include a `Testing` section.

Use this shape:

````markdown
## Testing

Required:

- [ ] Unit tests
- [ ] Integration tests
- [ ] Manual verification
- [ ] Build
- [ ] Lint

Not applicable:

- [ ] Reason:

Commands:

```bash
# Frontend, if applicable
cd frontend
pnpm lint
pnpm test
pnpm build

# Backend, if applicable
cd backend
uv run ruff check .
uv run pytest
uv run pyright
```
````

If tests are not added, explain why.

---

# AI Agent Instructions

When implementing a task, the AI-agent must:

1. identify what behavior changed
2. decide what test level is appropriate
3. add or update tests when the change touches application code
4. run available test commands
5. report the exact commands and result
6. explain if tests were not added or could not be run

Use this prompt addition:

```text
Lisää tai päivitä testit muutoksen riskin mukaan.
Jos et lisää testejä, perustele miksi.
Aja saatavilla olevat testikomennot ja raportoi tulokset.
```

---

# When Scaffolding Is Missing

ADR-001 has selected the stack, but the repository may not yet have runnable `frontend/` or `backend/` scaffolds.

In that case:

- do not invent scripts outside the task scope
- do not add dependencies without approval
- document what should be tested later
- perform available static or manual checks
- report that automated tests are not yet configured in the affected package

---

# CI Expectations

Current baseline CI checks repository documentation structure.

CI runs the repository baseline checks and backend scaffold checks. As application
coverage grows, CI should run:

```text
Install
Lint
Tests
Typecheck
Build
```

The exact commands must be documented in:

- `README.md`
- `docs/LOCAL-DEVELOPMENT.md`
- this file
- `.github/workflows/ci.yml`

---

# PR Expectations

Every PR must state:

- what tests were added or updated
- what commands were run
- whether manual verification was done
- why tests were not added, if not applicable

PRs that change application behavior without tests or a clear reason should not be approved.
