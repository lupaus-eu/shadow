import assert from "node:assert/strict";
import { test } from "node:test";

import { matchesText, normalizeText } from "../../src/text-match.ts";

test("matching ignores case and accents", () => {
  assert.equal(normalizeText("  Hallituksen Käsittely "), "hallituksen kasittely");
  assert.ok(matchesText("kasittely", "Hallituksen käsittely"));
  assert.ok(matchesText("ÅRS", "Årsplan"));
  assert.ok(matchesText("cafe", "Café meeting"));
});

test("an empty query matches everything and missing text never matches", () => {
  assert.ok(matchesText("   ", "Anything"));
  assert.equal(matchesText("board", null, undefined, "Budget"), false);
});
