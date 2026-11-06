import { apiBaseUrl, AuthenticationRequiredError } from "./auth-client";
import type { Locale } from "./i18n";

export type OrganizationSignupInput = {
  organization_name: string;
  time_zone: string;
  default_locale: Locale;
  billing_name: string;
  billing_email: string;
  initial_seats: number;
  accepted_documents?: Array<{ document_key: string; version: number; locale: Locale }>;
};

export type OrganizationSignup = {
  organization_id: string;
  organization_name: string;
  status: "pending_activation" | "active" | "expired";
  initial_seats: number;
  expires_at: string;
  checkout_url: string | null;
  initial_content: {
    owner_user_account_id: string;
    yearclock_id: string;
    yearclock_name: string;
    lane_id: string;
    lane_name: string;
  } | null;
};

export type OrganizationSummary = {
  id: string;
  name: string;
  role: "owner" | "admin" | "member";
  status?: "active" | "pending_deletion";
  purge_after?: string | null;
};

export type OrganizationWorkspace = {
  organization: {
    id: string;
    name: string;
    time_zone: string;
  };
  membership: {
    role: "owner" | "admin" | "member";
  };
  subscription: Subscription;
  yearclocks: WorkspaceYearclock[];
  recent_yearclock_ids?: string[];
};

/** Remember that the user opened a Yearclock; failures are harmless and ignored by callers. */
export async function recordYearclockVisit(organizationId: string, yearclockId: string): Promise<{ previous_visited_at: string | null }> {
  const response = await fetch(`${apiBaseUrl}/api/v1/organizations/${organizationId}/yearclocks/${yearclockId}/visit`, { method: "POST", credentials: "include" });
  return response.ok ? ((await response.json().catch(() => ({ previous_visited_at: null }))) as { previous_visited_at: string | null }) : { previous_visited_at: null };
}

/** What others changed in a Yearclock (and its readable Linked Lanes) after ``since``. */
export async function loadChanges(organizationId: string, yearclockId: string, since: string, limit = 200): Promise<import("./yearclock/history").ChangesPage> {
  return yearclockResponse(await fetch(`${apiBaseUrl}/api/v1/organizations/${organizationId}/yearclocks/${yearclockId}/changes?since=${encodeURIComponent(since)}&limit=${limit}`, { credentials: "include" }));
}

export type Subscription = {
  state: "active" | "grace" | "read_only";
  writable: boolean;
  grace_expires_at: string | null;
  cancel_at_period_end: boolean;
  current_period_end: string | null;
  /** The subscription has ended (as opposed to unpaid): the Organization can subscribe again. */
  ended?: boolean;
};

export type AuditItem = { id: string; actor: string | null; support_access_id: string | null; action: string; target_type: string; target_id: string; occurred_at: string; change_summary: Record<string, unknown> };

export async function loadAuditEvents(organizationId: string, { prefix, offset = 0, limit = 25 }: { prefix?: string; offset?: number; limit?: number } = {}): Promise<{ items: AuditItem[]; next_offset: number | null }> {
  const params = new URLSearchParams({ offset: String(offset), limit: String(limit) });
  if (prefix) params.set("prefix", prefix);
  const response = await fetch(`${apiBaseUrl}/api/v1/organizations/${organizationId}/audit-events?${params.toString()}`, { credentials: "include" });
  if (response.status === 401) throw new AuthenticationRequiredError();
  if (!response.ok) throw new Error("Audit request failed");
  return (await response.json()) as { items: AuditItem[]; next_offset: number | null };
}

export type SupportAccessStatus = "pending" | "approved" | "rejected" | "revoked" | "expired";
export type SupportAccessRequest = { id: string; organization_id: string; case_reference: string; scope: "read" | "write"; status: SupportAccessStatus; requested_hours: number; requested_by: string; created_at: string; decided_at: string | null; expires_at: string | null };

export async function loadSupportAccess(organizationId: string): Promise<SupportAccessRequest[]> {
  const response = await fetch(`${apiBaseUrl}/api/v1/organizations/${organizationId}/support-access`, { credentials: "include" });
  if (response.status === 401) throw new AuthenticationRequiredError();
  if (!response.ok) throw new Error("Support Access request failed");
  return (await response.json()) as SupportAccessRequest[];
}

export async function decideSupportAccess(organizationId: string, requestId: string, decision: "approve" | "reject" | "revoke", hours?: number): Promise<SupportAccessRequest> {
  const response = await fetch(`${apiBaseUrl}/api/v1/organizations/${organizationId}/support-access/${requestId}/${decision}`, {
    method: "POST", credentials: "include", headers: { "Content-Type": "application/json" }, body: decision === "approve" ? JSON.stringify({ hours: hours ?? null }) : undefined,
  });
  if (response.status === 401) throw new AuthenticationRequiredError();
  if (!response.ok) throw new Error("Support Access decision failed");
  return (await response.json()) as SupportAccessRequest;
}

export type DeletionState = { status: string; deletion_requested_at: string | null; purge_after: string | null };

export async function requestOrganizationDeletion(organizationId: string): Promise<DeletionState> {
  const response = await fetch(`${apiBaseUrl}/api/v1/organizations/${organizationId}/deletion`, { method: "POST", credentials: "include", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ confirm: true }) });
  if (response.status === 401) throw new AuthenticationRequiredError();
  if (!response.ok) throw new Error("Deletion request failed");
  return (await response.json()) as DeletionState;
}

export async function restoreOrganization(organizationId: string): Promise<DeletionState> {
  const response = await fetch(`${apiBaseUrl}/api/v1/organizations/${organizationId}/deletion/restore`, { method: "POST", credentials: "include" });
  if (response.status === 401) throw new AuthenticationRequiredError();
  if (!response.ok) throw new Error("Restore failed");
  return (await response.json()) as DeletionState;
}

export async function openBillingPortal(organizationId: string): Promise<string> {
  const response = await fetch(`${apiBaseUrl}/api/v1/organizations/${organizationId}/billing/portal`, { method: "POST", credentials: "include" });
  if (response.status === 401) throw new AuthenticationRequiredError();
  if (!response.ok) throw new Error("Billing portal request failed");
  return ((await response.json()) as { url: string }).url;
}

export type SubscriptionChange = Subscription & { released_seat_decrease: boolean };
export type CancelReason = "too_expensive" | "not_needed" | "switching" | "other";

async function subscriptionCall(organizationId: string, path: string, body?: unknown): Promise<SubscriptionChange> {
  const response = await fetch(`${apiBaseUrl}/api/v1/organizations/${organizationId}/billing/${path}`, { method: "POST", credentials: "include", ...(body === undefined ? {} : { headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }) });
  if (response.status === 401) throw new AuthenticationRequiredError();
  if (!response.ok) throw new Error("Subscription request failed");
  return (await response.json()) as SubscriptionChange;
}

