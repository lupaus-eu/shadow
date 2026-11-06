import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

// The Authentik sign-in pages bridge the application's tokens (ADR-0039). If a token is renamed or
// changes value, the bridge's variables or fallbacks would silently drift from the application.
const theme = readFileSync(new URL("../../src/theme.css", import.meta.url), "utf8");
const bridge = readFileSync(new URL("../../../authentik/blueprints/yearclock-brand.css", import.meta.url), "utf8");

const tokens = new Map([...theme.matchAll(/^\s*(--[a-z0-9-]+):\s*(.+?);\s*$/gm)].map((match) => [match[1], match[2]]));
const uses = [...bridge.matchAll(/var\((--[a-z0-9-]+),\s*([^;]+?)\)\s*[;}]/g)].map((match) => ({ name: match[1], fallback: match[2].trim() }));

test("the bridge uses at least the colour, type, shape tokens it needs", () => {
  assert.ok(uses.length >= 15, `found ${uses.length} token uses`);
});

test("every token the bridge reads exists in theme.css", () => {
  for (const { name } of uses) assert.ok(tokens.has(name), `${name} is not defined in theme.css`);
});

test("every fallback in the bridge equals the token's value", () => {
  const normalize = (value: string) => value.replace(/\s+/g, " ").trim().toLowerCase();
  for (const { name, fallback } of uses) assert.equal(normalize(fallback), normalize(tokens.get(name) ?? ""), `${name}: fallback differs from theme.css`);
});

test("the sign-in pages show no background image and stay scoped to flow pages", () => {
  assert.match(bridge, /--ak-global--background-image:\s*none\s*!important/);
  assert.match(bridge, /:root:has\(ak-flow-executor\)/);
});
