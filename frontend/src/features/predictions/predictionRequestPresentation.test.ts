import { describe, expect, it } from "vitest";
import type { PredictionRequestSummaryDto } from "../../api/predictions";
import { formatElapsedMinutes, formatRequestTimestamp, requestDurations } from "./predictionRequestPresentation";

const submittedTime = "2026-03-29T00:59:30Z";

describe("prediction request timing", () => {
  it("formats local dates to minutes without losing the source offset", () => {
    const value = "2026-09-10T14:23:59+03:00";
    expect(formatRequestTimestamp(value)).toBe(new Intl.DateTimeFormat(undefined, {
      year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit"
    }).format(new Date(value)));
  });

  it.each([
    [-1, "<1 min"], [0, "<1 min"], [59_999, "<1 min"], [60_000, "1 min"],
    [119_999, "1 min"], [3_600_000, "1 h"], [3_660_000, "1 h 1 min"],
    [86_400_000, "1 d"], [90_061_000, "1 d 1 h 1 min"]
  ])("formats %i elapsed milliseconds as %s", (elapsed, expected) => {
    expect(formatElapsedMinutes(submittedTime, Date.parse(submittedTime) + elapsed)).toBe(expected);
  });

  it("uses elapsed instants across timezone offsets and daylight saving changes", () => {
    expect(formatElapsedMinutes("2026-03-29T02:59:30+02:00", "2026-03-29T04:01:29+03:00")).toBe("1 min");
  });

  it.each([
    ["queued", null, null, "5 min", "Not started"],
    ["running", "2026-03-29T01:00:00Z", null, "<1 min", "4 min"],
    ["cancelling", "2026-03-29T01:00:00Z", null, "<1 min", "4 min"],
    ["completed", "2026-03-29T01:00:00Z", "2026-03-29T01:02:00Z", "<1 min", "2 min"],
    ["failed", "2026-03-29T01:00:00Z", "2026-03-29T01:00:20Z", "<1 min", "<1 min"],
    ["cancelled", null, "2026-03-29T01:01:40Z", "2 min", "Not started"],
    ["failed", null, "2026-03-29T01:01:40Z", "2 min", "Not started"],
    ["cancelled", "2026-03-29T01:00:00Z", "2026-03-29T01:02:00Z", "<1 min", "2 min"],
    ["completed", "2026-03-29T00:58:00Z", "2026-03-29T00:57:00Z", "<1 min", "<1 min"]
  ] as const)("derives %s durations from the available lifecycle stages", (state, startTime, finishTime, queue, processing) => {
    const request: PredictionRequestSummaryDto = {
      id: "request", name: "Plan", state, submittedTime, startTime, finishTime,
      failureCode: null, failureReason: null, completedPredictionId: null
    };
    expect(requestDurations(request, Date.parse("2026-03-29T01:04:30Z"))).toEqual({ queue, processing });
  });
});