/** Cancel at the end of the paid period; the answer carries the new state. */
export type BillingContact = { billing_name: string; billing_email: string };
export class ContactRateLimitedError extends Error {
  constructor(readonly retryAfterSeconds: number) { super("Rate limited"); }
}

export async function loadBillingContact(organizationId: string): Promise<BillingContact> {
  const response = await fetch(`${apiBaseUrl}/api/v1/organizations/${organizationId}/billing/contact`, { credentials: "include" });
  if (response.status === 401) throw new AuthenticationRequiredError();
  if (!response.ok) throw new Error("Billing contact request failed");
  return (await response.json()) as BillingContact;
}

/** The billing name and email, saved in Stripe first; 429 when changed too often. */
export async function saveBillingContact(organizationId: string, contact: BillingContact): Promise<BillingContact> {
  const response = await fetch(`${apiBaseUrl}/api/v1/organizations/${organizationId}/billing/contact`, { method: "PUT", credentials: "include", headers: { "Content-Type": "application/json" }, body: JSON.stringify(contact) });
  if (response.status === 401) throw new AuthenticationRequiredError();
  if (response.status === 429) {
    const detail = ((await response.json().catch(() => null)) as { detail?: { retry_after_seconds?: number } } | null)?.detail;
    throw new ContactRateLimitedError(detail?.retry_after_seconds ?? Number(response.headers.get("Retry-After") ?? 3600));
  }
  if (!response.ok) throw new Error("Billing contact change failed");
  return (await response.json()) as BillingContact;
}

/** Start Checkout for a new subscription; returns the Stripe Checkout address. */
export async function startResubscription(organizationId: string, seats: number): Promise<string> {
  const response = await fetch(`${apiBaseUrl}/api/v1/organizations/${organizationId}/billing/resubscribe`, { method: "POST", credentials: "include", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ seats }) });
  if (response.status === 401) throw new AuthenticationRequiredError();
  if (!response.ok) throw new Error("Resubscription request failed");
  return ((await response.json()) as { url: string }).url;
}

export const cancelSubscription = (organizationId: string, reason: CancelReason | null) => subscriptionCall(organizationId, "cancel", { reason });
export const undoCancellation = (organizationId: string) => subscriptionCall(organizationId, "cancel/undo");

export type WorkspaceYearclock = {
  id: string;
  name: string;
  version: number;
  access_role: "editor" | "viewer";
  lanes: Lane[];
  start_month?: number;
  show_week_ring?: boolean;
  show_quarter_ring?: boolean;
};

export type LayoutChanges = { start_month?: number; show_week_ring?: boolean; show_quarter_ring?: boolean };

export async function updateLayout(organizationId: string, yearclock: { id: string; version: number }, changes: LayoutChanges): Promise<{ id: string; version: number; start_month: number }> {
  return yearclockResponse(await fetch(`${apiBaseUrl}/api/v1/organizations/${organizationId}/yearclocks/${yearclock.id}/layout`, { method: "PATCH", credentials: "include", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ...changes, expected_version: yearclock.version }) }));
}

export type SeatProjection = {
  purchased: number;
  occupied: number;
  reserved: number;
  available: number;
  version: number;
  pending_change: {
    id: string;
    kind: "increase" | "decrease";
    status: "pending_payment" | "scheduled";
    target_seats: number;
    effective_at: string | null;
  } | null;
};

export type SeatIncreasePreview = {
  preview_id: string;
  target_seats: number;
  amount_due: number;
  currency: string;
  proration_date: string;
};

export type OrganizationInvitation = {
  id: string;
  email: string;
  role: "owner" | "admin" | "member";
  status: "pending" | "accepted" | "revoked" | "superseded" | "expired";
  expires_at: string;
  version: number;
};

export type OrganizationMembership = {
  id: string;
  user_account_id: string;
  email: string;
  display_name: string;
  role: "owner" | "admin" | "member";
  version: number;
};

export type Lane = {
  id: string;
  name: string;
  display_order: number;
  version: number;
  tint?: string | null;
  height?: "normal" | "tall";
  source_lane_id?: string | null;
  source?: LinkSource | null;
};

/** What the viewer may know about a Linked Lane's source (Yearclock V2). */
export type LinkSource = { available: boolean; reason: "no_access" | "deleted" | null; yearclock_id: string | null; yearclock_name: string | null; lane_name: string | null };

export type ManagedYearclock = {
  id: string;
  name: string;
  display_order: number;
  version: number;
  archived_at: string | null;
  deleted_at?: string | null;
  purge_after?: string | null;
  lanes: Lane[];
  organization_access?: OrganizationAccess;
};

export type OrganizationAccess = "none" | "viewer" | "editor";

export class ConfirmationRequiredError extends Error {
  constructor(readonly members: number) { super("confirmation required"); }
}

/** Share a Yearclock with every member of the Organization (Yearclock V2). */
export async function setOrganizationAccess(organizationId: string, yearclock: { id: string; version: number }, role: OrganizationAccess, confirm = false): Promise<{ organization_access: OrganizationAccess; version: number }> {
  const response = await fetch(`${apiBaseUrl}/api/v1/organizations/${organizationId}/yearclocks/${yearclock.id}/organization-access`, { method: "PUT", credentials: "include", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ role, expected_version: yearclock.version, confirm }) });
  if (response.status === 409) {
    const detail = ((await response.json().catch(() => null)) as { detail?: { reason?: string; members?: number } } | null)?.detail;
    if (detail?.reason === "confirmation_required") throw new ConfirmationRequiredError(detail.members ?? 0);
    throw new ConflictError("The Yearclock changed");
  }
  return yearclockResponse(response);
}

export type YearclockAccessGrant = {
  id: string;
  user_account_id: string;
  role: "editor" | "viewer";
  version: number;
};

import type { EventLink } from "./yearclock/event-links";

export type YearclockEvent = {
  id: string;
  lane_id: string;
  category_id: string | null;
  label_ids?: string[];
  title: string;
  description: string | null;
  description_format?: "plain" | "markdown";
  location?: string | null;
  links?: EventLink[];
  starts_at?: string | null;
  ends_at?: string | null;
  starts_on: string;
  ends_on: string | null;
  version: number;
  occurrence_id?: string | null;
  series_id?: string | null;
  series_date?: string | null;
  exception?: boolean;
  skipped?: boolean;
  deleted_at?: string | null;
  purge_after?: string | null;
  linked?: boolean;
  source_yearclock_id?: string | null;
};

