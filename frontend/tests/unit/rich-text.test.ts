import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import { parseRichText, plainText } from "../../src/yearclock/rich-text.ts";

type Case = { name: string; input: string; blocks: unknown; plain: string };
const cases = JSON.parse(readFileSync(new URL("./rich-text-cases.json", import.meta.url), "utf8")) as Case[];

// The same cases run against `backend/app/rich_text.py`, so both parsers read a description alike.
for (const item of cases) {
  test(`rich text: ${item.name}`, () => {
    assert.deepEqual(parseRichText(item.input), item.blocks);
    assert.equal(plainText(item.input), item.plain);
  });
}

test("a plain-format description is returned as it is", () => {
  assert.equal(plainText("**not bold** *at all*", "plain"), "**not bold** *at all*");
  assert.equal(plainText(null), "");
});
