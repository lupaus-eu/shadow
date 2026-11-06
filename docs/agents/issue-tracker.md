# Issue tracker: Local Markdown

Yearclock PRDs, technical designs, domain models, and implementation tickets
live in `.scratch/`.

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
- An `implemented` ticket also has `## Ajetut tarkistukset` and
  `## Completion record`; record actual commands, results, and updated
  documentation paths there.
- Use `.scratch/tech-<slug>/` for architecture, tooling, or documentation work
  that is not a user-facing feature.

All permitted statuses and their meanings are in
[`triage-labels.md`](triage-labels.md). The `Status:` line in an `issues/`
file is the authoritative local work queue. PRD, domain-model, and technical
design statuses express acceptance of those artefacts, not open implementation
work.

The `.scratch/yearclock-v1/` tickets were split from a single legacy
`tickets.md` into `issues/` on 2026-09-23. Tickets 01–06 predate the
definition of done, so their `Ajetut tarkistukset` and `Completion record`
sections state that no evidence was recorded.

When a skill says “publish to the issue tracker”, create or update the
relevant Markdown file in `.scratch/`. When it says “fetch the ticket”, read
the path the user supplied.

## Wayfinding operations

For `/wayfinder`, use `.scratch/<effort>/map.md` and one child ticket per file
under `issues/`. Record blockers as `Blocked by: 01, 02`; the frontier is the
first open, unblocked, unclaimed ticket. Claim it with `Status: claimed`; on
resolution, add `## Answer`, set `Status: resolved`, and link the result from
the map. Implementation tickets instead finish as `implemented` after their
definition of done is met.
