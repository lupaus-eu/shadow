import { apiBaseUrl } from "../auth-client";

/** Too many exports or imports in the last hour; the server says when to try again. */
export class RateLimitedError extends Error {
  constructor(readonly retryAfterSeconds: number) { super("Rate limited"); }
}

export type ExportBody = {
  format: "xlsx" | "csv" | "ics";
  scope: "window" | "all";
  window_start?: string;
  length?: number;
  filters: { lanes: string[]; categories: string[]; labels: string[] };
  locale: "en" | "fi";
};

/** Ask the server for a Yearclock's Events as a file; the response is authorized and audited there. */
export async function exportYearclock(organizationId: string, yearclockId: string, body: ExportBody): Promise<{ blob: Blob; fileName: string }> {
  const response = await fetch(`${apiBaseUrl}/api/v1/organizations/${organizationId}/yearclocks/${yearclockId}/export`, { method: "POST", credentials: "include", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  if (response.status === 429) {
    const detail = ((await response.json().catch(() => null)) as { detail?: { retry_after_seconds?: number } } | null)?.detail;
    throw new RateLimitedError(detail?.retry_after_seconds ?? Number(response.headers.get("Retry-After") ?? 60));
  }
  if (!response.ok) throw new Error("Export failed");
  const fileName = /filename="([^"]+)"/.exec(response.headers.get("Content-Disposition") ?? "")?.[1] ?? `yearclock.${body.format}`;
  return { blob: await response.blob(), fileName };
}

export type ImportIssue = { row: number; column: string | null; reason: string; value: string | null };
export type ImportResult = {
  rows: number;
  create: Array<{ row: number; title: string; starts_on: string; ends_on: string | null; lane: string; category: string | null; labels: string[] }>;
  skipped: Array<{ row: number; title: string; reason: "duplicate" | "series" | "linked" }>;
  errors: ImportIssue[];
  created: number;
};

/** The file itself is refused (unreadable, macros, too big, too many rows, or the Event limit); `reason` says why. */
export class ImportRefusedError extends Error {
  constructor(readonly reason: string, readonly detail: Record<string, unknown>) { super(reason); }
}

/** Preview (dry run) or save an import; the server reads the file each time and stores nothing. */
export async function importEvents(organizationId: string, yearclockId: string, file: File, format: "xlsx" | "csv", dryRun: boolean): Promise<ImportResult> {
  const response = await fetch(`${apiBaseUrl}/api/v1/organizations/${organizationId}/yearclocks/${yearclockId}/import?format=${format}&dry_run=${dryRun}`, { method: "POST", credentials: "include", headers: { "Content-Type": "application/octet-stream" }, body: file });
  if (response.ok) return (await response.json()) as ImportResult;
  const detail = ((await response.json().catch(() => null)) as { detail?: Record<string, unknown> } | null)?.detail ?? {};
  if (response.status === 429) throw new RateLimitedError(Number(detail.retry_after_seconds ?? response.headers.get("Retry-After") ?? 60));
  if ([409, 413, 422].includes(response.status) && typeof detail.reason === "string") throw new ImportRefusedError(detail.reason, detail);
  throw new Error("Import failed");
}

export async function downloadImportTemplate(organizationId: string, yearclockId: string, locale: "en" | "fi"): Promise<{ blob: Blob; fileName: string }> {
  const response = await fetch(`${apiBaseUrl}/api/v1/organizations/${organizationId}/yearclocks/${yearclockId}/import/template?locale=${locale}`, { credentials: "include" });
  if (!response.ok) throw new Error("Template failed");
  return { blob: await response.blob(), fileName: /filename="([^"]+)"/.exec(response.headers.get("Content-Disposition") ?? "")?.[1] ?? `yearclock-import-template-${locale}.xlsx` };
}

/** The Organization Export (Owners only) as a file; the server builds and audits it. */
export async function exportOrganization(organizationId: string): Promise<{ blob: Blob; fileName: string }> {
  const response = await fetch(`${apiBaseUrl}/api/v1/organizations/${organizationId}/export`, { credentials: "include" });
  if (response.status === 429) {
    const detail = ((await response.json().catch(() => null)) as { detail?: { retry_after_seconds?: number } } | null)?.detail;
    throw new RateLimitedError(detail?.retry_after_seconds ?? Number(response.headers.get("Retry-After") ?? 60));
  }
  if (!response.ok) throw new Error("Organization export failed");
  return { blob: await response.blob(), fileName: /filename="([^"]+)"/.exec(response.headers.get("Content-Disposition") ?? "")?.[1] ?? "organization-export.json" };
}
