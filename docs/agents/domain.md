# Domain Docs

This repository uses a single-context domain-doc layout with a root glossary
and per-domain and per-concept documents.

## Before exploring or designing

- `CONTEXT.md` at the repository root (canonical vocabulary)
- Relevant accepted decisions under `docs/adr/`
- The owning domain in `docs/architecture/domains/` (`DOMAIN.md` is the
  index) when the work touches a domain's data, API, or rules
- The concept in `docs/architecture/concepts/` (`CONCEPTS.md` is the index)
  when the work touches a concept's fields, relationships, invariants, or
  lifecycle
- `docs/architecture/data/` when the work touches persistence

If a document is absent, proceed silently. Domain-modeling skills create
documentation lazily when terms or decisions are resolved.

## Use the glossary's vocabulary

Use domain concepts as defined in `CONTEXT.md`. Avoid synonyms the glossary
explicitly rejects. If a needed concept is absent, reconsider the terminology
or note the gap for domain modeling.

## Flag ADR conflicts

Explicitly surface proposed work that contradicts an existing ADR instead of
silently overriding it.

## Feature-specific domain specification

Create `.scratch/<feature>/domain-model.md` from
`.scratch/_template/domain-model.md` after the PRD and before technical design
when a feature introduces a business concept, changes a lifecycle or ownership
rule, contains a state machine or approval/authorization rule, crosses domains
or integration boundaries, or exposes ambiguity in the canonical vocabulary.

Define the terms, aggregate ownership, state transitions, invariants, and
authorization matrix. The domain specification does not decide database tables,
HTTP routes, or UI components; those belong to the technical design. Promote
system-wide terminology and settled decisions to `CONTEXT.md`,
`docs/architecture/domains/`, `docs/architecture/concepts/`, or `docs/adr/`
when they are confirmed in implementation.
