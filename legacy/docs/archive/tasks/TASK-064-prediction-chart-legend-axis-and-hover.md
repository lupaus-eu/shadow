# TASK-064 Prediction Chart Legend, Axis And Hover

## Source Plan

Developer-approved follow-up after reviewing a throwaway prototype for
overlapping prediction lines (2026-10-08). The prototype also tried widened
outlines for covered lines, overlap notes, legend highlighting and visibility
toggles; the developer discarded it and kept only the three changes below.
TASK-062 left the y-axis label rounding out of scope; the developer approved
adding it here.

## Goal

The comparison chart legend shows how each series is drawn, the y-axis range
labels are formatted the same way as the point hover values, and the point
hover text puts the value first and lists every series that has the point.
Together these make overlapping series easier to identify without changing the
plotted data.

## Requirements

### Legend Line Style

- Each legend entry shows a short sample line drawn in the same style as the
  series in the chart: its colour, its stroke width (the thicker Current
  Reality line stays thicker) and its dash pattern. Dashed series (currently
  Naive `7 4`, Average `2 4` and Prophet `10 3 2 3`) show as dashed, and solid
  series show as solid.
- The sample replaces the current colour swatch. It is decorative and hidden
  from assistive technology; the legend text is unchanged.
- The sample takes its style from the same line data the chart uses
  (`PredictionChartLine.strokeDasharray`, line kind and colour), so the legend
  and the chart cannot drift apart.

### Y-Axis Range Labels

- The y-axis maximum and minimum labels use the same display formatting as
  prediction point hover values (`formatPredictionPointValue`): at most two
  decimals without trailing zeros, `.` as the decimal separator, no grouping
  and never `-0`. For example `44` instead of `44.000` and `61.17` instead of
  `61.167`.
- This applies whichever series sets the range, including Current Reality and
  interval bounds.
- Display formatting only. Scaling and plotted positions are unchanged.

### Point Hover Text

The native hover text of a chart point is restructured into rows:

1. First row, alone: the point value and, when the hovered series has an
   available interval for the point, its lower and upper bound and the saved
   interval level, for example
   `30 EUR, lower bound 20 EUR, upper bound 40 EUR (80% prediction interval)`.
   Without an available interval the row is the value only, for example
   `28.125 EUR`.
2. Then one row per series in the chart that has that point, showing the
   series label. The hovered series is always included. Rows follow the
   chart's line order (the legend order).
3. Last row: the point date.

A series has the hovered point when its point overlaps the hovered point so
that the user cannot get a separate hover text for each of them: the points
are on the same date and the centres of their hover dots are less than the
dot radius (3 chart units in the SVG viewBox) apart vertically. Such a dot is
covered so far that its exposed part cannot be hovered reliably.

- The first row uses the hovered series' value and interval.
- If a listed series' own displayed value or interval text differs from the
  first row's, its row adds what differs in parentheses, for example
  `January plan · Future plan · Naive (no prediction interval)` or
  `January plan · Future plan · Average (30.4 EUR, no prediction interval)`.
- Values are shown with the existing rules: prediction values and bounds use
  `formatPredictionPointValue`, and Current Reality values stay as entered.
- The rule applies to visible dots and to the transparent hover targets of
  lines with 100 or more points.
- Rows are separated by newlines in the SVG `<title>`.
- The "point estimate" wording and the leading series label of the old format
  are removed.

## Acceptance Criteria

- [ ] Each legend entry shows a sample line with the series' colour, width and
      dash pattern; dashed series are dashed and solid series are solid.
- [ ] The y-axis maximum and minimum labels are formatted like prediction hover
      values, for example `44` rather than `44.000`.
- [ ] A point's hover text starts with its value and, if available, its bounds
      and interval level, alone on the first row.
- [ ] The hover text then lists, one row each, every series whose point on
      that date is less than the dot radius away from the hovered point,
      noting a differing value or interval in parentheses, and ends with the
      date.
- [ ] A series whose point on the same date can be hovered separately (centres
      at least the dot radius apart) is not listed.
- [ ] Plot geometry (line paths, dots, bands and scaling) is unchanged.

## Out Of Scope

- Detecting overlapping lines, widened outlines, overlap notes in the legend
  and changes to dot size or shape.
- Legend highlighting, series visibility toggles and other chart interaction.
- Changing line colours, dash patterns or the colour palette.
- Additional y-axis ticks or gridlines.
- A custom (non-native) tooltip component.
- Locale-aware number formatting.
- Backend, API or migration changes.

## Implementation Notes

Read before implementation:

```text
AGENTS.md
docs/architecture/overview.md
docs/architecture/domains/FORECASTING.md (prediction chart behaviour)
docs/operations/testing.md
```

- All changes are in `MetricChart` in
  `frontend/src/features/predictions/PredictionsTab.tsx`, its styles in
  `frontend/src/styles/components.css` and, for pure helpers,
  `frontend/src/features/predictions/predictionChart.ts`.
- The y-axis labels currently use `max.toPrecision(5)` and
  `min.toPrecision(5)`.
- The current legend swatch is a CSS block (`.prediction-chart__swatch` and
  `--reality`). A small inline SVG line is a natural replacement. Note that
  the chart's `.prediction-chart svg` rule (full width, background, radius)
  also matches an SVG inside the legend and must not apply to the sample.
- The hover text is built by `pointTitle`. Building the series rows needs a
  date-to-point lookup per line and the chart's `y` scale; keep it cheap for
  lines with many points (the chart already handles 100+ point lines). Use the
  existing dot radius (`r="3"`) as the threshold rather than a second
  constant, so the rule follows the dot size.
- No new dependencies.

## Testing

Required:

- [ ] Frontend tests:
  - `PredictionsTab.test.tsx`:
    - legend samples carry each series' dash pattern (dashed and solid) and
      colour;
    - the y-axis labels use the point formatting, including a range set by a
      bound or by Current Reality;
    - hover text for a point with an interval, without an interval, and for
      Current Reality;
    - hover text listing two series with identical points, including one
      whose interval differs;
    - hover text listing a series whose point is less than the dot radius
      away with its own value in parentheses, and not listing a series whose
      point on the same date is the dot radius or more away;
    - update existing expectations that use the old hover format
      (`point estimate …`) or the old axis format (`44.000`).
  - `predictionChart.test.ts`: any new pure helper.
- [ ] Manual verification: at `https://app.localhost`, compare saved versions
      whose lines overlap (for example two models with identical results) and
      check the legend samples, the axis labels and that hovering a shared
      point lists both series on separate rows.
- [ ] Lint
- [ ] Build

```bash
cd frontend
pnpm lint
pnpm test
pnpm build
python3 scripts/ai_review_records.py validate
```

## Documentation

- `docs/architecture/domains/FORECASTING.md`: update the chart paragraph to describe the
  legend line samples, the axis label formatting and the new hover text rows.
- `docs/operations/testing.md`: add the new frontend coverage to the Predictions UI
  section.

## Notes For AI Agent

- Use the branch `feature/TASK-064-prediction-chart-legend-axis-and-hover`.
- Save the redacted Step 13 review record under `docs/ai-reviews/TASK-064/`.
- Report all changed files and every verification command run.
