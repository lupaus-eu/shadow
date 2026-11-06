import assert from "node:assert/strict";
import { test } from "node:test";

import { DEFAULT_DISPLAY, loadDisplay, saveDisplay } from "../../src/yearclock/displays/display-mode.ts";

const memory = () => {
  const items = new Map<string, string>();
  return { getItem: (key: string) => items.get(key) ?? null, setItem: (key: string, value: string) => void items.set(key, value), removeItem: (key: string) => void items.delete(key), items };
};
const all = ["circle", "timeline", "list", "agenda"] as const;

test("the circle is the default and the choice is kept per Yearclock", () => {
  const storage = memory();
  assert.equal(loadDisplay("a", all, storage), DEFAULT_DISPLAY);
  saveDisplay("a", "list", storage);
  assert.equal(loadDisplay("a", all, storage), "list");
  assert.equal(loadDisplay("b", all, storage), "circle");
});

test("choosing the circle clears the stored value", () => {
  const storage = memory();
  saveDisplay("a", "agenda", storage);
  saveDisplay("a", "circle", storage);
  assert.equal(storage.items.size, 0);
});

test("an unknown or unavailable display falls back to the circle", () => {
  const storage = memory();
  storage.setItem("yearclock.display.a", "gantt");
  assert.equal(loadDisplay("a", all, storage), "circle");
  saveDisplay("a", "timeline", storage);
  assert.equal(loadDisplay("a", ["circle", "list"], storage), "circle");
});

test("blocked storage never throws", () => {
  const blocked = { getItem: () => { throw new Error("blocked"); }, setItem: () => { throw new Error("blocked"); }, removeItem: () => { throw new Error("blocked"); } };
  assert.equal(loadDisplay("a", all, blocked), "circle");
  assert.doesNotThrow(() => saveDisplay("a", "list", blocked));
});
