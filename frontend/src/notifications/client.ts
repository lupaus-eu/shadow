import { apiBaseUrl, AuthenticationRequiredError } from "../auth-client";
import type { NotificationItem } from "./text";

const base = (organizationId: string) => `${apiBaseUrl}/api/v1/organizations/${organizationId}/notifications`;

async function call(url: string, init?: RequestInit): Promise<Response> {
  const response = await fetch(url, { credentials: "include", ...init });
  if (response.status === 401) throw new AuthenticationRequiredError();
  if (!response.ok) throw new Error("Notification request failed");
  return response;
}

export async function loadNotifications(organizationId: string, { cursor, unread = false }: { cursor?: string | null; unread?: boolean } = {}): Promise<{ items: NotificationItem[]; next_cursor: string | null }> {
  const params = new URLSearchParams();
  if (cursor) params.set("cursor", cursor);
  if (unread) params.set("unread", "true");
  return (await call(`${base(organizationId)}?${params.toString()}`)).json();
}

export async function loadUnreadCount(organizationId: string): Promise<number> {
  return ((await (await call(`${base(organizationId)}/unread-count`)).json()) as { unread: number }).unread;
}

export async function markRead(organizationId: string, id: string): Promise<void> {
  await call(`${base(organizationId)}/${id}/read`, { method: "POST" });
}

export async function markAllRead(organizationId: string): Promise<void> {
  await call(`${base(organizationId)}/read-all`, { method: "POST" });
}

export type SettingItem = { key: string; audience: "everyone" | "managers"; in_app: boolean; email: boolean };
export type SummaryChoice = { frequency: "off" | "daily" | "weekly"; yearclock_ids: string[] | null };
export type Settings = { items: SettingItem[]; summary: SummaryChoice };

const settingsUrl = (organizationId: string) => `${apiBaseUrl}/api/v1/organizations/${organizationId}/notification-settings`;

export async function loadSettings(organizationId: string): Promise<Settings> {
  return (await call(settingsUrl(organizationId))).json();
}

export async function saveSettings(organizationId: string, { items, summary }: Settings): Promise<Settings> {
  const settings = Object.fromEntries(items.map((item) => [item.key, { in_app: item.in_app, email: item.email }]));
  const response = await call(settingsUrl(organizationId), { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ settings, summary }) });
  return response.json();
}
