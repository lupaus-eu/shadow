import assert from "node:assert/strict";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { test } from "node:test";

// The browser storage notice lists every cookie and web-storage key (backend/legal/browser-storage.json).
// This test keeps the code and that list the same, so the notice cannot go stale unnoticed.
const FIX = "Update backend/legal/browser-storage.json and the browser storage notice (backend/legal/storage.*.md) in the same change.";
const listPath = new URL("../../../backend/legal/browser-storage.json", import.meta.url);
const list = JSON.parse(readFileSync(listPath, "utf8")) as {
  localStorage: Array<{ key: string; dynamic?: boolean; purpose: string; lifetime: string }>;
  sessionStorage: Array<{ key: string; dynamic?: boolean; purpose: string; lifetime: string }>;
};
const source = fileURLToPath(new URL("../../src", import.meta.url));

function files(directory: string): string[] {
  return readdirSync(directory).flatMap((name) => {
    const path = join(directory, name);
    return statSync(path).isDirectory() ? files(path) : /\.(ts|tsx)$/.test(name) ? [path] : [];
  });
}
const code = files(source).map((path) => ({ path, text: readFileSync(path, "utf8") }));
const relative = (path: string) => path.slice(source.length + 1);

// String and template literals that look like one of our keys: "yearclock.something" or `yearclock.filters.${id}`.
const KEY = /["'`](yearclock\.[a-z][a-z0-9.-]*)/g;
const used = new Map<string, string[]>();
for (const { path, text } of code) {
  if (!/localStorage|sessionStorage/.test(text)) continue;
  for (const match of text.matchAll(KEY)) used.set(match[1], [...(used.get(match[1]) ?? []), relative(path)]);
}
const listed = [...list.localStorage, ...list.sessionStorage];

test("every entry records a purpose and a lifetime", () => {
  for (const entry of listed) {
    assert.ok(entry.purpose.length > 10, `${entry.key}: purpose is missing`);
    assert.ok(entry.lifetime.length > 3, `${entry.key}: lifetime is missing`);
  }
});

test("every storage key in the code is listed", () => {
  assert.ok(used.size >= 6, `the scan found only ${used.size} keys; has the code moved?`);
  for (const [key, where] of used) {
    const known = listed.some((entry) => (entry.dynamic ? key.startsWith(entry.key) : key === entry.key));
    assert.ok(known, `${key} (in ${where.join(", ")}) is not in the browser storage list. ${FIX}`);
  }
});

test("every listed key still exists in the code", () => {
  for (const entry of listed) {
    const present = [...used.keys()].some((key) => (entry.dynamic ? key.startsWith(entry.key) : key === entry.key));
    assert.ok(present, `${entry.key} is in the browser storage list but no code uses it. ${FIX}`);
  }
});

test("a file that uses web storage names its keys, and cookies and IndexedDB are not used", () => {
  for (const { path, text } of code) {
    if (/\b(localStorage|sessionStorage)\b/.test(text)) assert.ok([...text.matchAll(KEY)].length > 0, `${relative(path)} uses web storage without a yearclock.* key. ${FIX}`);
    assert.ok(!/document\.cookie/.test(text), `${relative(path)} sets a cookie from script. ${FIX}`);
    assert.ok(!/indexedDB/.test(text), `${relative(path)} uses IndexedDB. ${FIX}`);
  }
});