export type EventInput = Pick<YearclockEvent, "title" | "lane_id" | "category_id" | "starts_on" | "ends_on" | "description"> & { description_format: "plain" | "markdown"; location: string | null; links: EventLink[]; starts_at: string | null; ends_at: string | null } & { label_ids?: string[]; origin?: "duplicate" | "plan_again" };
export type YearclockCategory = { id: string; name: string; color: string | null; display_order: number; version: number; scope?: "organization" | "yearclock" | "linked"; usage?: number | null; source_yearclock_id?: string | null; source_yearclock_name?: string | null };
export type SeriesInput = { title: string; lane_id: string; category_id: string | null; description: string | null; description_format: "plain" | "markdown"; location: string | null; links: EventLink[]; starts_at: string | null; ends_at: string | null; starts_on: string; frequency: "WEEKLY" | "MONTHLY" | "YEARLY"; interval: number; until: string | null; occurrence_count: number | null; last_day: boolean; label_ids?: string[] };
export type OccurrenceEdit = Partial<Pick<YearclockEvent, "title" | "description" | "description_format" | "location" | "links" | "starts_at" | "ends_at" | "lane_id" | "category_id" | "starts_on">> & { label_ids?: string[] };
export type SeriesChanges = Partial<Pick<YearclockEvent, "title" | "description" | "description_format" | "location" | "links" | "starts_at" | "ends_at" | "lane_id" | "category_id">> & { label_ids?: string[] };
export type YearclockSeries = { id: string; title: string; frequency: SeriesInput["frequency"]; interval: number; starts_on: string; effective_from: string; until: string | null; occurrence_count: number | null; last_day: boolean; rrule: string; version: number };

export class ConflictError extends Error {}

async function organizationResponse(
  response: Response,
): Promise<OrganizationSignup> {
  if (response.status === 401) {
    throw new AuthenticationRequiredError();
  }
  if (!response.ok) {
    throw new Error("Organization signup request failed");
  }
  return (await response.json()) as OrganizationSignup;
}

export async function createOrganizationSignup(
  input: OrganizationSignupInput,
): Promise<OrganizationSignup> {
  return organizationResponse(
    await fetch(`${apiBaseUrl}/api/v1/organization-signups`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
    }),
  );
}

export async function loadOrganizationSignup(
  organizationId: string,
  signal?: AbortSignal,
): Promise<OrganizationSignup> {
  return organizationResponse(
    await fetch(
      `${apiBaseUrl}/api/v1/organization-signups/${organizationId}`,
      {
        credentials: "include",
        signal,
      },
    ),
  );
}

export async function loadOrganizations(
  signal?: AbortSignal,
): Promise<OrganizationSummary[]> {
  const response = await fetch(`${apiBaseUrl}/api/v1/organizations`, {
    credentials: "include",
    signal,
  });
  if (response.status === 401) {
    throw new AuthenticationRequiredError();
  }
  if (!response.ok) {
    throw new Error("Organization list request failed");
  }
  const result = (await response.json()) as {
    organizations: OrganizationSummary[];
  };
  return result.organizations;
}

export async function loadOrganizationWorkspace(
  organizationId: string,
  signal?: AbortSignal,
): Promise<OrganizationWorkspace> {
  const response = await fetch(
    `${apiBaseUrl}/api/v1/organizations/${organizationId}`,
    {
      credentials: "include",
      signal,
    },
  );
  if (response.status === 401) {
    throw new AuthenticationRequiredError();
  }
  if (!response.ok) {
    throw new Error("Organization workspace request failed");
  }
  return (await response.json()) as OrganizationWorkspace;
}

async function billingResponse<T>(response: Response): Promise<T> {
  if (response.status === 401) {
    throw new AuthenticationRequiredError();
  }
  if (!response.ok) {
    throw new Error("Organization billing request failed");
  }
  return (await response.json()) as T;
}

export async function loadSeatProjection(
  organizationId: string,
  signal?: AbortSignal,
): Promise<SeatProjection> {
  return billingResponse(
    await fetch(
      `${apiBaseUrl}/api/v1/organizations/${organizationId}/billing/seats`,
      { credentials: "include", signal },
    ),
  );
}

export async function previewSeatIncrease(
  organizationId: string,
  targetSeats: number,
  expectedVersion: number,
): Promise<SeatIncreasePreview> {
  return billingResponse(
    await fetch(
      `${apiBaseUrl}/api/v1/organizations/${organizationId}/billing/seats/increase-preview`,
      {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          target_seats: targetSeats,
          expected_version: expectedVersion,
        }),
      },
    ),
  );
}

export async function changeSeatCapacity(
  organizationId: string,
  targetSeats: number,
  expectedVersion: number,
  previewId: string | null,
): Promise<SeatProjection> {
  return billingResponse(
    await fetch(
      `${apiBaseUrl}/api/v1/organizations/${organizationId}/billing/seats`,
      {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          target_seats: targetSeats,
          expected_version: expectedVersion,
          preview_id: previewId,
          confirmed: true,
        }),
      },
    ),
  );
}

async function invitationResponse<T>(response: Response): Promise<T> {
  if (response.status === 401) throw new AuthenticationRequiredError();
  if (!response.ok) throw new Error("Invitation request failed");
  return (await response.json()) as T;
}

export async function loadInvitations(organizationId: string): Promise<OrganizationInvitation[]> {
  return invitationResponse(await fetch(`${apiBaseUrl}/api/v1/organizations/${organizationId}/invitations`, { credentials: "include" }));
}

export async function inviteOrganizationUser(organizationId: string, email: string, role: OrganizationInvitation["role"] = "member", groupIds: string[] = []): Promise<OrganizationInvitation> {
  return invitationResponse(await fetch(`${apiBaseUrl}/api/v1/organizations/${organizationId}/invitations`, { method: "POST", credentials: "include", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email, role, ...(groupIds.length ? { group_ids: groupIds } : {}) }) }));
}

export type BulkInvitationResult = { invite: string[]; skipped: Array<{ email: string; reason: "invalid" | "duplicate" | "member" | "invited" }>; seats_needed: number; created: number };
export class SeatsNeededError extends Error {
  constructor(readonly seats: number) { super("seats needed"); }
}
/** Invite up to 50 people; a dry run only previews (Yearclock V2). */
export async function inviteMany(organizationId: string, emails: string[], role: OrganizationInvitation["role"], groupIds: string[], dryRun: boolean): Promise<BulkInvitationResult> {
  const response = await fetch(`${apiBaseUrl}/api/v1/organizations/${organizationId}/invitations/bulk`, { method: "POST", credentials: "include", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ emails, role, group_ids: groupIds, dry_run: dryRun }) });
  if (response.status === 409) {
    const detail = ((await response.json().catch(() => null)) as { detail?: { reason?: string; seats_needed?: number } } | null)?.detail;
    if (detail?.reason === "seats_needed") throw new SeatsNeededError(detail.seats_needed ?? 0);
  }
  if (!response.ok) throw new Error("Bulk invitation failed");
  return (await response.json()) as BulkInvitationResult;
}

