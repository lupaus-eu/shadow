---
status: accepted
---

# Add Prophet as a forecasting method

## Context

Forecasts used three in-house methods (linear, seasonal, Holt) because a library such as Prophet needed a new dependency. Users with longer histories want a method that handles trend changes and yearly seasonality, with uncertainty bands.

## Decision

- Add `prophet==1.5.0` and a fourth method `prophet` next to the others. It needs at least 12 months of history, fits monthly data (`MS`) with a 95 % interval, and enables yearly seasonality from 24 months.
- Import Prophet lazily inside the method, so the other methods and the test suite do not pay its start-up cost.
- `simulations.method` allows `prophet` (migration 0056).

## Consequences

- The backend image grows and the first Prophet fit takes several seconds.
- The pure-Python methods stay as the default and as fallback for short histories.
