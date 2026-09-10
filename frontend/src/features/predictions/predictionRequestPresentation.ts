import type { PredictionRequestSummaryDto } from "../../api/predictions";

export function isTerminalRequest(request: PredictionRequestSummaryDto): boolean {
  return request.state === "completed" || request.state === "cancelled" || request.state === "failed";
}

export function formatRequestTimestamp(value: string): string {
  return new Intl.DateTimeFormat(undefined, {
    year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit"
  }).format(new Date(value));
}

export function formatElapsedMinutes(start: string, end: string | number): string {
  const minutes = Math.max(0, Math.floor(
    ((typeof end === "number" ? end : Date.parse(end)) - Date.parse(start)) / 60_000
  ));
  if (minutes < 1) return "<1 min";
  const days = Math.floor(minutes / 1440);
  const hours = Math.floor(minutes % 1440 / 60);
  const remainder = minutes % 60;
  return [days ? `${days} d` : "", hours ? `${hours} h` : "", remainder ? `${remainder} min` : ""]
    .filter(Boolean).join(" ");
}

export function requestDurations(request: PredictionRequestSummaryDto, now: number) {
  const end = request.finishTime ?? (isTerminalRequest(request) ? null : now);
  return {
    queue: request.startTime !== null || end !== null
      ? formatElapsedMinutes(request.submittedTime, request.startTime ?? end!)
      : "Not finished",
    processing: request.startTime === null ? "Not started"
      : end === null ? "Not finished" : formatElapsedMinutes(request.startTime, end)
  };
}

export function requestNoticeMessage(request: PredictionRequestSummaryDto): string {
  const prefix = `Prediction request “${request.name}”`;
  switch (request.state) {
    case "completed": return `${prefix} completed.`;
    case "cancelled": return `${prefix} was cancelled.`;
    case "failed": return `${prefix} failed.${request.failureReason ? ` ${request.failureReason}` : ""}`;
    default: return `${prefix} was accepted and queued.`;
  }
}
