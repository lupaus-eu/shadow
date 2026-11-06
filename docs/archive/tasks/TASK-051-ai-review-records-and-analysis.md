# TASK-051 AI Review Records and Analysis

## Source Plan

Developer-approved plan: retain every AI-review round as a version-controlled,
structured JSON record so agents and developers can inspect review evidence,
identify recurring categories of findings, and propose advisory follow-up work.

The approved plan selects JSON-only review records, retains every review round,
uses structured findings rather than raw prompts, diffs or transcripts, adds a
dependency-free local aggregation command, and leaves all conclusions and
follow-up decisions with the developer.

## Goal

Make Step 13 of `docs/archive/process/AI-DEVELOPMENT-WORKFLOW.md` produce durable,
machine-readable AI-review evidence. A developer or agent must be able to
validate the archive and generate an on-demand summary of findings, their
resolution status, and recurring review patterns without adding a runtime
dependency or making the AI-review process a CI or merge gate.

## Requirements

- Add a version-controlled `docs/ai-reviews/` archive with a short README.
  Store records under `docs/ai-reviews/TASK-XXX/` as sequential
  `review-001.json`, `review-002.json`, and so on.
- Define schema version `1` in documentation and enforce it with a
  dependency-free Python command. Records must include:
  - record ID, task ID/path, round number, UTC timestamp, reviewer label and
    optional PR reference;
  - committed base and reviewed-head SHA references, the comparison range, and
    the archive exclusion `docs/ai-reviews/**` to prevent recursive review of
    review metadata;
  - review outcome: `clean`, `findings`, or `inconclusive`, plus a concise
    conclusion summary;
  - findings with a record-local stable ID, category, severity, concise
    rationale, recommendation and affected repository path with optional line
    reference; and
  - dispositions of findings from earlier records: `fixed`, `accepted_risk`,
    or `not_reproduced`, including a rationale and the review or commit that
    validates the disposition.
- Limit finding categories to `bug`, `regression`, `security`, `missing_test`,
  `documentation`, and `scope`; limit severity to `critical`, `high`,
  `medium`, `low`, and `info`.
- Require a record for every AI-review round, including a clean or
  inconclusive review. A later review record, rather than an overwritten prior
  record, must record dispositions for earlier findings.
- Do not retain prompts, raw model output, complete diffs, code snippets,
  request/response bodies, credentials, tokens, personal data, or URLs with
  sensitive query values in review records. Document that authors must redact
  sensitive material before committing.
- Add `scripts/ai_review_records.py` with these interfaces:

  ```bash
  python3 scripts/ai_review_records.py validate
  python3 scripts/ai_review_records.py summarize --format json
  python3 scripts/ai_review_records.py summarize --format markdown
  ```

  `validate` must fail with the record path and reason for malformed JSON,
  unknown schema version, missing or invalid fields/enums, duplicate record or
  finding references, invalid per-task round sequence, and invalid prior
  finding disposition references. `summarize` must read only valid records and
  report review/outcome counts, open findings, counts by category, severity and
  disposition, and recurrence candidates grouped by category and affected
  repository files. It must write reports to stdout and must not modify files,
  create tasks, or make approval decisions.
- Update Step 13, `docs/archive/process/AI-FIRST-ENGINEERING-HANDBOOK.md`, `AGENTS.md`, and
  `.github/PULL_REQUEST_TEMPLATE.md` with the archive lifecycle, validation
  command, record link, resolution loop, redaction rule, and the fact that
  aggregate analysis is advisory only.
- Update `docs/architecture/diagrams/ai-first-pr-workflow.puml` to show record creation and
  validation as part of Step 13, and regenerate
  `docs/architecture/diagrams/generated/ai-first-pr-workflow.svg`.

## Acceptance Criteria

- [ ] `docs/ai-reviews/` documents the record location, schema version 1,
      naming, required fields, redaction rules, and a standard Step 13 review
      and analysis flow.
- [ ] A valid record can represent a clean review, a review with findings, and
      an inconclusive review of a committed diff or PR.
- [ ] Every finding can be traced to its review record and later disposition
      without editing the original review record.
- [ ] The validator accepts valid multi-round fixture data and rejects each
      defined invalid condition with a precise failure message.
- [ ] Both aggregation formats accurately show counts, unresolved findings,
      prior dispositions, and recurrence candidates from fixture data.
- [ ] Step 13, the handbook, agent rules, PR template and workflow diagram all
      state that review records are required, exclude archive metadata from the
      reviewed scope, retain no sensitive raw evidence, and do not create a CI
      merge gate.
