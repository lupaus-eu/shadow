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

export type AiAccess = "none" | "read" | "readWrite";

const READ_SCOPE = "shadow.read";
const WRITE_SCOPE = "shadow.write";

// The consent and connections APIs report a space-separated scope set:
// `shadow.read`, or `shadow.read` and `shadow.write` in any order. An
// empty set means the User's role allows no AI access (`ROLE_SCOPES` maps it to
// no scope). Any other set, including write without read, is not a Shadow
// access level.
export function aiAccessFromScope(scope: string): AiAccess | null {
  const scopes = new Set(scope.split(" ").filter((item) => item !== ""));
  if (scopes.size === 0) return "none";
  for (const item of scopes) {
    if (item !== READ_SCOPE && item !== WRITE_SCOPE) return null;
  }
  if (!scopes.has(READ_SCOPE)) return null;
  return scopes.has(WRITE_SCOPE) ? "readWrite" : "read";
}

// With MCP change-set review on, write access can also apply and reject.
export function aiScopeLabel(scope: string, changeSetReview = false): string {
  const access = aiAccessFromScope(scope);
  if (access === "none") return "No access";
  if (access === "read") return "Read access";
  if (access === "readWrite") {
    return changeSetReview ? "Read, propose, apply and reject changes" : "Read and propose changes";
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
