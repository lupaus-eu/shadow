# Implementation guidance

1. Read `AGENTS.md`, `CONTEXT.md`, the relevant architecture documents, PRD,
   technical design, and ticket. Select additional documents with
   [architecture routing](architecture-routing.md).
2. Clarify missing acceptance criteria before coding.
3. Implement one narrow vertical slice across persistence, API, and UI only as
   required by the ticket.
4. Add focused backend and browser tests with the change.
5. Complete the feature's documentation effects in the same ticket, including
   `docs/design/` for durable UI decisions.
6. Update the technical design and ADR before closing the ticket if
   implementation differs from a settled decision.
7. Select and run applicable checks with [testing guidance](testing.md), then
   record exact commands and results in the ticket.
8. Update `.env.example` when configuration changes.

Treat Organization isolation, authorization, auditability, idempotency, and
external-system boundaries as invariants. Close an implementation ticket only
after the [definition of done](definition-of-done.md) is satisfied.
