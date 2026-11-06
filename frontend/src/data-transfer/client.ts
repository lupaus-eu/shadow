import { apiBaseUrl } from "../auth-client";

const base = `${apiBaseUrl}/api/v1/data-transfer`;

export type TransferOrganization = { id: string; name: string; role: "owner" | "admin" };
export type KindCounts = { created: number; updated: number; unchanged: number };
export type TransferIssue = { row: number; type: string | null; column: string | null; reason: string; value: string | null };
export type TransferResult = {
  rows: number;
  organizations: Array<{ id: string; name: string | null; kinds: Record<string, KindCounts>; overwrites_newer: number }>;
  errors: TransferIssue[];
  saved: boolean;
};

/** Too many transfers in the last hour; the server says when to try again. */
export class TransferRateLimitedError extends Error {
  constructor(readonly retryAfterSeconds: number) { super("Rate limited"); }
}

/** The file itself is refused (unreadable, wrong format, too big, too many rows, or a save with errors). */
export class TransferRefusedError extends Error {
  constructor(readonly reason: string, readonly detail: Record<string, unknown>) { super(reason); }
}

async function refusal(response: Response): Promise<Error> {
  const detail = ((await response.json().catch(() => null)) as { detail?: Record<string, unknown> } | null)?.detail ?? {};
  if (response.status === 429) return new TransferRateLimitedError(Number(detail.retry_after_seconds ?? response.headers.get("Retry-After") ?? 60));
  if (typeof detail.reason === "string") return new TransferRefusedError(detail.reason, detail);
  return new Error("Data transfer failed");
}

/** The Organizations where the person is Owner or Admin: the scope of one transfer. */
export async function loadTransferOrganizations(signal?: AbortSignal): Promise<TransferOrganization[]> {
  const response = await fetch(`${base}/organizations`, { credentials: "include", signal });
  if (!response.ok) throw new Error("Scope failed");
  return ((await response.json()) as { organizations: TransferOrganization[] }).organizations;
}

export async function exportAll(): Promise<{ blob: Blob; fileName: string }> {
  const response = await fetch(`${base}/export`, { credentials: "include" });
  if (!response.ok) throw await refusal(response);
  return { blob: await response.blob(), fileName: /filename="([^"]+)"/.exec(response.headers.get("Content-Disposition") ?? "")?.[1] ?? "yearclock-data.csv" };
}

/** Preview (dry run) or save a transfer file; the server reads the file each time and stores nothing. */
export async function importFile(file: File, dryRun: boolean): Promise<TransferResult> {
  const response = await fetch(`${base}/import?dry_run=${dryRun}`, { method: "POST", credentials: "include", headers: { "Content-Type": "text/csv" }, body: file });
  if (response.ok) return (await response.json()) as TransferResult;
  throw await refusal(response);
}
