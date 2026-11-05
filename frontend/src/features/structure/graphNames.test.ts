import { describe, expect, it } from "vitest";
import { displayGraphName, graphNameTooLong } from "./graphNames";

describe("graphNames", () => {
  it("allows 60 characters after trimming", () => {
    expect(graphNameTooLong("N".repeat(60))).toBe(false);
    expect(graphNameTooLong(`  ${"N".repeat(60)}  `)).toBe(false);
    expect(graphNameTooLong("N".repeat(61))).toBe(true);
  });

  it("counts an emoji as one character, like the backend", () => {
    expect(graphNameTooLong("😀".repeat(60))).toBe(false);
    expect(graphNameTooLong("😀".repeat(61))).toBe(true);
  });

  it("shortens long names without splitting characters", () => {
    expect(displayGraphName("N".repeat(60))).toBe("N".repeat(60));
    expect(displayGraphName("N".repeat(61))).toBe(`${"N".repeat(60)}…`);
    expect(displayGraphName("😀".repeat(61))).toBe(`${"😀".repeat(60)}…`);
  });
});
