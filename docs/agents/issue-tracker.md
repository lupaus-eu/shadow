# Issue tracker: Local Markdown

Shadow PRDs, technical designs, domain models, and implementation tickets
live in `.scratch/`. They stay on the local machine: `.gitignore` excludes
everything under `.scratch/` except its README and `_template/`, so they are
never pushed to GitHub. GitHub Issues are not used as a work source.

`.scratch/_PORTFOLIO.md` is the portfolio view. Its first table shows the
delivery state of product features, its second the `tech-*` work, and a third
section lists every open ticket with its unchecked acceptance criteria and
whether its blockers are done. Regenerate it whenever a ticket status or
criterion changes:

```bash
python3 scripts/scratch-status.py > .scratch/_PORTFOLIO.md
```

The script validates every ticket status. An invalid status such as
`completed` stops the run; correct it to the vocabulary in
[`triage-labels.md`](triage-labels.md) first.

## Conventions

- One feature per `.scratch/<feature-slug>/` directory.
- Feature outcome: `PRD.md`.
- Domain specification when needed: `domain-model.md`.
- Technical design: `technical-design.md`.
- Tickets: `issues/<NN>-<slug>.md`, numbered from `01`.
- Every ticket has a `Status:` line near its top and a `## Comments` section
  for later discussion.
- An `implemented` ticket also has `## Ajetut tarkistukset`, `## AI review`
  and `## Completion record`; record actual commands, results, review
  findings, and updated documentation paths there.
- Use `.scratch/tech-<slug>/` for architecture, tooling, or documentation work
  that is not a user-facing feature.
- An effort that spans several features (for example the SaaS platform) may
  keep its overall plan in `.scratch/<effort>/PLAN.md`; each feature it
  produces still gets its own directory.

All permitted statuses and their meanings are in
[`triage-labels.md`](triage-labels.md). The `Status:` line in an `issues/`
file is the authoritative local work queue. PRD, domain-model, and technical
design statuses express acceptance of those artefacts, not open implementation
work.

When a skill says “publish to the issue tracker”, create or update the
relevant Markdown file in `.scratch/`. When it says “fetch the ticket”, read
the path the user supplied.

## Branches and commits

Name a branch after the work and ticket:
`feature/<feature-slug>-NN-short-name`, `fix/<slug>-NN-short-name`,
`docs/…`, `chore/…`, or `refactor/…`. Branches stay local like the tickets:
only `main` is pushed to GitHub, so GitHub pull requests are not used. When a
ticket is complete, the agent merges its branch into the local `main`
(fast-forward) and deletes the branch; the human reviews the unpushed commits
and pushes `main`. Agents never push.

A commit message names the feature slug and ticket number; because the ticket
itself is local, the message also states the goal, the checks run, and the
one-line AI review summary.

## History

Work before November 2026 was specified as `tasks/TASK-*.md` and reviewed with
JSON records. The tasks are kept read-only in
[`docs/archive/tasks/`](../archive/tasks/) and the review records in
[`docs/ai-reviews/`](../ai-reviews/) (format: [ai-review-records.md](ai-review-records.md)).
Existing ADRs, code comments, and documents still cite those `TASK-*`
identifiers; do not create new ones.

## Wayfinding operations

For `/wayfinder`, use `.scratch/<effort>/map.md` and one child ticket per file
under `issues/`. Record blockers as `Blocked by: 01, 02`; the frontier is the
first open, unblocked, unclaimed ticket. Claim it with `Status: claimed`; on
resolution, add `## Answer`, set `Status: resolved`, and link the result from
the map. Implementation tickets instead finish as `implemented` after their
definition of done is met.
