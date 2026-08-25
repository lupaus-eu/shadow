# ADR-008: Target Scenario Observation Overrides

Status: Accepted

Date: 2026-08-25

---

# Context

ADR-007 made Reality the sole source of observed metric values. That prevents
planning-scenario data from leaking into another scenario, but it cannot model
the approved "possible past" use case: a user may enter scenario-specific
values for historical periods and expect that scenario's prediction to continue
from those values.

# Decision

For one prediction target, Forecasting constructs its observed history from
the compatible Reality metric and that target scenario's matching metric only.
If both have a value for the same valid metric period, the target scenario's
value overrides the Reality value for that period. Values from every other
non-Reality scenario remain prohibited.

The merged history is subject to the existing selected cutoff mode and must be
contiguous on the metric grid. `asOfStart` retains observations strictly before
the first generated period from either allowed source. The existing public
`allCurrentReality` cutoff-mode value is retained for API compatibility but now
uses all current observations from the two allowed sources; its saved metadata
must disclose the target-scenario override policy.

Forecasting snapshots every effective observation with its source (`reality` or
`targetScenario`) and retains the override policy. This keeps an immutable
version auditable after source rows change or are soft-deleted.

# Consequences

Benefits:

- historical scenario values can express and evaluate possible pasts;
- a target scenario remains isolated from every other planning scenario; and
- saved versions disclose exactly which source won for every period.

Costs and constraints:

- prediction output is no longer solely a projection of realized Reality;
- target-scenario values can deliberately diverge from Reality for historical
  dates; and
- clients must disclose the observation-source policy together with the
  existing cutoff-mode leakage disclosure.

# Supersedes

This ADR amends only ADR-007's sole-Reality observed-value rule and its related
baseline/training wording. It does not change Forecasting ownership, model
libraries, persistence ownership, execution bounds or the prohibition on using
other target scenarios' values.

# References

- `docs/decisions/ADR-007-predictions-forecasting-domain.md`
- `docs/domains/FORECASTING.md`
- `tasks/TASK-041B-predictions-backend-modeling.md`