export async function resendInvitation(organizationId: string, invitation: OrganizationInvitation): Promise<OrganizationInvitation> {
  return invitationResponse(await fetch(`${apiBaseUrl}/api/v1/organizations/${organizationId}/invitations/${invitation.id}/resend?expected_version=${invitation.version}`, { method: "POST", credentials: "include" }));
}

export async function revokeInvitation(organizationId: string, invitation: OrganizationInvitation): Promise<void> {
  const response = await fetch(`${apiBaseUrl}/api/v1/organizations/${organizationId}/invitations/${invitation.id}?expected_version=${invitation.version}`, { method: "DELETE", credentials: "include" });
  if (response.status === 401) throw new AuthenticationRequiredError();
  if (!response.ok) throw new Error("Invitation request failed");
}

export async function acceptInvitation(token: string): Promise<OrganizationInvitation> {
  return invitationResponse(await fetch(`${apiBaseUrl}/api/v1/invitations/accept`, { method: "POST", credentials: "include", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ token }) }));
}

export type GroupMember = { membership_id: string; name: string; email: string };
export type Group = { id: string; name: string; version: number; members: GroupMember[] };
export type OwnGroup = { id: string; name: string; access: Array<{ yearclock_id: string; yearclock_name: string; role: "editor" | "viewer" }> };
export type GroupImpact = { members: number; yearclocks: number; losing_access: Array<{ name: string; yearclock_name: string }> };
export class GroupConfirmationRequiredError extends Error {
  constructor(readonly impact: GroupImpact) { super("confirmation required"); }
}
export class DuplicateNameError extends Error {}

async function groupResponse<T>(response: Response): Promise<T> {
  if (response.status === 409) {
    const detail = ((await response.clone().json().catch(() => null)) as { detail?: Record<string, unknown> } | null)?.detail;
    if (detail?.reason === "confirmation_required") throw new GroupConfirmationRequiredError(detail as unknown as GroupImpact);
    if (detail?.reason === "duplicate_name") throw new DuplicateNameError("duplicate");
  }
  return yearclockResponse(response);
}
const groupsUrl = (organizationId: string) => `${apiBaseUrl}/api/v1/organizations/${organizationId}/groups`;
export async function loadGroups(organizationId: string): Promise<Group[]> { return groupResponse(await fetch(groupsUrl(organizationId), { credentials: "include" })); }
export async function loadOwnGroups(organizationId: string): Promise<OwnGroup[]> { return groupResponse(await fetch(`${apiBaseUrl}/api/v1/organizations/${organizationId}/me/groups`, { credentials: "include" })); }
export async function createGroup(organizationId: string, name: string): Promise<Group> { return groupResponse(await fetch(groupsUrl(organizationId), { method: "POST", credentials: "include", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name }) })); }
export async function renameGroup(organizationId: string, group: Group, name: string): Promise<Group> { return groupResponse(await fetch(`${groupsUrl(organizationId)}/${group.id}`, { method: "PATCH", credentials: "include", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name, expected_version: group.version }) })); }
export async function deleteGroup(organizationId: string, group: Group, confirm = false): Promise<void> {
  const response = await fetch(`${groupsUrl(organizationId)}/${group.id}?expected_version=${group.version}${confirm ? "&confirm=true" : ""}`, { method: "DELETE", credentials: "include" });
  if (response.status === 204) return;
  await groupResponse(response);
}
export async function addGroupMember(organizationId: string, group: Group, membershipId: string): Promise<Group> { return groupResponse(await fetch(`${groupsUrl(organizationId)}/${group.id}/members/${membershipId}`, { method: "PUT", credentials: "include" })); }
export async function removeGroupMember(organizationId: string, group: Group, membershipId: string): Promise<Group> { return groupResponse(await fetch(`${groupsUrl(organizationId)}/${group.id}/members/${membershipId}`, { method: "DELETE", credentials: "include" })); }

export type GroupGrant = { group_id: string; name: string; role: "editor" | "viewer"; version: number };
export async function loadGroupGrants(organizationId: string, yearclockId: string): Promise<GroupGrant[]> {
  return yearclockResponse(await fetch(`${apiBaseUrl}/api/v1/organizations/${organizationId}/yearclocks/${yearclockId}/group-access`, { credentials: "include" }));
}
export async function grantGroupAccess(organizationId: string, yearclockId: string, groupId: string, role: GroupGrant["role"], existing?: GroupGrant): Promise<GroupGrant> {
  return yearclockResponse(await fetch(`${apiBaseUrl}/api/v1/organizations/${organizationId}/yearclocks/${yearclockId}/group-access`, { method: "PUT", credentials: "include", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ group_id: groupId, role, ...(existing ? { expected_version: existing.version } : {}) }) }));
}
export async function revokeGroupAccess(organizationId: string, yearclockId: string, grant: GroupGrant): Promise<void> {
  const response = await fetch(`${apiBaseUrl}/api/v1/organizations/${organizationId}/yearclocks/${yearclockId}/group-access/${grant.group_id}?expected_version=${grant.version}`, { method: "DELETE", credentials: "include" });
  if (!response.ok) throw new Error("Group access request failed");
}

export type PersonAccess = { person: { membership_id: string; name: string; email: string; organization_role: string }; yearclocks: Array<{ id: string; name: string; archived: boolean; role: "editor" | "viewer"; sources: import("./access-sources").AccessSource[] }> };
export type YearclockPeople = { id: string; name: string; people: Array<{ membership_id: string; name: string; email: string; organization_role: string; role: "editor" | "viewer"; sources: import("./access-sources").AccessSource[] }> };
export async function loadPersonAccess(organizationId: string, membershipId: string): Promise<PersonAccess> {
  return yearclockResponse(await fetch(`${apiBaseUrl}/api/v1/organizations/${organizationId}/access-overview/people/${membershipId}`, { credentials: "include" }));
}
export async function loadYearclockPeople(organizationId: string, yearclockId: string): Promise<YearclockPeople> {
  return yearclockResponse(await fetch(`${apiBaseUrl}/api/v1/organizations/${organizationId}/access-overview/yearclocks/${yearclockId}`, { credentials: "include" }));
}

export async function loadMemberships(organizationId: string): Promise<OrganizationMembership[]> {
  return invitationResponse(await fetch(`${apiBaseUrl}/api/v1/organizations/${organizationId}/memberships`, { credentials: "include" }));
}

export async function changeMembershipRole(organizationId: string, membership: OrganizationMembership, role: OrganizationMembership["role"]): Promise<OrganizationMembership> {
  return invitationResponse(await fetch(`${apiBaseUrl}/api/v1/organizations/${organizationId}/memberships/${membership.id}`, { method: "PATCH", credentials: "include", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ role, expected_version: membership.version }) }));
}