- [ ] The regenerated SVG reflects the updated PlantUML workflow source.
- [ ] No application runtime behavior, database schema, migration, external
      integration, dependency list, or CI merge requirement changes.

## Out Of Scope

- Implementing an automatic CI or merge gate that requires an AI-review record
  or resolves review findings.
- Saving raw AI prompts, transcripts, patches, source snapshots or other
  sensitive review evidence.
- Automatically creating, approving, or modifying task files, ADRs, PRs or
  code from aggregate analysis.
- Adding a new Python package, a frontend dependency, a backend runtime
  dependency, database tables, migrations, or external service integration.
- Retrospectively creating records for existing tasks or pull requests.

## Implementation Notes

Read before implementation:

```text
AGENTS.md
docs/architecture/overview.md
docs/archive/process/AI-FIRST-ENGINEERING-HANDBOOK.md
docs/archive/process/AI-DEVELOPMENT-WORKFLOW.md
docs/architecture/diagrams/README.md
docs/archive/tasks/TASK-051-ai-review-records-and-analysis.md
```

- This is process documentation and local tooling; no ADR is required because
  it does not change the application architecture, technology stack, runtime
  or deployment model.
- Make the Python script self-contained with the Python standard library. The
  documented schema is the public contract; keep validation behavior aligned
  with it.
- Scan only task record files inside `docs/ai-reviews/TASK-*/`; do not treat
  README files or test fixtures as production records.
- Record `base_sha` and `head_sha` as immutable committed revisions. The
  `head_sha` identifies the implementation diff actually reviewed; committing
  its metadata afterward does not require recursively reviewing that metadata.
- A later review must declare any disposition against the exact earlier record
  ID and finding ID. Findings without a later disposition remain open in the
  aggregation output.
- Use concise, redacted summaries and repository-relative file references.
  Review records are not a replacement for Git history, PR discussion, tasks
  or ADRs.
- The aggregate report is input for an AI or developer to make evidence-based
  recommendations. Any durable product, architecture or implementation
  decision remains in a developer-approved task or ADR.

Suggested branch:

```text
docs/TASK-051-ai-review-records-and-analysis
```

## Testing

Required:

- [ ] Standard-library unit tests for the validator and aggregator
- [ ] Valid clean, findings and inconclusive JSON fixtures
- [ ] Multi-round fixture with a prior finding disposition
- [ ] Invalid JSON, required-field, enum, duplicate-ID, round-order and
      invalid-prior-reference rejection coverage
- [ ] JSON and Markdown aggregation output verification
- [ ] Manual documentation/workflow review
- [ ] PlantUML SVG regeneration and visual inspection

Not applicable:

- [x] Frontend lint, tests and build: no frontend change.
- [x] Backend lint, tests, typecheck and build: no backend application change.
- [x] Integration tests: no application or external integration behavior.
- [x] Database migration verification: no data-model or schema change.
- [x] CI merge-gate verification: CI enforcement is explicitly out of scope.

Commands:

```bash
# Run the new standard-library tooling tests from the repository root.
python3 -m unittest discover -s scripts/tests

# Validate committed AI-review records and inspect both report formats.
python3 scripts/ai_review_records.py validate
python3 scripts/ai_review_records.py summarize --format json
python3 scripts/ai_review_records.py summarize --format markdown

# Regenerate the workflow diagram after changing its PlantUML source.
docker compose --profile docs build diagram-renderer
docker compose --profile docs run --rm diagram-renderer \
  -tsvg -o generated ai-first-pr-workflow.puml
```

## Documentation

Update:

- `AGENTS.md`
- `docs/archive/process/AI-FIRST-ENGINEERING-HANDBOOK.md`
- `.github/PULL_REQUEST_TEMPLATE.md`
- `docs/archive/process/AI-DEVELOPMENT-WORKFLOW.md`
- `docs/agents/ai-review-records.md`
- `docs/ai-reviews/README.md`
- `docs/architecture/diagrams/ai-first-pr-workflow.puml`
- `docs/architecture/diagrams/generated/ai-first-pr-workflow.svg`

## Notes For AI Agent

- Implement only this task's documentation, local record archive and
  dependency-free analysis-tooling scope.
- Do not add dependencies or change CI into a record-presence or review-outcome
  gate.
- Do not include secrets, tokens, personal data, raw prompts, model transcripts
  or raw diffs in any committed record, fixture or documentation example.
- Do not modify frontend/backend application behavior, database schema,
  migrations, authentication, authorization, deployment or external
  integrations.
- Update both the PlantUML source and generated SVG when changing the workflow
  diagram.
- Report the exact validation, fixture, documentation and diagram checks run.
