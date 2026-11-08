import type { Bounds } from "./view";

/**
 * Export of the Structure canvas as SVG and PNG. The SVG is the canvas's own `<svg>` cloned: the viewport transform is dropped so the
 * whole graph is in view, what is hidden (a hidden type and its connections) and what only helps editing (selection outlines, hit
 * areas) is removed, and a `<style>` element carries the few rules the drawing needs, with the theme's colours resolved to values, so
 * the file looks the same outside the page. The PNG draws that SVG onto a canvas. Everything that touches the DOM takes it as a parameter.
 */

/** Space around the graph in the exported image, in canvas units. */
export const EXPORT_PADDING = 24;
/** The PNG is drawn at this multiple of the SVG's size, unless that would be too large for a canvas. */
export const PNG_SCALE = 2;
const MAX_PNG_SIDE = 16000;
const SVG_NS = "http://www.w3.org/2000/svg";

/** Theme colours the exported drawing needs, as resolved values. */
export type ExportTokens = { ink: string; inkMuted: string; surface: string; accent: string; font: string };
export const DEFAULT_TOKENS: ExportTokens = { ink: "#17212B", inkMuted: "#56636E", surface: "#FFFFFF", accent: "#0F766E", font: "Inter, system-ui, -apple-system, 'Segoe UI', Arial, sans-serif" };

