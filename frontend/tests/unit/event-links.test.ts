import assert from "node:assert/strict";
import { test } from "node:test";

import { cleanLinks, isWebAddress, linkProblems, moveLink, sameLinks, type EventLink } from "../../src/yearclock/event-links.ts";

const link = (title: string, url: string): EventLink => ({ title, url });

test("only http and https addresses with a host are links", () => {
  assert.equal(isWebAddress("https://example.com/a"), true);
  assert.equal(isWebAddress("http://example.com"), true);
  for (const bad of ["ftp://example.com", "javascript:alert(1)", "example.com", "https://", ""]) assert.equal(isWebAddress(bad), false, bad);
});

test("cleaning trims rows and drops the empty ones", () => {
  assert.deepEqual(cleanLinks([link("  A ", " https://example.com/a "), link("", ""), link("B", "")]), [link("A", "https://example.com/a"), link("B", "")]);
});

test("each row with a problem is reported once, with its position", () => {
  const rows = [link("Good", "https://example.com/a"), link("", "https://example.com/b"), link("Bad address", "ftp://x"), link("Same", "https://example.com/a")];
  assert.deepEqual(linkProblems(rows), [{ row: 2, kind: "title" }, { row: 3, kind: "address" }, { row: 4, kind: "duplicate" }]);
  assert.deepEqual(linkProblems([link("", ""), link("Fine", "https://example.com")]), []);
  assert.deepEqual(linkProblems([link("x".repeat(101), "https://example.com")]), [{ row: 1, kind: "title" }]);
});

test("more than ten links is one problem", () => {
  const eleven = Array.from({ length: 11 }, (_, index) => link(`l${index}`, `https://example.com/${index}`));
  assert.deepEqual(linkProblems(eleven), [{ row: 0, kind: "tooMany" }]);
  assert.deepEqual(linkProblems(eleven.slice(0, 10)), []);
});

test("moving a link swaps neighbours and stays put at the ends", () => {
  const rows = [link("a", "https://a.test"), link("b", "https://b.test"), link("c", "https://c.test")];
  assert.deepEqual(moveLink(rows, 1, -1).map((item) => item.title), ["b", "a", "c"]);
  assert.deepEqual(moveLink(rows, 1, 1).map((item) => item.title), ["a", "c", "b"]);
  assert.equal(moveLink(rows, 0, -1), rows);
  assert.equal(moveLink(rows, 2, 1), rows);
});

test("link lists compare by content, and a missing list is empty", () => {
  assert.equal(sameLinks([link("a", "https://a.test")], [link("a", "https://a.test")]), true);
  assert.equal(sameLinks(undefined, []), true);
  assert.equal(sameLinks([link("a", "https://a.test")], [link("b", "https://a.test")]), false);
});
