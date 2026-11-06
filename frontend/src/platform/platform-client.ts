import { apiBaseUrl, AuthenticationRequiredError } from "../auth-client";

export class CustomerAccountError extends Error {}

export type PlatformSession = { id: string; email: string; display_name: string; locale: "en" | "fi"; roles: Array<"platform_admin" | "support_agent"> };
export type QueueCounts = { pending: number; processing: number; completed: number; failed: number };
export type PlatformHealth = { database: string; email: QueueCounts; jobs: Record<string, QueueCounts>; webhooks: Record<string, number>; organizations: Record<string, number> };
export type PlatformOrganization = {
  id: string;
  name: string;
  status: string;
  subscription: { state: string; writable: boolean; grace_expires_at: string | null; cancel_at_period_end: boolean; current_period_end: string | null };
  purchased_seats: number;
  members: number;
  yearclocks: number;
  activated_at: string | null;
  deletion_requested_at: string | null;
  mcp_enabled: boolean;
  mcp_platform_blocked: boolean;
};
export type PlatformJob = { kind: "email" | "job"; id: string; type: string; organization_id: string | null; status: string; attempts: number; next_attempt_at: string | null; last_error: string | null; created_at: string };

async function platformResponse<T>(response: Response): Promise<T> {
  if (response.status === 401) throw new AuthenticationRequiredError();
  if (!response.ok) throw new Error("Platform request failed");
  return (await response.json()) as T;
}

const get = <T,>(path: string) => fetch(`${apiBaseUrl}/api/v1/platform${path}`, { credentials: "include" }).then((response) => platformResponse<T>(response));

export async function loadPlatformSession(): Promise<PlatformSession> {
  const response = await fetch(`${apiBaseUrl}/api/v1/platform/session`, { credentials: "include" });
  if (response.status === 403) throw new CustomerAccountError();
  return platformResponse<PlatformSession>(response);
}
export const loadPlatformHealth = () => get<PlatformHealth>("/health");
export const loadPlatformOrganizations = () => get<PlatformOrganization[]>("/organizations");
export const loadFailedJobs = () => get<PlatformJob[]>("/jobs?status=failed");

export async function setMcpBlock(organizationId: string, blocked: boolean): Promise<PlatformOrganization> {
  return platformResponse(await fetch(`${apiBaseUrl}/api/v1/platform/organizations/${organizationId}/mcp-block`, { method: "PATCH", credentials: "include", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ blocked }) }));
}

export async function replayJob(job: PlatformJob): Promise<PlatformJob> {
  return platformResponse(await fetch(`${apiBaseUrl}/api/v1/platform/jobs/${job.kind}/${job.id}/replay`, { method: "POST", credentials: "include" }));
}

export const platformLoginUrl = `${apiBaseUrl}/api/v1/auth/login?audience=platform&return_to=${encodeURIComponent("/platform")}`;
export const platformLogoutUrl = `${apiBaseUrl}/api/v1/platform/logout`;

export type SupportStatus = "pending" | "approved" | "rejected" | "revoked" | "expired";
export type SupportGrant = { id: string; organization_id: string; case_reference: string; scope: "read" | "write"; status: SupportStatus; requested_hours: number; requested_by: string; created_at: string; decided_at: string | null; expires_at: string | null };
export type SupportYearclock = { id: string; name: string; lanes: Array<{ id: string; name: string; position: number }>; categories: Array<{ id: string; name: string; color: string | null }> };
export type SupportEvent = { id: string; lane_id: string; category_id: string | null; title: string; starts_on: string; ends_on: string | null; version: number };

export const loadSupportGrants = () => get<SupportGrant[]>("/support-access");
export const loadSupportYearclocks = (grantId: string) => get<SupportYearclock[]>(`/support-access/${grantId}/yearclocks`);
export const loadSupportEvents = (grantId: string, yearclockId: string) => get<SupportEvent[]>(`/support-access/${grantId}/yearclocks/${yearclockId}/events`);

export async function requestSupportAccess(body: { organization_id: string; case_reference: string; scope: "read" | "write"; hours: number }): Promise<SupportGrant> {
  return platformResponse(await fetch(`${apiBaseUrl}/api/v1/platform/support-access`, { method: "POST", credentials: "include", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }));
}
