# Specs and implementation tickets

This directory holds feature PRDs, domain models, technical designs, and
implementation tickets. **Only this README and `_template/` are versioned**;
everything else under `.scratch/` stays on the local machine and is never
pushed to GitHub (see `.gitignore`). Durable outcomes are promoted to
`docs/`, `CONTEXT.md`, and `docs/adr/` when they are settled.

Use one directory per feature. The complete process is documented in
[`FEATURE_WORKFLOW.md`](../FEATURE_WORKFLOW.md); copy `.scratch/_template/` to
start a feature:

```text
.scratch/<feature-slug>/
├── PRD.md
├── domain-model.md          # when lifecycle, permissions, or rules need it
├── technical-design.md
└── issues/
    ├── 01-<vertical-slice>.md
    └── 02-<vertical-slice>.md
```

Technical and architecture work that is not a user-facing feature uses
`.scratch/tech-<slug>/`. Its technical design and tickets are mandatory; it
does not need a feature PRD. A larger effort that spans several features may
keep its overall plan in `.scratch/<effort>/PLAN.md` or a wayfinding
`map.md`.

The `Status:` lines in `issues/` files are the authoritative work queue. Find
open work with:

```bash
rg -n '^Status: (needs-triage|needs-info|ready-for-agent|claimed|ready-for-human)$' \
  .scratch --glob '**/issues/*.md' --glob '!**/_template/**'
```

Status meanings are in
[`docs/agents/triage-labels.md`](../docs/agents/triage-labels.md). An
implementation ticket becomes `implemented` only after its documentation
effects and executed checks are recorded.

`_PORTFOLIO.md` (local, not versioned) summarizes every feature, technical
work item, and open ticket. Regenerate it with:

```bash
python3 scripts/scratch-status.py > .scratch/_PORTFOLIO.md
```

Work before 2026-11 was tracked as `tasks/TASK-*.md`; those files are kept,
read-only, in [`docs/archive/tasks/`](../docs/archive/tasks/).
