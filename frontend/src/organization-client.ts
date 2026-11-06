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
    shadow_id: string;
    shadow_name: string;
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
};

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

export class ConfirmationRequiredError extends Error {
  constructor(readonly members: number) { super("confirmation required"); }
}

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

export type BulkInvitationResult = { invite: string[]; skipped: Array<{ email: string; reason: "invalid" | "duplicate" | "member" | "invited" }>; seats_needed: number; created: number };
export class SeatsNeededError extends Error {
  constructor(readonly seats: number) { super("seats needed"); }
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

export class DuplicateNameError extends Error {}

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

const json = (method: string, body: unknown): RequestInit => ({ method, credentials: "include", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

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

export async function loadAuditEvents(organizationId: string, { prefix, offset = 0, limit = 25 }: { prefix?: string; offset?: number; limit?: number } = {}): Promise<{ items: AuditItem[]; next_offset: number | null }> {
  const params = new URLSearchParams({ offset: String(offset), limit: String(limit) });
  if (prefix) params.set("prefix", prefix);
  const response = await fetch(`${apiBaseUrl}/api/v1/organizations/${organizationId}/audit-events?${params.toString()}`, { credentials: "include" });
  if (response.status === 401) throw new AuthenticationRequiredError();
  if (!response.ok) throw new Error("Audit request failed");
  return (await response.json()) as { items: AuditItem[]; next_offset: number | null };
}

export async function inviteOrganizationUser(organizationId: string, email: string, role: OrganizationInvitation["role"] = "member"): Promise<OrganizationInvitation> {
  return invitationResponse(await fetch(`${apiBaseUrl}/api/v1/organizations/${organizationId}/invitations`, { method: "POST", credentials: "include", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email, role }) }));
}

export async function inviteMany(organizationId: string, emails: string[], role: OrganizationInvitation["role"], dryRun: boolean): Promise<BulkInvitationResult> {
  const response = await fetch(`${apiBaseUrl}/api/v1/organizations/${organizationId}/invitations/bulk`, { method: "POST", credentials: "include", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ emails, role, dry_run: dryRun }) });
  if (response.status === 409) {
    const detail = ((await response.json().catch(() => null)) as { detail?: { reason?: string; seats_needed?: number } } | null)?.detail;
    if (detail?.reason === "seats_needed") throw new SeatsNeededError(detail.seats_needed ?? 0);
  }
  if (!response.ok) throw new Error("Bulk invitation failed");
  return (await response.json()) as BulkInvitationResult;
}

