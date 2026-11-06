# Implementation guidance

1. Read `AGENTS.md`, `CONTEXT.md`, the relevant architecture documents, PRD,
   technical design, and ticket. Select additional documents with
   [architecture routing](architecture-routing.md).
2. Clarify missing acceptance criteria before coding.
3. Implement one narrow vertical slice across persistence, API, and UI only as
   required by the ticket.
4. Add focused backend, frontend, and browser tests with the change.
5. Complete the ticket's documentation effects in the same change, including
   `docs/design/` for durable UI decisions and the diagrams for changed
   architecture.
6. Update the technical design and ADR before closing the ticket if
   implementation differs from a settled decision.
7. Select and run applicable checks with [testing guidance](testing.md), then
   record exact commands and results in the ticket.
8. Start the AI review yourself, without being asked: the `code-review` skill
   or a fresh-context subagent given only the ticket and the diff, at the
   effort and with the three-round limit in the
   [definition of done](definition-of-done.md#ai-review). Record the findings
   and their resolution in the ticket.
9. Update `.env.example` when configuration changes.

Treat authentication and backend authorization checks, input validation,
parameterized SQL, data isolation between customers, auditability,
idempotency, and external-system boundaries as invariants. Close an
implementation ticket only after the [definition of done](definition-of-done.md)
is satisfied.
