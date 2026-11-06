import assert from "node:assert/strict";
import { test } from "node:test";

import { applyFormat } from "../../src/yearclock/description-format.ts";

test("bold and italic wrap the selection and keep it selected", () => {
  assert.deepEqual(applyFormat("a word here", 2, 6, "bold"), { value: "a **word** here", start: 4, end: 8 });
  assert.deepEqual(applyFormat("a word here", 2, 6, "italic"), { value: "a *word* here", start: 3, end: 7 });
});

test("with nothing selected the markers go in with the caret between them", () => {
  assert.deepEqual(applyFormat("ab", 1, 1, "bold"), { value: "a****b", start: 3, end: 3 });
});

test("selecting marked text and pressing the button again removes the markers", () => {
  assert.deepEqual(applyFormat("**word**", 0, 8, "bold"), { value: "word", start: 0, end: 4 });
});

test("a link keeps the selected text and selects the address placeholder", () => {
  const edit = applyFormat("see plan now", 4, 8, "link");
  assert.equal(edit.value, "see [plan](https://) now");
  assert.equal(edit.value.slice(edit.start, edit.end), "https://");
  assert.equal(applyFormat("", 0, 0, "link").value, "[text](https://)");
});

test("a list prefixes every touched line and a second press takes the prefix away", () => {
  const first = applyFormat("one\ntwo\nthree", 2, 6, "list");
  assert.equal(first.value, "- one\n- two\nthree");
  const second = applyFormat(first.value, first.start, first.end, "list");
  assert.equal(second.value, "one\ntwo\nthree");
  assert.equal(applyFormat("- a\nb", 0, 5, "list").value, "- a\n- b");
});