export async function removeMembership(organizationId: string, membership: OrganizationMembership): Promise<void> {
  const response = await fetch(`${apiBaseUrl}/api/v1/organizations/${organizationId}/memberships/${membership.id}?expected_version=${membership.version}`, { method: "DELETE", credentials: "include" });
  if (response.status === 401) throw new AuthenticationRequiredError();
  if (!response.ok) throw new Error("Membership request failed");
}

/** One action: the person becomes an Owner and, unless the caller keeps the role, the caller becomes an Administrator. */
export async function transferOwnership(organizationId: string, membership: OrganizationMembership, keepOwner: boolean): Promise<OrganizationMembership> {
  return invitationResponse(await fetch(`${apiBaseUrl}/api/v1/organizations/${organizationId}/memberships/${membership.id}/transfer-ownership`, { method: "POST", credentials: "include", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ keep_owner: keepOwner, expected_version: membership.version }) }));
}

export type LeaveOutcome = "left" | "successor_required" | "last_member";

/** Leave the Organization; the only Owner names a successor, who becomes an Owner in the same action. */
export async function leaveOrganization(organizationId: string, membershipId: string, successorMembershipId?: string): Promise<LeaveOutcome> {
  const response = await fetch(`${apiBaseUrl}/api/v1/organizations/${organizationId}/memberships/${membershipId}/leave`, { method: "POST", credentials: "include", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ successor_membership_id: successorMembershipId ?? null }) });
  if (response.status === 401) throw new AuthenticationRequiredError();
  if (response.status === 204) return "left";
  const reason = response.status === 409 ? ((await response.json().catch(() => null)) as { detail?: { reason?: string } } | null)?.detail?.reason : undefined;
  if (reason === "successor_required" || reason === "last_member") return reason;
  throw new Error("Leave request failed");
}

export class LimitReachedError extends Error {
  constructor(readonly limit: string, readonly maximum: number) { super(`limit reached: ${limit}`); }
}

async function yearclockResponse<T>(response: Response): Promise<T> {
  if (response.status === 401) throw new AuthenticationRequiredError();
  if (response.status === 409) {
    const detail = ((await response.json().catch(() => null)) as { detail?: { reason?: string; limit?: string; maximum?: number } } | null)?.detail;
    if (detail?.reason === "limit_reached") throw new LimitReachedError(detail.limit ?? "", detail.maximum ?? 0);
    throw new ConflictError("The resource changed");
  }
  if (!response.ok) throw new Error("Yearclock request failed");
  return (await response.json()) as T;
}

export async function loadManagedYearclocks(organizationId: string, includeArchived = true): Promise<ManagedYearclock[]> {
  return yearclockResponse(await fetch(`${apiBaseUrl}/api/v1/organizations/${organizationId}/yearclocks?include_archived=${includeArchived}&include_deleted=true`, { credentials: "include" }));
}

export async function deleteYearclock(organizationId: string, yearclock: ManagedYearclock): Promise<void> {
  const response = await fetch(`${apiBaseUrl}/api/v1/organizations/${organizationId}/yearclocks/${yearclock.id}?expected_version=${yearclock.version}`, { method: "DELETE", credentials: "include" });
  if (response.status === 401) throw new AuthenticationRequiredError();
  if (response.status === 409) throw new ConflictError("The Yearclock changed");
  if (!response.ok) throw new Error("Yearclock request failed");
}

export async function recoverYearclock(organizationId: string, yearclock: ManagedYearclock): Promise<ManagedYearclock> {
  return yearclockResponse(await fetch(`${apiBaseUrl}/api/v1/organizations/${organizationId}/yearclocks/${yearclock.id}/recover?expected_version=${yearclock.version}`, { method: "POST", credentials: "include" }));
}

export async function createYearclock(organizationId: string, name: string): Promise<ManagedYearclock> {
  return yearclockResponse(await fetch(`${apiBaseUrl}/api/v1/organizations/${organizationId}/yearclocks`, { method: "POST", credentials: "include", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name }) }));
}

export async function renameYearclock(organizationId: string, yearclock: ManagedYearclock, name: string): Promise<ManagedYearclock> {
  return yearclockResponse(await fetch(`${apiBaseUrl}/api/v1/organizations/${organizationId}/yearclocks/${yearclock.id}`, { method: "PATCH", credentials: "include", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name, expected_version: yearclock.version }) }));
}

export async function archiveYearclock(organizationId: string, yearclock: ManagedYearclock, restore = false): Promise<ManagedYearclock> {
  const action = restore ? "restore" : "archive";
  return yearclockResponse(await fetch(`${apiBaseUrl}/api/v1/organizations/${organizationId}/yearclocks/${yearclock.id}/${action}`, { method: "POST", credentials: "include", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name: yearclock.name, expected_version: yearclock.version }) }));
}

export async function reorderYearclocks(organizationId: string, yearclocks: ManagedYearclock[], orderedIds: string[]): Promise<ManagedYearclock[]> {
  const expectedVersions = Object.fromEntries(yearclocks.map((yearclock) => [yearclock.id, yearclock.version]));
  return yearclockResponse(await fetch(`${apiBaseUrl}/api/v1/organizations/${organizationId}/yearclocks/order`, { method: "PUT", credentials: "include", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ordered_ids: orderedIds, expected_versions: expectedVersions }) }));
}

export async function createLane(organizationId: string, yearclockId: string, name: string): Promise<Lane> {
  return yearclockResponse(await fetch(`${apiBaseUrl}/api/v1/organizations/${organizationId}/yearclocks/${yearclockId}/lanes`, { method: "POST", credentials: "include", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name }) }));
}

export async function copyLane(organizationId: string, yearclockId: string, sourceLaneId: string, includeEvents: boolean): Promise<{ lane: Lane; events: number; series: number; categories_created: number }> {
  return yearclockResponse(await fetch(`${apiBaseUrl}/api/v1/organizations/${organizationId}/yearclocks/${yearclockId}/lanes/copy`, { method: "POST", credentials: "include", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ source_lane_id: sourceLaneId, include_events: includeEvents }) }));
}

export async function linkLane(organizationId: string, yearclockId: string, sourceLaneId: string): Promise<Lane> {
  return yearclockResponse(await fetch(`${apiBaseUrl}/api/v1/organizations/${organizationId}/yearclocks/${yearclockId}/lanes/link`, { method: "POST", credentials: "include", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ source_lane_id: sourceLaneId }) }));
}

export async function renameLane(organizationId: string, yearclockId: string, lane: Lane, name: string, appearance: { tint?: string | null; height?: "normal" | "tall" } = {}): Promise<Lane> {
  return yearclockResponse(await fetch(`${apiBaseUrl}/api/v1/organizations/${organizationId}/yearclocks/${yearclockId}/lanes/${lane.id}`, { method: "PATCH", credentials: "include", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name, ...appearance, expected_version: lane.version }) }));
}

