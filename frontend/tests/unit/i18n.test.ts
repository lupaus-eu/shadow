import assert from "node:assert/strict";
import { test } from "node:test";

import { messages, platformMessages, rememberLocale, storedLocale, workspaceMessages } from "../../src/i18n.ts";

type Tree = Record<string, unknown>;

function shape(value: unknown, path: string, out: Map<string, string>): void {
  if (typeof value === "function") {
    out.set(path, "function");
    const sample = (value as (...args: unknown[]) => unknown)("X", 1);
    assert.equal(typeof sample, "string", `${path} must return text`);
    return;
  }
  if (value && typeof value === "object") {
    for (const [key, child] of Object.entries(value as Tree)) shape(child, path ? `${path}.${key}` : key, out);
    return;
  }
  assert.equal(typeof value, "string", `${path} must be text`);
  assert.ok((value as string).trim().length > 0, `${path} must not be empty`);
  out.set(path, "string");
}

for (const [name, load] of [["messages", messages], ["workspaceMessages", workspaceMessages], ["platformMessages", platformMessages]] as const) {
  test(`${name}: Finnish and English define exactly the same texts`, () => {
    const english = new Map<string, string>();
    const finnish = new Map<string, string>();
    shape(load("en"), "", english);
    shape(load("fi"), "", finnish);
    assert.deepEqual([...finnish.keys()].sort(), [...english.keys()].sort());
    for (const [key, kind] of english) assert.equal(finnish.get(key), kind, key);
  });
}

test("an unknown locale falls back to English", () => {
  for (const load of [messages, workspaceMessages, platformMessages]) {
    assert.equal(load("sv" as never), load("en"));
  }
});

test("blocked storage does not break reading or remembering the locale", () => {
  const original = Object.getOwnPropertyDescriptor(globalThis, "localStorage");
  Object.defineProperty(globalThis, "localStorage", { configurable: true, get() { throw new Error("blocked"); } });
  try {
    assert.equal(storedLocale(), "en");
    assert.doesNotThrow(() => rememberLocale("fi"));
  } finally {
    if (original) Object.defineProperty(globalThis, "localStorage", original); else delete (globalThis as { localStorage?: unknown }).localStorage;
  }
});
