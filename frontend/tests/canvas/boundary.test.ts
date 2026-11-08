import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const canvas = join(import.meta.dirname, "../../src/models/canvas");
const files = (dir: string): string[] => readdirSync(dir, { withFileTypes: true }).flatMap((entry) => (entry.isDirectory() ? files(join(dir, entry.name)) : [join(dir, entry.name)]));

describe("the canvas is a view of plain graph data", () => {
  // `useGraphState.ts` is the one seam that may know about lines and changes.
  const view = files(canvas).filter((file) => !file.endsWith("useGraphState.ts"));

  it("imports no line, change or version types and no server calls outside the hook", () => {
    expect(view.length).toBeGreaterThan(6);
    for (const file of view) {
      const source = readFileSync(file, "utf8");
      const imports = [...source.matchAll(/import[^;]*?from\s+"([^"]+)"/gs)].map((match) => ({ path: match[1], text: match[0] }));
      for (const { path, text } of imports) {
        if (!/(^|\/)client$/.test(path)) continue;
        expect(text, `${file} may only take plain graph types from the client`).toMatch(/^import type /);
        expect(text, file).not.toMatch(/\b(LineChange|ModelLine|Version\w*|ModelSummary)\b/);
      }
    }
  });
});