export async function reorderLanes(organizationId: string, yearclock: { id: string; version: number }, orderedIds: string[]): Promise<Lane[]> {
  return yearclockResponse(await fetch(`${apiBaseUrl}/api/v1/organizations/${organizationId}/yearclocks/${yearclock.id}/lanes/order`, { method: "PUT", credentials: "include", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ordered_ids: orderedIds, expected_version: yearclock.version }) }));
}

export class LaneHasEventsError extends Error {
  constructor(readonly events: number, readonly series: number) { super("Lane has Events"); }
}

export async function deleteLane(organizationId: string, yearclockId: string, lane: Lane): Promise<void> {
  const response = await fetch(`${apiBaseUrl}/api/v1/organizations/${organizationId}/yearclocks/${yearclockId}/lanes/${lane.id}?expected_version=${lane.version}`, { method: "DELETE", credentials: "include" });
  if (response.status === 401) throw new AuthenticationRequiredError();
  if (response.status === 409) {
    const detail = ((await response.json()) as { detail?: { reason?: string; events?: number; series?: number } }).detail;
    if (detail?.reason === "lane_has_events") throw new LaneHasEventsError(detail.events ?? 0, detail.series ?? 0);
    throw new ConflictError(detail?.reason ?? "The Lane changed");
  }
  if (!response.ok) throw new Error("Lane request failed");
}

export async function moveLaneEvents(organizationId: string, yearclockId: string, lane: Lane, targetLaneId: string): Promise<void> {
  await yearclockResponse(await fetch(`${apiBaseUrl}/api/v1/organizations/${organizationId}/yearclocks/${yearclockId}/lanes/${lane.id}/move-events`, { method: "POST", credentials: "include", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ target_lane_id: targetLaneId, expected_version: lane.version }) }));
}

export async function loadYearclockAccess(organizationId: string, yearclockId: string): Promise<YearclockAccessGrant[]> {
  return yearclockResponse(await fetch(`${apiBaseUrl}/api/v1/organizations/${organizationId}/yearclocks/${yearclockId}/access`, { credentials: "include" }));
}

export async function grantYearclockAccess(organizationId: string, yearclockId: string, userAccountId: string, role: YearclockAccessGrant["role"]): Promise<YearclockAccessGrant> {
  return yearclockResponse(await fetch(`${apiBaseUrl}/api/v1/organizations/${organizationId}/yearclocks/${yearclockId}/access`, { method: "PUT", credentials: "include", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ user_account_id: userAccountId, role }) }));
}

export async function revokeYearclockAccess(organizationId: string, yearclockId: string, grant: YearclockAccessGrant): Promise<void> {
  const response = await fetch(`${apiBaseUrl}/api/v1/organizations/${organizationId}/yearclocks/${yearclockId}/access/${grant.user_account_id}?expected_version=${grant.version}`, { method: "DELETE", credentials: "include" });
  if (response.status === 401) throw new AuthenticationRequiredError();
  if (!response.ok) throw new Error("Yearclock access request failed");
}

export async function loadEvents(organizationId: string, yearclockId: string, windowStart?: string, includeSkipped = false, months = 12): Promise<YearclockEvent[]> {
  const params = new URLSearchParams();
  if (windowStart) params.set("window_start", windowStart);
  if (months !== 12) params.set("months", String(months));
  if (includeSkipped) params.set("include_skipped", "true");
  const query = params.size ? `?${params.toString()}` : "";
  return yearclockResponse(await fetch(`${apiBaseUrl}/api/v1/organizations/${organizationId}/yearclocks/${yearclockId}/events${query}`, { credentials: "include" }));
}

export async function createEvent(organizationId: string, yearclockId: string, input: EventInput): Promise<YearclockEvent> {
  return yearclockResponse(await fetch(`${apiBaseUrl}/api/v1/organizations/${organizationId}/yearclocks/${yearclockId}/events`, { method: "POST", credentials: "include", headers: { "Content-Type": "application/json" }, body: JSON.stringify(input) }));
}

export async function updateEvent(organizationId: string, yearclockId: string, event: YearclockEvent, input: EventInput): Promise<YearclockEvent> {
  return yearclockResponse(await fetch(`${apiBaseUrl}/api/v1/organizations/${organizationId}/yearclocks/${yearclockId}/events/${event.id}`, { method: "PATCH", credentials: "include", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ...input, expected_version: event.version }) }));
}

