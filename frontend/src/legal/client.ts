import { apiBaseUrl } from "../auth-client";
import type { Locale } from "../i18n";

const base = `${apiBaseUrl}/api/v1/legal/documents`;

export type LegalAcceptanceMode = "required" | "notice" | "none";
export type LegalDocumentSummary = {
  key: string;
  title: string;
  version: number;
  effective_from: string;
  status: "draft" | "published";
  acceptance: LegalAcceptanceMode;
};
export type LegalDocument = LegalDocumentSummary & { body: string };

/** The document does not exist, or is a draft that this reader may not see. */
export class LegalDocumentNotFoundError extends Error {
  constructor() { super("Legal document not found"); }
}

export async function loadLegalDocuments(locale: Locale, signal?: AbortSignal): Promise<LegalDocumentSummary[]> {
  // The session cookie goes along: a signed-in person also sees the drafts when the operator enabled them.
  const response = await fetch(`${base}?locale=${locale}`, { credentials: "include", signal });
  if (!response.ok) throw new Error("Legal documents could not be loaded");
  const items = (await response.json()) as unknown;
  if (!Array.isArray(items)) throw new Error("Legal documents could not be loaded");
  return items as LegalDocumentSummary[];
}

export async function loadLegalDocument(key: string, locale: Locale, signal?: AbortSignal): Promise<LegalDocument> {
  const response = await fetch(`${base}/${encodeURIComponent(key)}?locale=${locale}`, { credentials: "include", signal });
  if (response.status === 404) throw new LegalDocumentNotFoundError();
  if (!response.ok) throw new Error("The legal document could not be loaded");
  return (await response.json()) as LegalDocument;
}

export type OrganizationLegalDocument = {
  key: string;
  title: string;
  acceptance: LegalAcceptanceMode;
  current_version: number;
  effective_from: string;
  accepted_version: number | null;
  accepted_at: string | null;
  accepted_by_name: string | null;
  accepted_by_former_member: boolean;
  state: "accepted" | "acceptance_due" | "not_required";
};

export async function loadOrganizationLegal(organizationId: string, locale: Locale, signal?: AbortSignal): Promise<OrganizationLegalDocument[]> {
  const response = await fetch(`${apiBaseUrl}/api/v1/organizations/${organizationId}/legal?locale=${locale}`, { credentials: "include", signal });
  if (!response.ok) throw new Error("Legal documents could not be loaded");
  const body = (await response.json()) as { documents?: unknown };
  if (!Array.isArray(body.documents)) throw new Error("Legal documents could not be loaded");
  return body.documents as OrganizationLegalDocument[];
}

export async function acceptLegalDocument(organizationId: string, documentKey: string, version: number, locale: Locale): Promise<OrganizationLegalDocument> {
  const response = await fetch(`${apiBaseUrl}/api/v1/organizations/${organizationId}/legal/acceptances`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ document_key: documentKey, version, locale }),
  });
  if (!response.ok) throw new Error("The acceptance could not be saved");
  return (await response.json()) as OrganizationLegalDocument;
}

/** Published documents an Organization must accept, as the public list shows them. */
export function requiredDocuments(items: LegalDocumentSummary[]): LegalDocumentSummary[] {
  return items.filter((item) => item.status === "published" && item.acceptance === "required");
}

/** Documents due for acceptance whose date has passed (a banner is shown only for these). */
export function dueDocuments(items: OrganizationLegalDocument[], today: string = new Date().toISOString().slice(0, 10)): OrganizationLegalDocument[] {
  return items.filter((item) => item.state === "acceptance_due" && item.effective_from <= today);
}
