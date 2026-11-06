# Ticket definition of done

A ticket is `implemented` when its own scope is complete, not when the whole
feature is complete. Record evidence in the ticket itself; “tested” alone is
not evidence.

## Required checklist

- Acceptance criteria are met, or their scope was updated before implementation.
- The change stays within the ticket; follow-up work has its own ticket.
- Focused tests were added where applicable, or their absence is justified.
- Applicable checks were run; exact commands and results are in
  `## Ajetut tarkistukset`.
- Each selected `Documentation effects` item names an updated file or a justified
  exception.
- Any implementation difference is reflected in the technical design, PRD, and
  ADR before the ticket closes.
- The ticket has `## Completion record` and `Status: implemented`.

## Change-specific conditions

| Change | Complete when |
| --- | --- |
| Data model or migration | The Alembic migration and applicable PostgreSQL-backed tests are complete; `docs/architecture/database.md` and relevant ADRs were evaluated. |
| API or authorization | Success, failure, and authorization paths are tested; API and authorization documentation was evaluated. |
| UI or UX | A focused UI test is added where suitable, accessibility and `docs/design/` are evaluated, and a changed user workflow is browser-tested. |
| Service boundary, container, or deployment | A suitable Compose/startup check is run; architecture, operations, and `.env.example` were evaluated. |
| External integration | Success, failure, retry/idempotency, configuration, operations, and audit effects are tested and documented as applicable. |
| Cookie or web-storage key | The key or cookie is added to `backend/legal/browser-storage.json` and the browser storage notice (`backend/legal/storage.*.md`) is evaluated; `frontend/tests/unit/browser-storage.test.ts` and `backend/tests/test_browser_storage.py` fail until both agree with the code. |
| Durable architecture decision | The relevant ADR is added or updated before implementation is complete. |

A feature is complete only when its PRD, optional domain model, and technical
design are `accepted`, all tickets are `implemented` or `resolved`, and the
PRD's documentation effects are complete.
