import assert from "node:assert/strict";
import { test } from "node:test";

import { parseAddresses } from "../../src/invitation-addresses.ts";

test("pasted addresses split on commas, semicolons, and lines, and drop names and repeats", () => {
  assert.deepEqual(parseAddresses("ann@example.com, Ben@Example.com;\ncat@example.com\n\nann@example.com"), ["ann@example.com", "Ben@Example.com", "cat@example.com"]);
  assert.deepEqual(parseAddresses('"Dan Driver" <dan@example.com>; (eve@example.com)'), ["dan@example.com", "eve@example.com"]);
  assert.deepEqual(parseAddresses("Name only, just-text"), []);
});
