# Architecture Decision Records

Create one Markdown file per durable architecture decision, numbered in
sequence:

```text
NNNN-short-imperative-title.md
```

Each new ADR starts with YAML front matter and a title:

```markdown
---
status: accepted
---

# Use PostgreSQL row-level security for tenant isolation
```

Allowed statuses:

- `proposed` — under discussion
- `accepted` — in force
- `deferred` — accepted in principle but outside the current release
- `superseded` — replaced; name the replacing ADR in the body

The body states the decision and its reasoning in one or a few short
paragraphs. Cover the context that forced the decision and its main
consequences or trade-offs. When a later ADR refines or replaces an earlier
one, add a closing line to both that names the other.

Write an ADR when choosing a new technology, changing the architecture, the
database strategy, or the deployment model, or adding a significant external
integration.

## Existing decisions

ADRs 0001–0015 were written before this format, as `docs/decisions/ADR-NNN-*.md`
following [`_legacy-template.md`](_legacy-template.md). They keep their own
`Status` sections and are still cited as `ADR-NNN` (for example ADR-013 is
[`0013-shared-entra-local-https-deployment.md`](0013-shared-entra-local-https-deployment.md)).
Number new ADRs from 0016 onward in the format above.

| ADR | Decision |
| --- | --- |
| [0001](0001-tech-stack.md) | Technology stack |
| [0002](0002-database-migrations.md) | Database migrations |
| [0003](0003-coolify-deployment.md) | Coolify deployment (superseded by ADR-013) |
| [0004](0004-authentication.md) | Authentication |
| [0005](0005-production-only-environments.md) | Production-only environments |
| [0006](0006-local-authentik-entra-federation.md) | Local Authentik–Entra federation (superseded by ADR-013) |
| [0007](0007-predictions-forecasting-domain.md) | Predictions and the Forecasting domain |
| [0008](0008-target-scenario-observation-overrides.md) | Target-scenario observation overrides |
| [0009](0009-scenario-owned-prediction-inputs.md) | Scenario-owned prediction inputs |
| [0010](0010-derived-metrics.md) | Derived metrics |
| [0011](0011-prediction-intervals.md) | Prediction intervals |
| [0012](0012-background-prediction-requests.md) | Background prediction requests |
| [0013](0013-shared-entra-local-https-deployment.md) | Shared Entra, local HTTPS, and UpCloud deployment |
| [0014](0014-prophet-and-model-selection.md) | Prophet and model selection |
| [0015](0015-ai-via-mcp.md) | AI via MCP |
| [0016](0016-introduce-tenants-memberships-and-rls.md) | Tenants, memberships and row-level security |
| [0017](0017-use-self-hosted-authentik-for-identity.md) | Self-hosted Authentik for identity; Microsoft Entra removed |
| [0019](0019-platform-services-worker-audit-email.md) | Platform services: audit log, worker and outbox, email, notifications (proposed) |
| [0023](0023-authorize-mcp-clients-with-a-dedicated-authentik-provider.md) | MCP clients authorized by a dedicated Authentik provider |
