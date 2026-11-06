/** Pure layout helpers of the timeline display (Yearclock V2 P5). Positions are fractions of the Planning Window. */

export const PX_PER_MONTH = 64;
export const MIN_CONTENT_PX = 720;
export const MARKER_PX = 14;
export const DENSE_MARKER_PX = 8;
export const LABEL_CHAR_PX = 6.5;
export const LABEL_MAX_PX = 168;

/** The width the lanes' content is laid out at (it grows with the window, and never shrinks below the minimum). */
export const contentWidth = (months: number): number => Math.max(months * PX_PER_MONTH, MIN_CONTENT_PX);

/** The space a single-day Event needs: its marker and, unless dense, its title. */
export function markerSlotPx(title: string, labelled: boolean): number {
  return MARKER_PX + (labelled ? 6 + Math.min(title.length * LABEL_CHAR_PX, LABEL_MAX_PX) : 0);
}

export type Slot = { key: string; from: number; to: number; minPx: number };

/**
 * Pack slots into tracks so that nothing overlaps at `widthPx`: each slot takes
 * the first track free at its start. A slot covers its range, and at least
 * `minPx`, from its left edge.
 */
export function packTracks(slots: Slot[], widthPx: number): { track: Map<string, number>; count: number } {
  const track = new Map<string, number>();
  const ends: number[] = [];
  for (const slot of [...slots].sort((a, b) => a.from - b.from || a.to - b.to || a.key.localeCompare(b.key))) {
    const left = slot.from * widthPx;
    const right = Math.max(slot.to * widthPx, left + slot.minPx);
    let index = ends.findIndex((end) => end <= left + 0.5);
    if (index < 0) { index = ends.length; ends.push(0); }
    ends[index] = right + 2;
    track.set(slot.key, index);
  }
  return { track, count: ends.length };
}

const DAY_MS = 86_400_000;

/** The all-day date at a horizontal fraction of the window (clamped to the window). */
export function dateAtFraction(windowStart: string, days: number, fraction: number): string {
  const day = Math.min(Math.max(Math.floor(fraction * days), 0), days - 1);
  return new Date(Date.parse(`${windowStart}T00:00:00Z`) + day * DAY_MS).toISOString().slice(0, 10);
}

/** True when the window covers more than one calendar year, so month labels carry the year. */
export const crossesYear = (windowStart: string, windowEnd: string): boolean => windowStart.slice(0, 4) !== windowEnd.slice(0, 4);

/** Which header rows the axis shows: months always, weeks for windows up to 3 months or when enabled, days for 1 month, quarters when enabled. */
export function axisRows(months: number, showWeeks: boolean, showQuarters: boolean): { quarters: boolean; weeks: boolean; days: boolean } {
  return { quarters: showQuarters, weeks: showWeeks || months <= 3, days: months === 1 };
}