export type BulkAction = { action: "move"; lane_id: string } | { action: "categorize"; category_id: string | null } | { action: "label"; add_label_ids?: string[]; remove_label_ids?: string[] } | { action: "delete" };
export async function bulkEdit(organizationId: string, yearclockId: string, events: YearclockEvent[], change: BulkAction): Promise<{ bulk_id: string; changed: number; items: YearclockEvent[] }> {
  return yearclockResponse(await fetch(`${apiBaseUrl}/api/v1/organizations/${organizationId}/yearclocks/${yearclockId}/events/bulk`, { method: "POST", credentials: "include", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ items: events.map((event) => ({ id: event.id, expected_version: event.version })), ...change }) }));
}
export type PlanAgainInput = { season_start: string; lane_ids: string[]; category_ids: string[]; include_uncategorized: boolean; date_rule: "same_date" | "same_weekday" };
export type PlanAgainResult = { to_create: number; skipped_existing: number; limit_exceeded: boolean; maximum: number; created_ids: string[] };
export async function planAgain(organizationId: string, yearclockId: string, input: PlanAgainInput, dryRun: boolean): Promise<PlanAgainResult> {
  return yearclockResponse(await fetch(`${apiBaseUrl}/api/v1/organizations/${organizationId}/yearclocks/${yearclockId}/plan-again`, { method: "POST", credentials: "include", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ...input, dry_run: dryRun }) }));
}
export async function loadEventHistory(organizationId: string, yearclockId: string, eventId: string, offset = 0): Promise<import("./yearclock/history").HistoryPage> {
  return yearclockResponse(await fetch(`${apiBaseUrl}/api/v1/organizations/${organizationId}/yearclocks/${yearclockId}/events/${eventId}/history?offset=${offset}`, { credentials: "include" }));
}
export type RestorePreview = { changes: import("./yearclock/history").HistoryChange[]; category_removed: boolean; labels_removed: number; lane_missing: boolean };
export async function previewVersionRestore(organizationId: string, yearclockId: string, eventId: string, revisionId: string): Promise<RestorePreview> {
  return yearclockResponse(await fetch(`${apiBaseUrl}/api/v1/organizations/${organizationId}/yearclocks/${yearclockId}/events/${eventId}/history/${revisionId}/restore-preview`, { credentials: "include" }));
}
export async function restoreVersion(organizationId: string, yearclockId: string, event: YearclockEvent, revisionId: string, laneId?: string): Promise<YearclockEvent> {
  return yearclockResponse(await fetch(`${apiBaseUrl}/api/v1/organizations/${organizationId}/yearclocks/${yearclockId}/events/${event.id}/history/${revisionId}/restore`, { method: "POST", credentials: "include", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ expected_version: event.version, ...(laneId ? { lane_id: laneId } : {}) }) }));
}
export async function deleteEvent(organizationId: string, yearclockId: string, event: YearclockEvent): Promise<void> {
  const response = await fetch(`${apiBaseUrl}/api/v1/organizations/${organizationId}/yearclocks/${yearclockId}/events/${event.id}?expected_version=${event.version}`, { method: "DELETE", credentials: "include" });
  if (response.status === 401) throw new AuthenticationRequiredError();
  if (response.status === 409) throw new ConflictError("The Event changed");
  if (!response.ok) throw new Error("Event request failed");
}
export async function loadDeletedEvents(organizationId: string, yearclockId: string): Promise<YearclockEvent[]> {
  return yearclockResponse(await fetch(`${apiBaseUrl}/api/v1/organizations/${organizationId}/yearclocks/${yearclockId}/deleted-events`, { credentials: "include" }));
}
export async function restoreEvent(organizationId: string, yearclockId: string, event: YearclockEvent): Promise<YearclockEvent> {
  return yearclockResponse(await fetch(`${apiBaseUrl}/api/v1/organizations/${organizationId}/yearclocks/${yearclockId}/events/${event.id}/restore?expected_version=${event.version}`, { method: "POST", credentials: "include" }));
}
export async function skipOccurrence(organizationId: string, yearclockId: string, occurrenceId: string, skipped = true): Promise<void> { await yearclockResponse(await fetch(`${apiBaseUrl}/api/v1/organizations/${organizationId}/yearclocks/${yearclockId}/occurrences/${occurrenceId}/skip?skipped=${skipped}`, { method: "POST", credentials: "include" })); }
export async function editOccurrence(organizationId: string, yearclockId: string, event: YearclockEvent, input: OccurrenceEdit): Promise<void> { await yearclockResponse(await fetch(`${apiBaseUrl}/api/v1/organizations/${organizationId}/yearclocks/${yearclockId}/occurrences/${event.occurrence_id}`, { method: "PATCH", credentials: "include", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ...input, expected_version: event.version }) })); }
export async function restoreOccurrence(organizationId: string, yearclockId: string, event: YearclockEvent): Promise<void> { await yearclockResponse(await fetch(`${apiBaseUrl}/api/v1/organizations/${organizationId}/yearclocks/${yearclockId}/occurrences/${event.occurrence_id}/restore?expected_version=${event.version}`, { method: "POST", credentials: "include" })); }
export async function loadSeries(organizationId: string, yearclockId: string, seriesId: string): Promise<YearclockSeries> { return yearclockResponse(await fetch(`${apiBaseUrl}/api/v1/organizations/${organizationId}/yearclocks/${yearclockId}/series/${seriesId}`, { credentials: "include" })); }
export async function splitSeries(organizationId: string, yearclockId: string, series: YearclockSeries, event: YearclockEvent, changes: SeriesChanges): Promise<YearclockSeries> { return yearclockResponse(await fetch(`${apiBaseUrl}/api/v1/organizations/${organizationId}/yearclocks/${yearclockId}/series/${series.id}/split`, { method: "POST", credentials: "include", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ...changes, from_occurrence_id: event.occurrence_id, expected_version: series.version }) })); }
export async function endSeries(organizationId: string, yearclockId: string, series: YearclockSeries, event: YearclockEvent): Promise<{ removed_occurrences: number }> { return yearclockResponse(await fetch(`${apiBaseUrl}/api/v1/organizations/${organizationId}/yearclocks/${yearclockId}/series/${series.id}/end`, { method: "POST", credentials: "include", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ from_occurrence_id: event.occurrence_id, expected_version: series.version }) })); }

export async function loadCategories(organizationId: string, yearclockId: string): Promise<YearclockCategory[]> { return yearclockResponse(await fetch(`${apiBaseUrl}/api/v1/organizations/${organizationId}/yearclocks/${yearclockId}/categories`, { credentials: "include" })); }
export async function createCategory(organizationId: string, yearclockId: string, name: string, color: string | null): Promise<YearclockCategory> { return yearclockResponse(await fetch(`${apiBaseUrl}/api/v1/organizations/${organizationId}/yearclocks/${yearclockId}/categories`, { method: "POST", credentials: "include", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name, color }) })); }
export async function updateCategory(organizationId: string, yearclockId: string, category: YearclockCategory, name: string, color: string | null): Promise<YearclockCategory> { return yearclockResponse(await fetch(`${apiBaseUrl}/api/v1/organizations/${organizationId}/yearclocks/${yearclockId}/categories/${category.id}`, { method: "PATCH", credentials: "include", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name, color, expected_version: category.version }) })); }
export async function reorderCategories(organizationId: string, yearclockId: string, categories: YearclockCategory[], orderedIds: string[]): Promise<YearclockCategory[]> { const expectedVersions = Object.fromEntries(categories.map((category) => [category.id, category.version])); return yearclockResponse(await fetch(`${apiBaseUrl}/api/v1/organizations/${organizationId}/yearclocks/${yearclockId}/categories/order`, { method: "PUT", credentials: "include", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ordered_ids: orderedIds, expected_versions: expectedVersions }) })); }
export async function deleteCategory(organizationId: string, yearclockId: string, category: YearclockCategory): Promise<void> { const response = await fetch(`${apiBaseUrl}/api/v1/organizations/${organizationId}/yearclocks/${yearclockId}/categories/${category.id}?expected_version=${category.version}&confirm=true`, { method: "DELETE", credentials: "include" }); if (!response.ok) throw new Error("Category request failed"); }
export async function createSeries(organizationId: string, yearclockId: string, input: SeriesInput): Promise<void> { await yearclockResponse(await fetch(`${apiBaseUrl}/api/v1/organizations/${organizationId}/yearclocks/${yearclockId}/series`, { method: "POST", credentials: "include", headers: { "Content-Type": "application/json" }, body: JSON.stringify(input) })); }

/** Label swatch palette; keep in sync with `LABEL_COLORS` in backend/app/label_routes.py. */
export const LABEL_COLORS = ["#1f5f99", "#2e7d32", "#8e24aa", "#c62828", "#ef6c00", "#00838f", "#5d4037", "#455a64", "#ad1457", "#283593", "#827717", "#6a1b9a"] as const;

export type Label = { id: string; name: string; color: string; version: number; usage: number };

