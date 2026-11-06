import type { YearclockEvent } from "../../organization-client";
import { DENSE_SERIES_THRESHOLD, rangeFractions, type PlanningWindow } from "../geometry";

export type PlacementLane = { id: string; name: string; tint?: string | null; height?: "normal" | "tall"; readOnly?: boolean; unavailable?: boolean };

/** An Event placed in the Planning Window: its Lane index, its span as fractions of the window, and whether it is clipped or part of a dense Series. */
export type Placed = {
  event: YearclockEvent;
  laneIndex: number;
  from: number;
  to: number;
  clippedStart: boolean;
  clippedEnd: boolean;
  dense: boolean;
};

/** Events visible in the window, in chronological then Lane order (the focus order of every display). */
export function placeEvents(events: YearclockEvent[], lanes: PlacementLane[], window: PlanningWindow): Placed[] {
  const laneIndex = new Map(lanes.map((lane, index) => [lane.id, index]));
  const seriesCounts = new Map<string, number>();
  for (const event of events) {
    if (event.series_id && !event.skipped) seriesCounts.set(event.series_id, (seriesCounts.get(event.series_id) ?? 0) + 1);
  }
  const placed: Placed[] = [];
  for (const event of events) {
    if (event.skipped) continue;
    const fractions = rangeFractions(event.starts_on, event.ends_on, window);
    const index = laneIndex.get(event.lane_id);
    if (!fractions || index === undefined) continue;
    placed.push({ event, laneIndex: index, ...fractions, dense: Boolean(event.series_id && (seriesCounts.get(event.series_id) ?? 0) >= DENSE_SERIES_THRESHOLD) });
  }
  return placed.sort((a, b) => a.event.starts_on.localeCompare(b.event.starts_on) || (a.event.starts_at ?? "").localeCompare((b.event.starts_at ?? "")) || a.laneIndex - b.laneIndex || a.event.id.localeCompare(b.event.id));
}
