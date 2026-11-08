/** Pure helpers for how a node and a connection are drawn: geometry, label text and colour. No diagram-js here, so they are easy to test. */

export const NODE_WIDTH = 160;
export const NODE_HEIGHT = 56;
export const FALLBACK_FILL = "#dddddd";
/** A name longer than this is shortened with an ellipsis in labels (PRD: structure canvas). The full name shows in the details panel. */
export const MAX_LABEL_CODE_POINTS = 60;

export type ShapeKind = "rectangle" | "roundrectangle" | "ellipse" | "diamond" | "hexagon";
export type Point = { x: number; y: number };

/** The shape of a node type. An unknown or empty value is a rounded rectangle, the default. */
export function shapeKind(value: string | null | undefined): ShapeKind {
  const key = (value ?? "").toLowerCase().replace(/[\s_-]/g, "");
  if (key === "rectangle" || key === "rect") return "rectangle";
  if (key === "ellipse" || key === "circle") return "ellipse";
  if (key === "diamond") return "diamond";
  if (key === "hexagon") return "hexagon";
  return "roundrectangle";
}

/** At most 60 code points: a longer name keeps its first 59 and ends with an ellipsis, so the result is exactly 60 code points. Counts code points, not UTF-16 units, so an emoji is one. */
export function shortenName(name: string, max = MAX_LABEL_CODE_POINTS): string {
  const points = Array.from(name);
  return points.length <= max ? name : `${points.slice(0, max - 1).join("")}…`;
}

/** Breaks a label into lines of at most `lineLength` characters (words are kept whole when they fit); what does not fit in `maxLines` ends with an ellipsis. */
export function wrapLabel(text: string, lineLength: number, maxLines: number): string[] {
  const words = text.split(/\s+/).filter(Boolean).flatMap((word) => {
    const points = Array.from(word);
    const parts: string[] = [];
    for (let at = 0; at < points.length; at += lineLength) parts.push(points.slice(at, at + lineLength).join(""));
    return parts;
  });
  const lines: string[] = [];
  let current = "";
  for (const word of words) {
    if (!current) current = word;
    else if (Array.from(current).length + 1 + Array.from(word).length <= lineLength) current += ` ${word}`;
    else { lines.push(current); current = word; }
  }
  if (current) lines.push(current);
  if (lines.length <= maxLines) return lines;
  const kept = lines.slice(0, maxLines);
  const last = Array.from(kept[maxLines - 1]);
  kept[maxLines - 1] = `${(last.length >= lineLength ? last.slice(0, lineLength - 1) : last).join("")}…`;
  return kept;
}

function luminance(hex: string): number | null {
  const match = /^#([0-9a-f]{3}|[0-9a-f]{6})$/i.exec(hex.trim());
  if (!match) return null;
  const digits = match[1].length === 3 ? [...match[1]].map((digit) => digit + digit).join("") : match[1];
  const [r, g, b] = [0, 2, 4].map((at) => {
    const channel = parseInt(digits.slice(at, at + 2), 16) / 255;
    return channel <= 0.03928 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

/** Dark or white text, whichever contrasts more with the node colour. A colour that is not a hex value gets dark text. */
export function contrastingInk(fill: string): string {
  const light = luminance(fill);
  if (light === null) return "#111827";
  const against = (other: number) => (Math.max(light, other) + 0.05) / (Math.min(light, other) + 0.05);
  return against(1) > against(luminance("#111827") ?? 0) ? "#ffffff" : "#111827";
}

/** The outline of a shape as an SVG path in the coordinates of its top-left corner (`x`, `y`); also used to crop connections at the border. */
export function shapePath(kind: ShapeKind, width: number, height: number, x = 0, y = 0): string {
  const p = (dx: number, dy: number) => `${x + dx},${y + dy}`;
  switch (kind) {
    case "ellipse": {
      const rx = width / 2;
      const ry = height / 2;
      return `M${p(0, ry)} a${rx},${ry} 0 1,0 ${width},0 a${rx},${ry} 0 1,0 ${-width},0 Z`;
    }
    case "diamond":
      return `M${p(width / 2, 0)} L${p(width, height / 2)} L${p(width / 2, height)} L${p(0, height / 2)} Z`;
    case "hexagon": {
      const inset = Math.min(width * 0.2, height / 2);
      return `M${p(inset, 0)} L${p(width - inset, 0)} L${p(width, height / 2)} L${p(width - inset, height)} L${p(inset, height)} L${p(0, height / 2)} Z`;
    }
    default:
      // A rounded rectangle is cropped at its sharp corners; the 8 px rounding does not matter for where a line touches.
      return `M${p(0, 0)} L${p(width, 0)} L${p(width, height)} L${p(0, height)} Z`;
  }
}

/** The corner points of an arrowhead whose tip is `tip`, pointing along the line that comes from `from`. */
export function arrowHead(from: Point, tip: Point, size = 10): Point[] {
  const angle = Math.atan2(tip.y - from.y, tip.x - from.x);
  const spread = Math.PI / 7;
  const wing = (offset: number) => ({ x: tip.x - size * Math.cos(angle + offset), y: tip.y - size * Math.sin(angle + offset) });
  return [tip, wing(-spread), wing(spread)];
}

/** Distance between two parallel connections of the same pair of nodes, in canvas units. */
export const PARALLEL_SPACING = 18;

/**
 * How far the `index`-th of `count` connections between two nodes is moved sideways so they do not lie on each other: the offsets are
 * centred on the straight line (one connection stays on it), spaced `PARALLEL_SPACING` apart, and perpendicular to the line from `from`
 * to `to`. The caller passes the two nodes in a fixed order (by id), so a connection in the opposite direction lands on the other side.
 */
export function parallelShift(index: number, count: number, from: Point, to: Point, spacing = PARALLEL_SPACING): Point {
  if (count <= 1) return { x: 0, y: 0 };
  const length = Math.hypot(to.x - from.x, to.y - from.y);
  if (length === 0) return { x: 0, y: 0 };
  const amount = (index - (count - 1) / 2) * spacing;
  // `+ 0` turns a negative zero into zero.
  return { x: (-(to.y - from.y) / length) * amount + 0, y: ((to.x - from.x) / length) * amount + 0 };
}

export const toPoints = (points: Point[]) => points.map((point) => `${Math.round(point.x * 100) / 100},${Math.round(point.y * 100) / 100}`).join(" ");
