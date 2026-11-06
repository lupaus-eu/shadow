# Contributing

Shadow is developed with AI agents using the same workflow as Yearclock.

1. Read [`AGENTS.md`](AGENTS.md) and [`CONTEXT.md`](CONTEXT.md).
2. Specify the work in `.scratch/` as described in
   [`FEATURE_WORKFLOW.md`](FEATURE_WORKFLOW.md): PRD, an optional domain
   model, a technical design, and small tickets. `.scratch/` stays on your
   machine.
3. Implement one ticket at a time on the local `main` and record the checks,
   the AI review, and the documentation updates in the ticket
   ([definition of done](docs/agents/definition-of-done.md)); commit it when
   it is done.
4. A human reviews the unpushed commits (`git log origin/main..main`) and
   pushes `main`; it is the only branch on GitHub. Images are built only from
   `v*` tags. Production releases need separate
   approval ([production runbook](docs/runbooks/production.md)).

The former process documents are archived in
[`docs/archive/process/`](docs/archive/process/).
