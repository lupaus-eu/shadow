import assert from "node:assert/strict";
import { test } from "node:test";

import { notificationHref, notificationText, type NotificationCopy, type NotificationItem } from "../../src/notifications/text.ts";

const copy: NotificationCopy = {
  roles: { owner: "Owner", admin: "Administrator", member: "Member", editor: "Editor", viewer: "Viewer" },
  canEdit: (name) => `edit ${name}`, canView: (name) => `view ${name}`, viewOnly: (name) => `view only ${name}`, lostAccess: (name) => `lost ${name}`,
  supportRequested: (c) => `support asked ${c}`, supportRevoked: (c) => `support ended ${c}`, supportExpired: (c) => `support expired ${c}`, billingGrace: (d) => `grace ${d}`, billingCanceled: "canceled", cancelScheduled: (d) => `cancel ${d}`, cancelUndone: "undone", resumed: "resumed", contactChanged: (n, e) => `contact ${[n ? "name" : "", e ? "email" : ""].filter(Boolean).join("+")}`, deletionScheduled: (d) => `deletion ${d}`,
  roleChanged: (from, to) => `${from}>${to}`, invitationAccepted: (name, role) => `${name} joined as ${role}`, ownerGained: (name) => `${name} owner`, ownerLost: (name) => `${name} not owner`, legalPublished: (k, v, d, a) => `legal ${k} v${v} ${d} ${a}`, unknown: "?",
};
const item = (type: string, params: Record<string, unknown>): NotificationItem => ({ id: "1", type, params, created_at: "2026-10-05T08:00:00Z", read_at: null });
const access = (from: string, to: string) => item("access_changed", { yearclock_id: "y1", yearclock_name: "Plan", from_role: from, to_role: to });

test("access notifications say what the person can now do", () => {
  assert.equal(notificationText(access("none", "editor"), copy), "edit Plan");
  assert.equal(notificationText(access("viewer", "editor"), copy), "edit Plan");
  assert.equal(notificationText(access("none", "viewer"), copy), "view Plan");
  assert.equal(notificationText(access("editor", "viewer"), copy), "view only Plan");
  assert.equal(notificationText(access("viewer", "none"), copy), "lost Plan");
});

test("role, invitation, and ownership notifications use role names", () => {
  assert.equal(notificationText(item("role_changed", { from_role: "member", to_role: "admin" }), copy), "Member>Administrator");
  assert.equal(notificationText(item("invitation_accepted", { name: "Sanna", role: "member" }), copy), "Sanna joined as Member");
  assert.equal(notificationText(item("ownership_changed", { name: "Mika", owner: true }), copy), "Mika owner");
  assert.equal(notificationText(item("ownership_changed", { name: "Mika", owner: false }), copy), "Mika not owner");
  assert.equal(notificationText(item("something_new", {}), copy), "?");
});

test("only a Yearclock the person can still open is linked", () => {
  assert.equal(notificationHref(access("none", "viewer"), "o1"), "/organizations/o1/yearclocks/y1");
  assert.equal(notificationHref(access("viewer", "none"), "o1"), null);
  assert.equal(notificationHref(item("role_changed", {}), "o1"), null);
});

test("Organization notices name the case or the date and lead to their page", () => {
  assert.equal(notificationText(item("support_access_requested", { case_reference: "C1" }), copy), "support asked C1");
  assert.equal(notificationText(item("support_access_ended", { case_reference: "C1", how: "expired" }), copy), "support expired C1");
  assert.equal(notificationText(item("support_access_ended", { case_reference: "C1", how: "revoked" }), copy), "support ended C1");
  assert.equal(notificationText(item("billing_problem", { state: "grace", grace_expires_at: "2026-10-12T00:00:00Z" }), copy), "grace 2026-10-12");
  assert.equal(notificationText(item("billing_problem", { state: "canceled" }), copy), "canceled");
  assert.equal(notificationText(item("deletion_scheduled", { purge_after: "2026-11-04T09:00:00Z" }), copy, () => "4 Nov"), "deletion 4 Nov");
  assert.equal(notificationHref(item("support_access_requested", {}), "o1"), "/organizations/o1/admin/support");
  assert.equal(notificationHref(item("billing_problem", {}), "o1"), "/organizations/o1/admin/billing");
  assert.equal(notificationHref(item("deletion_scheduled", {}), "o1"), "/organizations/o1/admin/settings");
});

test("subscription notices say what happened and lead to Billing", () => {
  assert.equal(notificationText(item("subscription_cancel_scheduled", { current_period_end: "2026-11-04T00:00:00Z" }), copy, () => "4 Nov"), "cancel 4 Nov");
  assert.equal(notificationText(item("subscription_cancel_undone", {}), copy), "undone");
  assert.equal(notificationText(item("subscription_resumed", {}), copy), "resumed");
  for (const type of ["subscription_cancel_scheduled", "subscription_cancel_undone", "subscription_resumed"]) assert.equal(notificationHref(item(type, {}), "o1"), "/organizations/o1/admin/billing");
});

test("a billing contact change names the fields", () => {
  assert.equal(notificationText(item("billing_contact_changed", { fields: ["name", "email"] }), copy), "contact name+email");
  assert.equal(notificationText(item("billing_contact_changed", {}), copy), "contact ");
  assert.equal(notificationHref(item("billing_contact_changed", {}), "o1"), "/organizations/o1/admin/billing");
});

test("a published legal document names the version and leads to the settings", () => {
  const notice = item("legal_document_published", { document_key: "terms", version: 2, effective_from: "2026-12-01", acceptance: "required" });
  assert.equal(notificationText(notice, copy), "legal terms v2 2026-12-01 required");
  assert.equal(notificationHref(notice, "o1"), "/organizations/o1/admin/settings");
});
