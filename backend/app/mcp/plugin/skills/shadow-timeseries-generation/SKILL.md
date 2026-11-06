---
name: shadow-timeseries-generation
description: Choose units, time grains and realistic generator parameters for Shadow timeseries, preview them, align their dates and write derived-metric formulas. Use whenever you create Shadow timeseries or propose their values through the Shadow MCP server.
---

# Generating Shadow timeseries

You choose generation parameters; Shadow generates the numbers. Never type
long value lists yourself. Every proposal is staged in a change set and takes
effect only when a person applies it, in Shadow or, through
`apply_change_set`, here in the chat (see the model-building skill).

## Units and time grain

- `timeUnit` (`day`, `week`, `month`, `year`): match how the business measures
  and decides. Money, headcount and most KPIs are monthly, operational flows
  (tickets, deliveries) weekly, traffic and sales per day only when daily
  variation matters, strategic targets yearly.
- Series that a derived formula combines must share one time unit.
- Budget: one change set sets or generates at most 20,000 values in total. Three
  years of a daily series is 1,096 values, of a monthly series 36.
- `unit` is the label people see. Put the scale in it (`EUR`, `kEUR`, `FTE`,
  `%`, `customers`) and keep the values on that scale, for example `3.5` with
  `%`.
- `valueUnit` must be `number` for generated values and for every series a
  formula references.
- The spec's `timeUnit` must equal the timeserie's `timeUnit`.

## Realistic parameters

- **Level.** Start from the level the user gives or the recent values
  (`get_timeserie`). A related series should start near the existing one so
  there is no jump.
- **Trend.** `linear` for steady absolute change (+0.8 FTE a month), `percent`
  for compound growth, `logistic` for adoption that saturates, `none` for a
  stable KPI. `percentPerPeriod` compounds, so convert yearly growth with
  (1 + yearly growth) ^ (1 / periods a year) − 1: 20 % a year is about
  1.53 % a month, 0.35 % a week or 0.05 % a day.
- **Seasonality.** `multiplicative` when swings scale with the level (sales,
  traffic), with `amplitude` 0.05 to 0.3 (±5 % to ±30 %); `additive` for swings
  of a fixed size. `period` is in periods: 12 for a year of months, 52.18 for
  a year of weeks, 7 for a week of days, 365.25 for a year of days.
- **Peak.** Period index `t` is 0 at `startDate`, and a cycle peaks where
  `t` modulo `period` equals `peakOffset`. A monthly series from January
  peaks in December with `peakOffset` 11; in general the offset is the peak
  month minus the start month, modulo 12. A daily series starting on a Monday
  peaks on Friday with `peakOffset` 4.
- **Noise.** `relativeStd` 0.02 to 0.05 for financial aggregates and 0.05 to
  0.15 for daily operational counts. Use `std` instead for a series near zero,
  where relative noise vanishes. `ar1` 0.3 to 0.7 makes deviations persist
  like real data.
- **Bounds and rounding.** `clampMin: 0` for counts and money, `clampMax: 100`
  for percentages; `decimals: 0` for counts, people and money totals such
  as revenue or cost, 2 for prices, other small money amounts and ratios.
- **Steps.** `levelShifts` for permanent steps (an acquisition, a price
  change); add a `create_event` on the same date that explains it.
- **Seed.** Give each series its own seed so their noise differs. Keep the
  seed while tuning other parameters; it changes only the noise.

## Worked examples

Monthly revenue, about +20 % a year, peaking in December:

```json
{"startDate": "2026-01-01", "periods": 36, "timeUnit": "month",
 "baseLevel": 120000, "trend": {"type": "percent", "percentPerPeriod": 1.53},
 "seasonality": [{"period": 12, "amplitude": 0.12, "mode": "multiplicative",
                  "peakOffset": 11}],
 "noise": {"relativeStd": 0.03, "ar1": 0.4},
 "clampMin": 0, "decimals": 0, "seed": 101}
```

Monthly headcount with steady hiring and an acquisition of 25 people in July
2026 (pair it with an event on 2026-07-01):