/** Reads the tokens from CSS custom properties through `read` (for example `getComputedStyle(document.documentElement).getPropertyValue`); a missing or odd value keeps the default. */
export function resolveTokens(read: (name: string) => string): ExportTokens {
  const pick = (name: string, fallback: string) => { const value = read(name).trim(); return /^(#[0-9a-f]{3,8}|rgba?\([\d\s.,%/]+\)|hsla?\([\d\s.,%/deg]+\))$/i.test(value) ? value : fallback; };
  return { ink: pick("--color-ink", DEFAULT_TOKENS.ink), inkMuted: pick("--color-ink-muted", DEFAULT_TOKENS.inkMuted), surface: pick("--color-surface", DEFAULT_TOKENS.surface), accent: pick("--color-accent", DEFAULT_TOKENS.accent), font: DEFAULT_TOKENS.font };
}

/** The rules of the drawing, the same as in `theme.css` for the canvas but with resolved colours and without selection or hover. */
export function exportStyles(tokens: ExportTokens): string {
  return [
    `svg{font-family:${tokens.font}}`,
    ".shadow-node-body{stroke:#4b5563;stroke-width:1}",
    ".shadow-added .shadow-node-body,.shadow-updated .shadow-node-body{stroke-dasharray:5 3}",
    `.shadow-match .shadow-node-body{stroke:${tokens.accent};stroke-width:2.5}`,
    ".shadow-dim{opacity:.3}",
    `.shadow-connection-line{fill:none;stroke:${tokens.inkMuted};stroke-width:1.5}`,
    `.shadow-connection-arrow{fill:${tokens.inkMuted};stroke:none}`,
    `.shadow-connection-label{fill:${tokens.inkMuted};stroke:${tokens.surface};stroke-width:3px;paint-order:stroke}`,
    `.shadow-change-badge circle{fill:${tokens.surface};stroke:${tokens.ink};stroke-width:1.5}`,
    `.shadow-change-badge text{fill:${tokens.ink}}`,
    `.shadow-ghost-body{fill:${tokens.surface};stroke:${tokens.inkMuted};stroke-width:1.5;stroke-dasharray:5 4}`,
    `.shadow-ghost-line{stroke:${tokens.inkMuted};stroke-width:1.5;stroke-dasharray:5 4}`,
    `.shadow-ghost-label{fill:${tokens.inkMuted};stroke:${tokens.surface};stroke-width:3px;paint-order:stroke}`,
  ].join("\n");
}

/** Classes and elements that only exist for editing and do not belong in an image. */
const EDITING_ONLY = [".djs-outline", ".djs-hit", ".djs-hit-all", ".djs-hit-stroke", ".djs-hit-click-stroke", ".djs-resizer", ".djs-bendpoint", ".djs-segment-dragger", ".djs-dragger", ".djs-crosshair-group", ".djs-snap-line", ".djs-visual-hidden"];
const HIDDEN = ".shadow-hidden";
const EDITING_ATTRIBUTES = ["tabindex", "role", "style"];


export type ExportedSvg = { svg: string; width: number; height: number };

/**
 * Serialises the drawing in `source` (the canvas's `<svg>`) for the area `bounds`, grown by `padding`. Returns null when there is nothing
 * to draw (`bounds` is null). `source` is not changed.
 */
export function buildExportSvg(source: SVGSVGElement, bounds: Bounds | null, options: { title: string; tokens?: ExportTokens; padding?: number }): ExportedSvg | null {
  if (!bounds) return null;
  const padding = options.padding ?? EXPORT_PADDING;
  const viewport = source.querySelector<SVGGElement>(":scope > .viewport") ?? source.querySelector<SVGGElement>(".viewport");
  if (!viewport) return null;
  const drawing = viewport.cloneNode(true) as SVGGElement;
  drawing.removeAttribute("transform");
  // A hidden type stays hidden: its elements are not in the file at all.
  for (const element of Array.from(drawing.querySelectorAll(HIDDEN))) element.remove();
  for (const element of Array.from(drawing.querySelectorAll(EDITING_ONLY.join(",")))) element.remove();
  for (const element of Array.from(drawing.querySelectorAll("*"))) {
    element.classList.remove("selected", "hover", "djs-hover", "djs-focused", "djs-dragging");
    for (const name of EDITING_ATTRIBUTES) element.removeAttribute(name);
  }
  const x = Math.floor(bounds.x - padding), y = Math.floor(bounds.y - padding);
  const width = Math.ceil(bounds.width + 2 * padding), height = Math.ceil(bounds.height + 2 * padding);
  const tokens = options.tokens ?? DEFAULT_TOKENS;
  const wrapper = source.ownerDocument.createElementNS(SVG_NS, "svg");
  wrapper.setAttribute("viewBox", `${x} ${y} ${width} ${height}`);
  wrapper.setAttribute("width", String(width));
  wrapper.setAttribute("height", String(height));
  wrapper.setAttribute("role", "img");
  const title = source.ownerDocument.createElementNS(SVG_NS, "title");
  title.textContent = options.title;
  const style = source.ownerDocument.createElementNS(SVG_NS, "style");
  style.textContent = exportStyles(tokens);
  const background = source.ownerDocument.createElementNS(SVG_NS, "rect");
  for (const [name, value] of Object.entries({ x, y, width, height, fill: tokens.surface })) background.setAttribute(name, String(value));
  wrapper.append(title, style, background, drawing);
  return { svg: `<?xml version="1.0" encoding="UTF-8"?>\n${new XMLSerializer().serializeToString(wrapper)}`, width, height };
}

/** Characters no file name may hold on a common system, and control characters. */
// eslint-disable-next-line no-control-regex
const UNSAFE = /[\\/:*?"<>|\u0000-\u001f\u007f]+/g;
const RESERVED = /^(con|prn|aux|nul|com[1-9]|lpt[1-9])$/i;
const MAX_NAME = 80;

/** One part of a file name: letters, digits, dot, dash and underscore stay, spaces and everything else become one dash; no dot or dash at either end. Empty when nothing is left. */
export function sanitizeNamePart(value: string): string {
  const clean = value.normalize("NFC").replace(UNSAFE, " ").replace(/[^\p{L}\p{N}._-]+/gu, "-").replace(/-{2,}/g, "-").replace(/^[.\-_]+|[.\-_]+$/g, "");
  return Array.from(clean).slice(0, MAX_NAME).join("");
}

/** The file name without extension: the model's name and the line's name, sanitised ("model" when both are empty). */
export function exportFileBase(modelName: string, lineName: string): string {
  const parts = [sanitizeNamePart(modelName), sanitizeNamePart(lineName)].filter(Boolean);
  const base = parts.length ? parts.join("-") : "model";
  return RESERVED.test(base) ? `model-${base}` : base;
}

export const exportFileName = (modelName: string, lineName: string, extension: "svg" | "png") => `${exportFileBase(modelName, lineName)}.${extension}`;

/** The scale a PNG of this size is drawn at: `PNG_SCALE`, less when the image would pass the largest size a canvas can have. */
export function pngScale(width: number, height: number, wanted = PNG_SCALE): number {
  return Math.max(0.1, Math.min(wanted, MAX_PNG_SIDE / Math.max(1, width, height)));
}

/** Draws a serialised SVG onto a canvas at `scale` and returns it as a PNG file. Rejects when the browser cannot load the image or encode it. */
export function svgToPng(exported: ExportedSvg, scale = pngScale(exported.width, exported.height)): Promise<Blob> {
  return new Promise((resolve, reject) => {
    // A data: URL, not a blob: one: the page's Content-Security-Policy allows images from 'self' and data: only (caddy/Caddyfile).
    const url = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(exported.svg)}`;
    const image = new Image();
    image.onload = () => {
      try {
        const canvas = document.createElement("canvas");
        canvas.width = Math.round(exported.width * scale);
        canvas.height = Math.round(exported.height * scale);
        const context = canvas.getContext("2d");
        if (!context) throw new Error("no 2d context");
        context.drawImage(image, 0, 0, canvas.width, canvas.height);
        canvas.toBlob((blob) => (blob ? resolve(blob) : reject(new Error("PNG encoding failed"))), "image/png");
      } catch (error) {
        reject(error);
      }
    };
    image.onerror = () => reject(new Error("the SVG could not be loaded as an image"));
    image.src = url;
  });
}

/** Hands a file to the browser's download. */
export function downloadBlob(blob: Blob, fileName: string): void {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = fileName;
  link.style.display = "none";
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
}

export const svgBlob = (exported: ExportedSvg) => new Blob([exported.svg], { type: "image/svg+xml;charset=utf-8" });
