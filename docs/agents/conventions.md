# Agent Conventions

- Read `AGENTS.md` before implementation changes and use architecture routing
  for feature-specific source documents.
- Prefer narrow, verifiable vertical slices.
- Update `.env.example` when configuration changes, and the production env
  contract in `docs/architecture/deployment.md` when production needs it.
- Update architecture documentation when service boundaries, ports, deployment,
  data ownership, integration seams, or core dependencies change.
- Update the PlantUML sources and the generated SVGs in
  `docs/architecture/diagrams/` (`make diagrams`) when an architecture, domain,
  or workflow diagram changes.
- Record every selected documentation update, every executed verification, and
  the AI review in the implementation ticket before marking it `implemented`.
- Keep Shadow business vocabulary aligned with `CONTEXT.md`.
- Do not commit secrets, generated dependency folders, local databases, virtual
  environments, caches, or anything under `.scratch/` other than its README and
  templates.
- Do not add a dependency, delete a test, change the architecture without an
  ADR, or touch production without human approval.
- Merge a finished ticket's branch into the local `main` yourself, but never
  push: the human pushes `main`.
