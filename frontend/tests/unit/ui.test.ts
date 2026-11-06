import assert from "node:assert/strict";
import { test } from "node:test";

import { cx } from "../../src/ui/cx.ts";

test("cx joins truthy class names and drops the rest", () => {
  assert.equal(cx("a", false, null, undefined, "b", { c: true, d: false }, ["e", 0 && "f"]), "a b c e");
});
