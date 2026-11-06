import { describe, expect, it } from "vitest";
import { endsInOrgState, nextOrgStateTargetDate } from "./lifetime";

describe("nextOrgStateTargetDate", () => {
  const orgStates = [
    { targetDate: "2026-03-01" },
    { targetDate: "2026-01-01" },
    { targetDate: "2026-02-01" }
  ];

  it("returns the closest later target date", () => {
    expect(nextOrgStateTargetDate(orgStates, "2026-01-01")).toBe("2026-02-01");
    expect(nextOrgStateTargetDate(orgStates, "2026-01-15")).toBe("2026-02-01");
  });

  it("returns null without a later org state", () => {
    expect(nextOrgStateTargetDate(orgStates, "2026-03-01")).toBeNull();
    expect(nextOrgStateTargetDate([], "2026-03-01")).toBeNull();
  });
});

describe("endsInOrgState", () => {
  it("never marks an element without a delete date", () => {
    expect(endsInOrgState(null, "2026-02-01", "2026-03-01")).toBe(false);
    expect(endsInOrgState(null, "2026-02-01", null)).toBe(false);
    expect(endsInOrgState(null, "2026-02-01", undefined)).toBe(false);
  });

  it("marks an element deleted on the target date", () => {
    expect(endsInOrgState("2026-02-01", "2026-02-01", "2026-03-01")).toBe(true);
  });

  it("marks an element deleted before the next org state", () => {
    expect(endsInOrgState("2026-01-15", "2026-01-01", "2026-02-01")).toBe(true);
  });

  it("does not mark an element still visible in the next org state", () => {
    expect(endsInOrgState("2026-02-01", "2026-01-01", "2026-02-01")).toBe(false);
    expect(endsInOrgState("2026-02-15", "2026-01-01", "2026-02-01")).toBe(false);
  });

  it("marks any element with a delete date when there is no later org state", () => {
    expect(endsInOrgState("2026-05-01", "2026-03-01", null)).toBe(true);
  });

  it("only marks an element deleted on the target date when org states are unknown", () => {
    expect(endsInOrgState("2026-02-01", "2026-02-01", undefined)).toBe(true);
    expect(endsInOrgState("2026-02-15", "2026-02-01", undefined)).toBe(false);
  });
});