```json
{"startDate": "2026-01-01", "periods": 36, "timeUnit": "month",
 "baseLevel": 40, "trend": {"type": "linear", "slope": 0.8},
 "levelShifts": [{"date": "2026-07-01", "delta": 25}],
 "noise": {"std": 0.6}, "clampMin": 0, "decimals": 0, "seed": 202}
```

Daily web visits from a Monday, busiest on Tuesdays, quieter in summer:

```json
{"startDate": "2026-01-05", "endDate": "2026-12-31", "timeUnit": "day",
 "baseLevel": 2000, "trend": {"type": "percent", "percentPerPeriod": 0.05},
 "seasonality": [{"period": 7, "amplitude": 0.25, "mode": "multiplicative",
                  "peakOffset": 1},
                 {"period": 365.25, "amplitude": 0.1, "mode": "multiplicative",
                  "peakOffset": 0}],
 "noise": {"relativeStd": 0.08, "ar1": 0.3},
 "clampMin": 0, "decimals": 0, "seed": 303}
```

Monthly active users of a new product, saturating near 5,000 with the
fastest growth after 18 months:

```json
{"startDate": "2026-01-01", "periods": 48, "timeUnit": "month",
 "baseLevel": 0,
 "trend": {"type": "logistic", "capacity": 5000, "growthRate": 0.35,
           "midpoint": 18},
 "noise": {"relativeStd": 0.02}, "clampMin": 0, "decimals": 0, "seed": 404}
```

Monthly churn in percent, slowly improving:

```json
{"startDate": "2026-01-01", "periods": 24, "timeUnit": "month",
 "baseLevel": 3.2, "trend": {"type": "linear", "slope": -0.03},
 "noise": {"std": 0.15}, "clampMin": 0, "clampMax": 100, "decimals": 2,
 "seed": 505}
```

## Date alignment

- `startDate` and every `levelShifts` date must be a period start: any day,
  a Monday, the 1st of a month or 1 January. `endDate` need not be aligned.
- Start series at or before the first organisation state's target date they
  describe, and place level shifts on the first period start the cause
  applies to: for a weekly series, the Monday on or after the event.
- Give the series that a formula combines the same `startDate` and length.
  A derived metric has values only on dates where every referenced series
  has one.

## Derived metrics

- `create_derived_metric` takes `name`, optional `unit` and a `formula` over
  the `shortName`s of numeric timeseries in the same scenario. Give every
  series you will reference a `shortName`: a letter, then letters, digits or
  underscores.
- Formulas use numbers, `+ - * /`, `**` (or `^`), unary minus and
  parentheses. There are no functions, and a formula cannot reference another
  derived metric.
- A date where the formula fails, such as a division by zero, has no value.
- The derived metric's time unit is that of its references, and its values
  follow theirs. Its key is server-generated: declare a `ref` to link it to a
  node with `patch_node` `timeserieId`.
- Examples: `revenue / headcount` (unit `EUR/FTE`),
  `(revenue - cost) / revenue * 100` (unit `%`).

## Always preview before staging

1. Call `preview_generated_timeserie` with the exact spec you will stage.
2. Check `min`, `max`, `mean`, `first_points` and `last_points` against what
   the user asked for: no negative counts, the end level matches the growth,
   the peak falls in the right period.
3. Adjust the parameters and preview again until it fits. Never edit values.
4. Summarise the preview for the user (start and end level, range), then
   stage the same spec with `generate_timeserie_values`. Submit freezes the
   generated values, so the reviewer sees exactly what will apply.

`set_timeserie_values` is for the few values the user gives explicitly, such
as actuals or targets. Both `set_timeserie_values` and
`generate_timeserie_values` replace **all** values of the timeserie, so do not
use them on a series with history unless the user wants it replaced.
`validate_change_set` flags such operations in `replacements`, but only in
scenarios that already exist: a series in a scenario this change set copies
keeps its history, and replacing it there is not flagged, so tell the user.
