# ADR-010: Derived Metrics

Status: Accepted

Date: 2026-08-28

## Context

Scenario metrics need arithmetic values calculated from other scenario-owned
numeric metrics. Their short names are the user-facing formula identifiers.
Forecasting must show a derived metric without fitting a separate model to its
materialized history.

## Decision

The Organisation States Domain owns one soft-deletable equation per derived
Timeserie and materializes its values in `timeserie_values` with
`is_derived=true`. Formula operands are active normal numeric Timeseries in the
same scenario, must have a short name, and must share one time unit. Derived
formulas cannot reference other derived metrics.

Formula creation, formula changes and normal-source value replacement
recalculate the affected derived values transactionally. The materializer uses
the input-date intersection and skips invalid arithmetic dates. Referenced
source short names are locked until no active equation references them.

Forecasting first creates normal-metric result kinds, then applies the same
formula independently to matching normal result points for a derived target.
Forecasting never writes `timeserie_values` or trains a model directly from a
derived metric.

## Consequences

- Derived values are readable with other scenario metrics but not manually
  writable.
- Formula source dependencies are stored as internal Timeserie IDs for locking,
  recalculation and scenario-copy remapping.
- Mixed-grain formulas, unit conversion, resampling and dependency chains are
  intentionally deferred.