async function labelResponse<T>(response: Response): Promise<T> {
  if (response.status === 401) throw new AuthenticationRequiredError();
  if (response.status === 409) {
    const detail = ((await response.json().catch(() => null)) as { detail?: { reason?: string; limit?: string; maximum?: number } } | null)?.detail;
    if (detail?.reason === "limit_reached") throw new LimitReachedError(detail.limit ?? "", detail.maximum ?? 0);
    throw new ConflictError(detail?.reason ?? "The Label changed");
  }
  if (!response.ok) throw new Error("Label request failed");
  return (response.status === 204 ? undefined : await response.json()) as T;
}

const labelsUrl = (organizationId: string) => `${apiBaseUrl}/api/v1/organizations/${organizationId}/labels`;
const json = (method: string, body: unknown): RequestInit => ({ method, credentials: "include", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

export const loadLabels = async (organizationId: string): Promise<Label[]> => labelResponse(await fetch(labelsUrl(organizationId), { credentials: "include" }));
export const createLabel = async (organizationId: string, name: string, color: string): Promise<Label> => labelResponse(await fetch(labelsUrl(organizationId), json("POST", { name, color })));
export const updateLabel = async (organizationId: string, label: Label, name: string, color: string): Promise<Label> => labelResponse(await fetch(`${labelsUrl(organizationId)}/${label.id}`, json("PATCH", { name, color, expected_version: label.version })));
export const mergeLabel = async (organizationId: string, label: Label, into: Label): Promise<Label> => labelResponse(await fetch(`${labelsUrl(organizationId)}/${label.id}/merge`, json("POST", { into_label_id: into.id, expected_version: label.version, confirm: true })));
export const deleteLabel = async (organizationId: string, label: Label): Promise<void> => labelResponse(await fetch(`${labelsUrl(organizationId)}/${label.id}?expected_version=${label.version}&confirm=true`, { method: "DELETE", credentials: "include" }));

const organizationCategoriesUrl = (organizationId: string) => `${apiBaseUrl}/api/v1/organizations/${organizationId}/categories`;

export const loadOrganizationCategories = async (organizationId: string): Promise<YearclockCategory[]> => labelResponse(await fetch(organizationCategoriesUrl(organizationId), { credentials: "include" }));
export const createOrganizationCategory = async (organizationId: string, name: string, color: string): Promise<YearclockCategory> => labelResponse(await fetch(organizationCategoriesUrl(organizationId), json("POST", { name, color })));
export const updateOrganizationCategory = async (organizationId: string, category: YearclockCategory, name: string, color: string): Promise<YearclockCategory> => labelResponse(await fetch(`${organizationCategoriesUrl(organizationId)}/${category.id}`, json("PATCH", { name, color, expected_version: category.version })));
export const reorderOrganizationCategories = async (organizationId: string, categories: YearclockCategory[], orderedIds: string[]): Promise<YearclockCategory[]> => labelResponse(await fetch(`${organizationCategoriesUrl(organizationId)}/order`, json("PUT", { ordered_ids: orderedIds, expected_versions: Object.fromEntries(categories.map((category) => [category.id, category.version])) })));
export const deleteOrganizationCategory = async (organizationId: string, category: YearclockCategory): Promise<void> => labelResponse(await fetch(`${organizationCategoriesUrl(organizationId)}/${category.id}?expected_version=${category.version}&confirm=true`, { method: "DELETE", credentials: "include" }));

export type SearchResult = { items: YearclockEvent[]; next_offset: number | null; total: number; includes_recurring: boolean };

export async function searchYearclock(organizationId: string, yearclockId: string, query: string, offset = 0): Promise<SearchResult> {
  const params = new URLSearchParams({ q: query, offset: String(offset) });
  return yearclockResponse(await fetch(`${apiBaseUrl}/api/v1/organizations/${organizationId}/yearclocks/${yearclockId}/search?${params.toString()}`, { credentials: "include" }));
}

export type McpConnection = { interface_available: boolean; enabled: boolean; platform_blocked: boolean; server_url: string; client_id: string; secret_configured: boolean };

async function mcpResponse<T>(response: Response): Promise<T> {
  if (response.status === 401) throw new AuthenticationRequiredError();
  if (!response.ok) throw new Error("Agent settings request failed");
  return (await response.json()) as T;
}

export async function loadMcpConnection(organizationId: string): Promise<McpConnection> {
  return mcpResponse(await fetch(`${apiBaseUrl}/api/v1/organizations/${organizationId}/mcp`, { credentials: "include" }));
}

export async function setMcpEnabled(organizationId: string, enabled: boolean): Promise<McpConnection> {
  return mcpResponse(await fetch(`${apiBaseUrl}/api/v1/organizations/${organizationId}/mcp`, { method: "PATCH", credentials: "include", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ enabled }) }));
}

/** Every reveal is recorded in the Organization's Activity. */
export async function revealMcpSecret(organizationId: string): Promise<string> {
  return (await mcpResponse<{ client_secret: string }>(await fetch(`${apiBaseUrl}/api/v1/organizations/${organizationId}/mcp/secret`, { method: "POST", credentials: "include" }))).client_secret;
}

export type NextCharge = { status: "scheduled" | "none_cancelled" | "none_ended" | "unavailable"; charge_date: string | null; amount: number | null; currency: string | null; seats: number | null };
export type PaymentState = "paid" | "open" | "failed" | "void" | "uncollectible";
export type PaymentReason = "renewal" | "seat_increase" | "signup" | "other";
export type Payment = { id: string; date: string; amount: number; currency: string; state: PaymentState; reason: PaymentReason; hosted_invoice_url: string | null };
export type Payments = { status: "ok" | "unavailable"; invoices: Payment[] };

/** The next charge as Stripe previews it. A failed request is the same as Stripe being unavailable: the page keeps working. */
export async function loadNextCharge(organizationId: string, signal?: AbortSignal): Promise<NextCharge> {
  try {
    const charge = await billingResponse<NextCharge>(await fetch(`${apiBaseUrl}/api/v1/organizations/${organizationId}/billing/next-charge`, { credentials: "include", signal }));
    if (typeof charge?.status !== "string") throw new Error("Unexpected next charge response");
    return charge;
  } catch (error) {
    if (error instanceof AuthenticationRequiredError || signal?.aborted) throw error;
    return { status: "unavailable", charge_date: null, amount: null, currency: null, seats: null };
  }
}

/** The latest invoices of the Organization's Stripe customer, newest first. */
export async function loadPayments(organizationId: string, signal?: AbortSignal): Promise<Payments> {
  try {
    const payments = await billingResponse<Payments>(await fetch(`${apiBaseUrl}/api/v1/organizations/${organizationId}/billing/invoices`, { credentials: "include", signal }));
    if (!Array.isArray(payments?.invoices)) throw new Error("Unexpected invoices response");
    return payments;
  } catch (error) {
    if (error instanceof AuthenticationRequiredError || signal?.aborted) throw error;
    return { status: "unavailable", invoices: [] };
  }
}
