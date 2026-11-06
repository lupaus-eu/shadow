/** The customer navigation model: which pages a role sees and their addresses. */

export type OrganizationRole = "owner" | "admin" | "member";

export const ADMIN_SECTIONS = ["people", "activity", "support", "agents", "billing", "settings"] as const;
export type AdminSection = (typeof ADMIN_SECTIONS)[number];

/** Billing and Organization settings (with deletion) are the Owner's; Members have no administration. */
const OWNER_ONLY: ReadonlySet<AdminSection> = new Set(["billing", "settings"]);

export function adminSections(role: OrganizationRole): AdminSection[] {
  if (role === "member") return [];
  return ADMIN_SECTIONS.filter((section) => role === "owner" || !OWNER_ONLY.has(section));
}

export function isAdminSection(value: string | undefined, role: OrganizationRole): value is AdminSection {
  return adminSections(role).includes(value as AdminSection);
}

export const organizationHref = (organizationId: string) => `/organizations/${organizationId}`;
export const modelsHref = (organizationId: string) => `${organizationHref(organizationId)}/models`;
export const modelHref = (organizationId: string, modelId: string) => `${modelsHref(organizationId)}/${modelId}`;
export const adminHref = (organizationId: string, section: AdminSection) => `${organizationHref(organizationId)}/admin/${section}`;
