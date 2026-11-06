# Shadow feature and specification workflow

This workflow keeps the user outcome, business rules, technical solution, and
implementation tasks distinct so that an agent can deliver a small, tested
vertical slice without expanding the agreed scope. It is the same workflow as
in Yearclock, which the same team maintains.

## Levels

1. `PRD.md` describes the user outcome, scope, vocabulary, and acceptance criteria.
2. `domain-model.md` is optional clarification of business rules, lifecycle,
   ownership, and authorization.
3. `technical-design.md` describes the technical solution, risks, tests, and
   documentation effects.
4. `issues/` contains small, implementable, verifiable tickets.

Create one directory per feature by copying `.scratch/_template/`:

```text
.scratch/
└── feature-slug/
    ├── PRD.md
    ├── domain-model.md         # when needed
    ├── technical-design.md
    └── issues/
        ├── 01-domain-and-api.md
        ├── 02-ui.md
        └── 03-tests-and-documentation.md
```

Use lowercase letters and hyphens in the feature slug. Technical work that is
not a user-facing feature belongs in `.scratch/tech-<slug>/`; it has a
technical design and tickets but no feature PRD.

`.scratch/` is local: PRDs, designs, and tickets are never pushed to GitHub.
Everything that must outlive the work (vocabulary, decisions, architecture,
user and operator guidance) is written to `CONTEXT.md`, `docs/adr/`, and
`docs/` as part of the tickets.

## PRD

The PRD describes what a user can do and why. It does not select tables,
routes, or component structure. Record the goal, user, use case, acceptance
criteria, non-goals, domain terms, documentation effects, and open questions.

Define a new or ambiguous business term first in the PRD or in `CONTEXT.md`.
Use the canonical vocabulary: an Organisation is the modelled organisation,
not the subscribing company, and a Scenario is not an Organisation State.

Open business decisions are settled with the user before the PRD is
accepted, for example by grilling the draft (`/grilling`) one question at a
time.

## Domain specification

Create `domain-model.md` after the PRD and before technical design when the
feature changes a lifecycle, ownership, permission rule, integration boundary,
or canonical business term. It defines terms, aggregate ownership, state
transitions, invariants, and the authorization matrix. It does not select SQL
tables, HTTP routes, or frontend components.

Simple features may proceed directly from PRD to technical design.

## Technical design and tickets

After the PRD is accepted, the technical design describes persistence, API,
frontend, authorization, integrations, errors, testing, configuration,
architecture effects, and documentation effects. Record a durable architecture
choice in `docs/adr/`; keep feature-specific detail in `.scratch/`.

A ticket has one small, verifiable goal. It includes acceptance criteria, test
selection, executed checks, an AI review, documentation effects, a completion
record, and a `Blocked by` section. Implement only that ticket's scope. Update
the design and any affected ADR before closing a ticket when implementation
changes a settled decision. Aim for under 500 lines of reviewable change per
ticket.

The completion conditions are in
[`docs/agents/definition-of-done.md`](docs/agents/definition-of-done.md) and
test selection is in [`docs/agents/testing.md`](docs/agents/testing.md).

## Documentation effects

Every PRD and technical design must evaluate effects on at least one item
below, or explain why no durable documentation changes:

- `docs/user/` — end-user workflows
- `docs/admin/` — administration and access guidance
- `docs/operations/` and `docs/runbooks/` — development, deployment,
  monitoring, QA evidence, and incident guidance
- `docs/gdpr/` — privacy, retention, and compliance material
- `docs/legal/` — legal texts and how they are published
- `docs/architecture/` — technical context, service boundaries, domains,
  concepts, the data model, and diagrams
- `docs/design/` — durable UI and UX guidance
- `docs/adr/` — durable architecture decisions
- `CONTEXT.md` — canonical business vocabulary
- `.env.example` — required configuration keys

## Delivery sequence

1. The user describes an idea.
2. The agent drafts a PRD and identifies open business decisions.
3. The user accepts the outcome, scope, vocabulary, and acceptance criteria.
4. The agent creates a domain specification when it is needed.
5. The agent creates a technical design and small tickets.
6. The user accepts material technical decisions where approval is needed
   (new dependencies, architecture changes, production operations).
7. The agent implements tickets one at a time on the local `main`, with
   focused tests and the required documentation updates.
8. The agent runs the applicable backend, frontend, browser, database, and
   architecture checks, then starts the AI review itself (a fresh-context
   reviewer, at most three rounds) and records the evidence in each ticket.
9. The agent commits the finished ticket to the local `main`. The human
   reviews the unpushed commits and pushes `main`, the only branch on GitHub.
   Images are built only from a `v*` tag that the human pushes, and production
   releases need separate human approval.

Do not begin substantial implementation until the PRD acceptance criteria and
the essential technical decisions are sufficiently clear.
