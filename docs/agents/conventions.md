# Agent Conventions

- Read `AGENTS.md` before implementation changes and use architecture routing
  for feature-specific source documents.
- Prefer narrow, verifiable vertical slices.
- Update `.env.example` when configuration changes.
- Update architecture documentation when service boundaries, ports, deployment,
  data ownership, integration seams, or core dependencies change.
- Record every selected documentation update and every executed verification in
  the implementation ticket before marking it `implemented`.
- Keep Yearclock business vocabulary aligned with `CONTEXT.md`.
- Do not commit secrets, generated dependency folders, local databases, virtual
  environments, or caches.
