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

// With MCP change-set review on, write access can also apply and reject.
export function aiScopeLabel(scope: string, changeSetReview = false): string {
  if (scope === "schatten.read") return "Read";
  if (scope === "schatten.write") {
    return changeSetReview ? "Propose and apply changes" : "Propose changes";
  }
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
