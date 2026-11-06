# Summary Manual QA Checklist

Use this checklist for TASK-030 visual and cross-feature verification. Record
the tested environment and any deviations in the pull request.

## Context And Loading

- [ ] Open `/shadow/{orgId}/summary` with no scenario selected and confirm the
      no-scenario guidance is announced.
- [ ] Select a scenario without selecting an organisation state and confirm
      Summary loads and shows `Summary of {scenario name}`.
- [ ] Confirm the muted title metadata shows the displayed timeline start/end
      dates and updates its row count when visibility or filters change.
- [ ] Refresh the Summary data and confirm loading resolves without duplicating
      rows.
- [ ] Switch scenarios during loading and confirm only the newest scenario is
      rendered.
- [ ] Verify an API failure shows a useful error and Retry/Refresh recovers.
- [ ] Verify an empty scenario shows the empty timeline message.

## Timeline Data

- [ ] Verify nodes and edges with different `createDate` and `deleteDate`
      lifetimes render at the correct horizontal positions.
- [ ] Verify open-ended graph elements extend to the right timeline boundary.
- [ ] Verify edge bars use the target node type color and appear after their
      source node.
- [ ] Verify events render as green markers with date and detail hover text.
- [ ] Confirm node and event hover details do not expose their ids, and unknown
      node types do not expose raw node-type ids in Summary popovers.
- [ ] Verify node labels include their node type, edge labels end in `(Edge)`,
      and event and timeseries labels use `Event:` and `Timeserie:` prefixes.
- [ ] Verify positive, negative, mixed, zero and fractional numeric timeseries
      render with points, a zero baseline and an upper-left
      `Y min = … max = …` annotation containing the actual value range.
- [ ] Confirm numeric rows with valid data points use the peach background, but
      empty or invalid-only numeric rows do not.
- [ ] Hover across a numeric series and confirm the nearest date, value and unit
      are shown without the tooltip flickering as the pointer crosses it.
- [ ] Move more than 40 px away from every numeric point and confirm the tooltip
      disappears.
- [ ] Hover points near both visible timeline edges and confirm the tooltip stays
      fully inside the scroll viewport.
- [ ] Verify string, boolean and empty numeric series show explanatory text.
- [ ] Confirm malformed dates do not crash the page.
- [ ] Select an organisation state and confirm its target date is included in
      the timeline bounds.

## Controls And Layout

- [ ] Toggle Nodes and their edges, Edges, Events and Timeseries filters.
- [ ] Use node type All/None and individual type filters; confirm edges disappear
      when either endpoint type is excluded.
- [ ] Hide individual rows from the Rows menu; confirm both their labels and
      timeline content disappear. Confirm restoring a row individually or with
      All also expands it.
- [ ] Collapse individual rows from their row carets; confirm labels remain
      visible while timeline content folds away.
- [ ] Open Filters and Rows in turn; confirm opening one dropdown closes the
      other.
- [ ] Use minus, plus and the zoom slider; confirm the date header, rows and
      bottom scrollbar stay horizontally aligned and the pixels/days indicator
      tracks the selected zoom level.
- [ ] Choose Zoom to fit after zooming and scrolling; confirm the full current
      timeline fits and horizontal scrolling returns to the start.
- [ ] Zoom out with a long timeline; confirm January columns show only the year,
      other columns use abbreviated month names and labels do not overlap.
- [ ] Zoom in until wider labels fit; confirm every month shows both year and
      abbreviated month in `YYYY Mon` format.
- [ ] Continue zooming out until month labels no longer fit; confirm the header
      switches to year columns and vertical month guides appear in timeline rows.
- [ ] Confirm the Dec/Jan boundary is slightly darker than other month borders.
- [ ] Scroll vertically from both label and timeline columns and confirm they
      remain aligned.
- [ ] Resize all timeseries rows and confirm the minimum and maximum bounds.
- [ ] Narrow the workspace and confirm controls wrap and the timeline remains
      usable.
- [ ] Navigate controls with a keyboard and confirm names, focus behavior and
      expanded states are available to assistive technology.

## Temporal Structure Behavior

- [ ] Delete an earlier-created edge from Structure and confirm it remains
      visible on the selected target date but not after it.
- [ ] Delete an earlier-created node and confirm connected edges receive
      compatible logical end dates.
- [ ] Delete a node or edge on its creation date and confirm it is
      persistence-soft-deleted and does not reappear after refresh. Confirm
      same-day node deletion also persistence-soft-deletes connected edges.
- [ ] Confirm logically deleted elements remain in Summary history.
- [ ] Delete or clean the owning scenario through the persistence flow and
      confirm its graph elements no longer appear in history.
