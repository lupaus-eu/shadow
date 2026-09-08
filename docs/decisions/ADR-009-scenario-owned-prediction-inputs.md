# ADR-009: Scenario-Owned Prediction Inputs

Status: Accepted

Date: 2026-08-26

---

# Context

Forecasting originally treated the protected Reality scenario as the source of
observed metric values. ADR-008 then permitted a selected planning scenario to
override a matching Reality value for the same period. TASK-042 changed
scenario forking so an independent fork now copies active events, timeseries
and their dated values through the selected organisation-state date.

Using Reality as a baseline after that fork leaves a scenario's copied history
partly unused and prevents forecasting a valid target whose Reality counterpart
is absent. It also makes a forecast depend on data outside the selected
scenario's independently editable branch.

# Decision

For every prediction target, Forecasting reads observed metric values only from
the selected target scenario's matching active numeric timeserie. It must not
read, merge, fall back to, impute from, or otherwise use Reality or another
scenario's values as a target, baseline input, or model-training value.

Reality is a normal active prediction target. When it is selected, it uses only
its own data. The Forecasting backend continues to enforce organisation scope,
active-row filtering and source isolation; UI selection is not the security
boundary.

Target metric eligibility requires a numeric target timeserie, finite target
values, and contiguous target history on the metric's time-unit grid under the
selected cutoff. Target-scenario events and graph history remain the only known
explanatory inputs. The current model kinds, deterministic configuration,
routes and resource limits are unchanged. ADR-012 later supersedes the
synchronous execution statement only; it preserves this source-isolation rule.

The cutoff API values are `asOfStart` and `allCurrentScenario`:

- `asOfStart` uses target-scenario observations strictly before the first
  generated metric period.
- `allCurrentScenario` uses all current active target-scenario observations and
  retains the existing future-knowledge disclosure for retrospective runs.

Prediction source snapshots record `observationPolicy: "targetScenarioOnly"`
and label every effective observation `targetScenario`. The obsolete dedicated
Reality-source persistence and response fields are removed. Development
prediction data need not be retained during this schema change.

# Consequences

Benefits:

- forked scenarios can forecast from their copied independent history;
- each prediction is fully isolated to its target scenario's values, events and
  graph history; and
- Reality can be forecast without special-case backend behavior.

Costs and constraints:

- a scenario with incomplete own history is ineligible even if Reality has
  complete values;
- existing development prediction records are discarded by the migration; and
- clients must use the renamed `allCurrentScenario` cutoff value.

# Supersedes

This ADR supersedes ADR-007's Reality-baseline, compatible-Reality-metric and
merged-history rules, and fully supersedes ADR-008's target-overrides-Reality
policy. ADR-007 remains authoritative for Forecasting ownership, immutable
results, model stack, execution bounds and all decisions not amended here.

# References

- `docs/decisions/ADR-007-predictions-forecasting-domain.md`
- `docs/decisions/ADR-008-target-scenario-observation-overrides.md`
- `docs/decisions/ADR-012-background-prediction-requests.md`
- `docs/domains/FORECASTING.md`
- `tasks/TASK-042-scenario-fork-timeseries-events-copy.md`
- `tasks/TASK-043-scenario-owned-prediction-inputs.md`
