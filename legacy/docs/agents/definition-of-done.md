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
- The implementing agent started the [AI review](#ai-review) itself; findings
  and how each was resolved or accepted are in `## AI review`.
- Each selected `Documentation effects` item names an updated file or a justified
  exception.
- Any implementation difference is reflected in the technical design, PRD, and
  ADR before the ticket closes.
- No secrets, test data for production, or sensitive values in logs were added.
- The ticket has `## Completion record` and `Status: implemented`.

## Change-specific conditions

| Change | Complete when |
| --- | --- |
| Data model or migration | A paired `db/migrations/NNN_name.sql` and `NNN_name.down.sql` exist (ADR-002), the PostgreSQL integration tests pass against a disposable database, and `docs/architecture/data/` (`DATA-MODEL.md`, `DATABASE.md`), the DB diagrams, and relevant ADRs were evaluated. |
| API or authorization | Success, failure, and authorization paths are tested in the backend; the owning domain document and authorization documentation were evaluated. |
| UI or UX | A focused UI test is added where suitable, accessibility and `docs/design/` are evaluated, and a changed user workflow is browser-checked. |
| Service boundary, container, or deployment | A suitable Compose/startup check is run; `docs/architecture/deployment.md`, `docs/operations/`, `docs/runbooks/`, and `.env.example` were evaluated. |
| External integration | Success, failure, retry/idempotency, configuration, operations, and audit effects are tested and documented as applicable. |
| Diagram-relevant change | The PlantUML or LikeC4 source and the generated SVG in `docs/architecture/diagrams/` are updated. |
| Durable architecture decision | The relevant ADR is added or updated before implementation is complete. |
| Production operation | It was explicitly approved by a human, and its evidence is in `docs/operations/qa/`. |

## AI review

Every implementation ticket gets an independent review before it is closed.
The implementing agent starts it on its own, without being asked, once the
ticket's checks pass. The reviewer must not inherit the implementer's
reasoning: it sees only the ticket and the diff.

1. **Start the review.** Run the `code-review` skill on the ticket's diff, or
   start a subagent with fresh context and give it only the ticket's path and
   the diff (not your conclusions). Choose the effort by risk:

   | Change | Review |
   | --- | --- |
   | Authentication, authorization, tenant isolation or RLS, billing, migrations of existing data, secrets, MCP OAuth | `high` |
   | Other application code | `medium` |
   | Documentation or comments only | No review; say so in the ticket |

2. **Fix and repeat.** Fix the findings, rerun the affected checks, and review
   again. Stop after **three rounds**: findings that remain are listed for the
   human as open, or as accepted risks with a reason.
3. **Record it** in the ticket's `## AI review`: the rounds and effort, each
   finding with its severity and outcome (`fixed`, `accepted risk` with the
   reason, or `not reproduced`), and anything left for the human.
4. **Summarize it in the commit message**, because the ticket stays local, in
   one line such as `AI review: 2 rounds (high), 3 fixed, 1 accepted risk
   (rate limit is per process)`.

The JSON records in `docs/ai-reviews/` ([format](ai-review-records.md)) are
historical and not written for new work.

A feature is complete only when its PRD, optional domain model, and technical
design are `accepted`, all tickets are `implemented` or `resolved`, and the
PRD's documentation effects are complete.
