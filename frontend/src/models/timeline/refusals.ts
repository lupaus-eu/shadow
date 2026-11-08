import type { Locale } from "../../i18n";
import { ChainBrokenError, ForbiddenError, RuleError, StaleVersionError } from "../client";
import { branchPointMessage, chainBrokenMessage } from "../timeline";
import { timelineMessages } from "../timeline-messages";

/** What a refused or failed write says, built from the structured answer (never the server's own text). */
export function refusalMessage(cause: unknown, locale: Locale): string {
  const text = timelineMessages(locale);
  if (cause instanceof StaleVersionError) return text.stale;
  if (cause instanceof ForbiddenError) return text.forbidden;
  if (cause instanceof ChainBrokenError) return chainBrokenMessage(cause.hint, locale);
  if (cause instanceof RuleError) {
    switch (cause.reason) {
      case "branch_point": return branchPointMessage(typeof cause.detail.line === "string" ? cause.detail.line : null, locale);
      case "duplicate_name": return text.duplicateName;
      case "limit_reached": return cause.detail.limit === "lines_per_model" ? text.limitScenarios : text.limitEvents;
      default: return text.failed;
    }
  }
  return text.failed;
}
