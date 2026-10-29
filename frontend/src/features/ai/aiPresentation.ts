import type { AiChangeSetStatus } from "../../api/ai";

export function formatAiTimestamp(value: string): string {
  return new Intl.DateTimeFormat(undefined, {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit"
  }).format(new Date(value));
}

export function aiScopeLabel(scope: string): string {
  if (scope === "schatten.read") return "Read";
  if (scope === "schatten.write") return "Propose changes";
  return scope;
}

const CHANGE_SET_STATUS_LABELS: Record<AiChangeSetStatus, string> = {
  draft: "Draft",
  submitted: "Awaiting review",
  applied: "Applied",
  rejected: "Rejected",
  failed: "Failed",
  discarded: "Discarded"
};

export function changeSetStatusLabel(status: AiChangeSetStatus): string {
  return CHANGE_SET_STATUS_LABELS[status] ?? status;
}
