import assert from "node:assert/strict";
import { test } from "node:test";

import { readPanels, writePanels } from "../../src/models/panel-state.ts";

const memory = () => {
  const data = new Map<string, string>();
  return { data, getItem: (key: string) => data.get(key) ?? null, setItem: (key: string, value: string) => { data.set(key, value); } };
};

test("panels default to open", () => {
  assert.deepEqual(readPanels(memory()), { left: false, right: false });
  assert.deepEqual(readPanels(null), { left: false, right: false });
});

test("the collapsed state round-trips", () => {
  const store = memory();
  writePanels({ left: true, right: false }, store);
  assert.equal(store.data.get("shadow.canvas.panels"), '{"left":true,"right":false}');
  assert.deepEqual(readPanels(store), { left: true, right: false });
});

test("bad JSON and wrong shapes give the defaults", () => {
  for (const bad of ["{oops", "null", "42", '"x"', '{"left":"yes","right":1}']) {
    const store = memory();
    store.data.set("shadow.canvas.panels", bad);
    assert.deepEqual(readPanels(store), { left: false, right: false }, bad);
  }
});

test("blocked storage neither reads nor throws", () => {
  const blocked = { getItem: () => { throw new Error("blocked"); }, setItem: () => { throw new Error("blocked"); } };
  assert.deepEqual(readPanels(blocked), { left: false, right: false });
  assert.doesNotThrow(() => writePanels({ left: true, right: true }, blocked));
});
