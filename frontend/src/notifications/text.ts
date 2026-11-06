/** Turns a notification's type and parameters into text and an optional link, in the reader's language (ADR-0031). */

export type NotificationItem = { id: string; type: string; params: Record<string, unknown>; created_at: string; read_at: string | null };

export type NotificationCopy = {
  roles: Record<"owner" | "admin" | "member" | "editor" | "viewer", string>;
  canEdit: (name: string) => string;
  canView: (name: string) => string;
  viewOnly: (name: string) => string;
  lostAccess: (name: string) => string;
  roleChanged: (from: string, to: string) => string;
  invitationAccepted: (name: string, role: string) => string;
  ownerGained: (name: string) => string;
  ownerLost: (name: string) => string;
  supportRequested: (caseReference: string) => string;
  supportRevoked: (caseReference: string) => string;
  supportExpired: (caseReference: string) => string;
  billingGrace: (until: string) => string;
  billingCanceled: string;
  deletionScheduled: (until: string) => string;
  cancelScheduled: (until: string) => string;
  cancelUndone: string;
  resumed: string;
  contactChanged: (name: boolean, email: boolean) => string;
  legalPublished: (key: string, version: number, date: string, acceptance: string) => string;
  unknown: string;
};

const text = (value: unknown) => (typeof value === "string" ? value : "");

export function notificationText(item: NotificationItem, copy: NotificationCopy, formatDay: (iso: string) => string = (iso) => iso.slice(0, 10)): string {
  const { params } = item;
  const role = (value: unknown) => copy.roles[text(value) as keyof NotificationCopy["roles"]] ?? text(value);
  switch (item.type) {
    case "access_changed": {
      const name = text(params.yearclock_name);
      const to = text(params.to_role);
      if (to === "editor") return copy.canEdit(name);
      if (to === "viewer") return text(params.from_role) === "editor" ? copy.viewOnly(name) : copy.canView(name);
      return copy.lostAccess(name);
    }
    case "role_changed": return copy.roleChanged(role(params.from_role), role(params.to_role));
    case "invitation_accepted": return copy.invitationAccepted(text(params.name), role(params.role));
    case "ownership_changed": return params.owner === true ? copy.ownerGained(text(params.name)) : copy.ownerLost(text(params.name));
    case "support_access_requested": return copy.supportRequested(text(params.case_reference));
    case "support_access_ended": return params.how === "expired" ? copy.supportExpired(text(params.case_reference)) : copy.supportRevoked(text(params.case_reference));
    case "billing_problem": return params.state === "canceled" ? copy.billingCanceled : copy.billingGrace(text(params.grace_expires_at) ? formatDay(text(params.grace_expires_at)) : "");
    case "subscription_cancel_scheduled": return copy.cancelScheduled(text(params.current_period_end) ? formatDay(text(params.current_period_end)) : "");
    case "subscription_cancel_undone": return copy.cancelUndone;
    case "subscription_resumed": return copy.resumed;
    case "billing_contact_changed": return copy.contactChanged(Array.isArray(params.fields) && params.fields.includes("name"), Array.isArray(params.fields) && params.fields.includes("email"));
    case "legal_document_published": return copy.legalPublished(text(params.document_key), Number(params.version) || 0, text(params.effective_from) ? formatDay(text(params.effective_from)) : "", text(params.acceptance));
    case "deletion_scheduled": return copy.deletionScheduled(text(params.purge_after) ? formatDay(text(params.purge_after)) : "");
    default: return copy.unknown;
  }
}

/** Where a notification leads, if anywhere: the Yearclock whose access changed, when it can still be opened. */
export function notificationHref(item: NotificationItem, organizationId: string): string | null {
  if (item.type === "support_access_requested" || item.type === "support_access_ended") return `/organizations/${organizationId}/admin/support`;
  if (item.type === "billing_problem" || item.type === "subscription_cancel_scheduled" || item.type === "subscription_cancel_undone" || item.type === "subscription_resumed" || item.type === "billing_contact_changed") return `/organizations/${organizationId}/admin/billing`;
  if (item.type === "legal_document_published") return `/organizations/${organizationId}/admin/settings`;
  if (item.type === "deletion_scheduled") return `/organizations/${organizationId}/admin/settings`;
  if (item.type !== "access_changed" || text(item.params.to_role) === "none" || !text(item.params.yearclock_id)) return null;
  return `/organizations/${organizationId}/yearclocks/${text(item.params.yearclock_id)}`;
}
