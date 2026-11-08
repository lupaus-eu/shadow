import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

// WCAG 2.1 contrast of the token pairs the Structure canvas draws text and controls with (panels, toolbar, caption, badges, popover, ghosts).
// The tokens are read from `src/theme.css`. There is no dark theme yet (no `prefers-color-scheme` or `data-theme` rule): when one is added it
// must add its own token block here, and this test fails until it does (see the last test).
const css = readFileSync(resolve(process.cwd(), "src/theme.css"), "utf8");
const tokens = new Map([...css.matchAll(/--color-([a-z-]+):\s*(#[0-9a-fA-F]{6})\s*;/g)].map((match) => [match[1], match[2]]));

function luminance(hex: string): number {
  const channel = (offset: number) => {
    const value = parseInt(hex.slice(1 + offset, 3 + offset), 16) / 255;
    return value <= 0.03928 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * channel(0) + 0.7152 * channel(2) + 0.0722 * channel(4);
}
export function contrast(a: string, b: string): number {
  const [light, dark] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (light + 0.05) / (dark + 0.05);
}
const ratio = (foreground: string, background: string) => {
  const [fg, bg] = [tokens.get(foreground), tokens.get(background)];
  if (!fg || !bg) throw new Error(`unknown token ${foreground} or ${background}`);
  return contrast(fg, bg);
};

// Text: foreground on background, 4.5:1 (AA).
const TEXT: [string, string, string][] = [
  ["ink", "surface", "panels, labels, node names"],
  ["ink", "canvas", "page"],
  ["ink-muted", "surface", "descriptions, counts, hints, connection labels"],
  ["ink-muted", "surface-subtle", "toolbar hover"],
  ["ink", "surface-sunken", "row hover"],
  ["ink", "accent-soft", "selected row"],
  ["accent", "accent-soft", "pressed toggle button"],
  ["accent", "surface", "links"],
  ["warning-ink", "surface", "Planned label on the caption"],
  ["warning-ink", "warning-soft", "planned notice"],
  ["info-ink", "surface", "Scenario caption accent text"],
  ["info-ink", "info-soft", "info alerts"],
  ["danger", "surface", "delete buttons, refusals"],
  ["danger", "danger-soft", "alerts"],
  ["success-ink", "success-soft", "saved"],
];
// Controls and graphics: 3:1 (AA for user interface components and meaningful graphics).
const UI: [string, string, string][] = [
  ["line-strong", "surface", "control borders, popover border"],
  ["accent", "surface", "focus ring, selection outline, match outline"],
  ["accent", "canvas", "focus ring on the page"],
  ["ink-muted", "surface", "connection lines, ghost outlines, arrowheads"],
  ["ink", "surface", "change badge outline and glyph"],
];

describe("canvas colour tokens (light theme)", () => {
  it("reads the tokens", () => { expect(tokens.size).toBeGreaterThan(20); });
  it.each(TEXT)("text %s on %s reaches 4.5:1 (%s)", (foreground, background) => {
    expect(ratio(foreground, background)).toBeGreaterThanOrEqual(4.5);
  });
  it.each(UI)("graphic %s on %s reaches 3:1 (%s)", (foreground, background) => {
    expect(ratio(foreground, background)).toBeGreaterThanOrEqual(3);
  });
  it("has no dark theme to test", () => {
    expect(/prefers-color-scheme\s*:\s*dark|data-theme/.test(css)).toBe(false);
  });
});
