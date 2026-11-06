/** Pure helpers of the PNG export (Yearclock V2 P7): sizes, legend layout, and the file name. */

export const IMAGE_SCALE = 2;
export const IMAGE_PADDING = 24;
export const TITLE_PX = 56;
export const LEGEND_ROW_PX = 22;

export type LegendEntry = { label: string; color?: string };
export type PlacedLegendEntry = LegendEntry & { x: number; row: number; width: number };

/** Flow legend entries (swatch, gap, label) into rows no wider than `maxWidth`. */
export function layoutLegend(entries: LegendEntry[], maxWidth: number, measure: (text: string) => number, swatch = 14, gap = 6, spacing = 18): { entries: PlacedLegendEntry[]; rows: number } {
  const placed: PlacedLegendEntry[] = [];
  let x = 0;
  let row = 0;
  for (const entry of entries) {
    const width = (entry.color ? swatch + gap : 0) + measure(entry.label);
    if (x > 0 && x + width > maxWidth) { row += 1; x = 0; }
    placed.push({ ...entry, x, row, width });
    x += width + spacing;
  }
  return { entries: placed, rows: entries.length ? row + 1 : 0 };
}

/** The canvas size in device pixels for an SVG shown at `svgPx`, with a title above and a legend of `legendRows` rows below. */
export function canvasSize(svgPx: number, legendRows: number): { width: number; height: number; legendTop: number } {
  const width = Math.round(svgPx + IMAGE_PADDING * 2);
  const legendTop = IMAGE_PADDING + TITLE_PX + svgPx + 12;
  const height = legendTop + legendRows * LEGEND_ROW_PX + IMAGE_PADDING;
  return { width: width * IMAGE_SCALE, height: height * IMAGE_SCALE, legendTop };
}

/** `northwind-yearclock-2026-01-01.png`: accents and symbols removed, so the name is safe on every system. */
export function imageFileName(yearclockName: string, windowStart: string): string {
  const slug = yearclockName.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
  return `${slug || "yearclock"}-${windowStart}.png`;
}
