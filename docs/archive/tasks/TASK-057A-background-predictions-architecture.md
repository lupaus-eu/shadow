# TASK-057A Background Predictions Architecture And Contracts

## Source Plan

Approved plan: "Background Prediction Requests", accepted for task creation in
the conversation on 2026-09-07 under Step 3 of
`docs/archive/process/AI-DEVELOPMENT-WORKFLOW.md`.

This is the architecture prerequisite for
[TASK-057B](TASK-057B-snapshot-based-prediction-calculation.md),
[TASK-057C](TASK-057C-durable-prediction-requests-worker.md),
[TASK-057D](TASK-057D-prediction-request-ui.md), and
[TASK-057E](TASK-057E-prediction-worker-runtime-qa.md).
These files specify future work; their creation does not implement the tasks.

## Goal

Document the accepted architecture and contracts for durable background
prediction requests before changing the Forecasting implementation. Separate
the mutable request lifecycle from immutable completed prediction versions.

## Requirements

- Create `docs/adr/0012-background-prediction-requests.md` from the
  approved plan. Supersede ADR-007's synchronous execution restriction while
  retaining existing forecasting algorithms, input isolation, intervals,
  eligibility rules, work limits, and completed-version immutability.
- Specify a PostgreSQL queue and one separate worker service using the existing
  backend image and dependencies. Process one request at a time globally in
  submission order, with a database advisory lock preventing duplicate workers
  from calculating concurrently.
- Define states `queued`, `running`, `cancelling`, `completed`, `cancelled`, and
  `failed`. Queued cancellation is immediate; running cancellation terminates
  the calculation promptly and discards partial output. Retain request history.
- Freeze a consistent input snapshot at submission, including observations,
  explanatory features, metric metadata, seasonal settings, model configuration,
  derived formulas, and referenced metric keys and short names. Calculation
  must not reread live source data.
- Specify Forecasting ownership of `prediction_requests`, with request identity,
  organisation, name, immutable snapshot, state, timestamps, submitter,
  cancellation actor, worker ownership, safe failure information, and optional
  completed-version reference. Preserve existing saved versions without
  synthesizing historical requests.
- Reserve names case-insensitively per organisation for active requests and
  completed versions. Cancelled and failed requests release their names.
  Serialize name admission and publication to prevent concurrent duplicates.
- Define atomic publication of the complete version and completed request state.
  Cancellation accepted before publication prevents a saved version; completion
  committed first remains completed. Model ineligibility is a normal saved
  result; unexpected failure leaves no partial version.
- Specify a supervised child process per calculation. The supervisor alone
  publishes results, checks work/cancellation every second, terminates on Stop,
  force-kills after a two-second grace period if needed, and reaps the child.
  Require cancellation within five seconds in healthy local verification.
- Require queued requests to survive restarts. Interrupted running work fails
  visibly without automatic retries; abandoned cancelling work becomes
  cancelled. Lost worker ownership prevents publication. Browser navigation,
  logout, and session expiry do not cancel accepted work.
- Define organisation-scoped request list/detail/cancel contracts. Existing
  prediction creation becomes `202 Accepted` with a request summary and status
  URL. Preflight stays synchronous; completed prediction list/detail contracts
  remain unchanged. TASK-057C contains the route inventory.
- Keep existing business authorization: consultants and administrators may
  inspect and cancel another user's requests. Organisation lookup, mutation
  CSRF/Origin checks, and actor attribution remain mandatory.
- Specify state-only progress in the current organisation's Predictions tab,
  all active requests plus the 50 most recently finished requests, and two-second
  polling while visible. Do not add percentages, work counters, time estimates,
  workspace-wide indicators, or deletion of saved predictions.
- Document that API, frontend, and worker require coordinated release because
  the create response changes. Worker startup follows successful migrations,
  uses no public port or OIDC credentials, and has its own health check and
  restart policy. Production rollout still needs separate human approval.

## Acceptance Criteria

- [ ] ADR-012 records the queue, ownership, snapshot, cancellation, recovery,
      naming, authorization, API, and runtime decisions above.
- [ ] ADR-007's synchronous restriction is explicitly superseded without
      changing model behavior or weakening saved-version invariants.
- [ ] The request state transitions and cancellation/publication race have one
      unambiguous outcome; names are reusable only after cancellation/failure.
- [ ] Source documents distinguish an accepted design from runtime behavior
      still awaiting TASK-057B through TASK-057E.
- [ ] Documentation and relevant diagrams agree and provide the downstream
      tasks with an implementation source of truth.
- [ ] No application code, migration, dependency, or Compose service is changed.

## Out Of Scope

- Implementing input snapshots, the request schema, queue, worker, or APIs.
- Frontend code, deployment wiring, or any production action.
- Brokers, task frameworks, concurrent processing, automatic retries, scheduling,
  queue reordering, result deletion, or changes to model behavior/work limits.

## Implementation Notes

Read `AGENTS.md`, `docs/architecture/overview.md`, ADR-002 through ADR-005, ADR-007,
ADR-009 through ADR-011, `docs/architecture/domains/FORECASTING.md`, the data documentation,
and `docs/architecture/diagrams/README.md`. Read the five TASK-057 specifications together
when checking the contracts. Record the approved architecture without claiming
that its runtime implementation is already available.

## Testing

Required: documentation consistency and local-link checks; render and inspect
every changed PlantUML source and its generated SVG.

Not applicable: application tests, lint, typecheck, and application builds,
because this task changes architecture documentation only.

Commands for diagrams and the eventual Step 13 record:

```bash
docker compose --profile docs build diagram-renderer
docker compose --profile docs run --rm diagram-renderer
docker compose --profile docs run --rm diagram-renderer -tsvg -o generated data-logical-model.puml
python3 scripts/ai_review_records.py validate
```

Render any additional changed architecture/lifecycle source explicitly using
the same renderer and inspect the output.

## Documentation

Create ADR-012 and update relevant ADR cross-references, `docs/architecture/overview.md`,
`docs/architecture/domains/FORECASTING.md`, and `docs/architecture/domains/DOMAIN.md` where ownership needs
clarification. Update logical data documentation and relevant architecture,
logical-data, and request-lifecycle diagrams with matching SVGs. Physical
schema implementation and its diagram belong to TASK-057C; deployed runtime
documentation is completed by TASK-057E.

## Notes For AI Agent

- Implement only this documentation task when separately requested.
- Do not introduce dependencies or implement another TASK-057 task.
- Preserve the user's state-only progress choice.
- Record each eventual Step 13 review under `docs/ai-reviews/TASK-057A/` using
  `docs/agents/ai-review-records.md`; report changed files and checks.
