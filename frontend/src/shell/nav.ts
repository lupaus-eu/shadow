/** The customer navigation model: which pages a role sees and their addresses. */

export type OrganizationRole = "owner" | "admin" | "member";

export const ADMIN_SECTIONS = ["people", "groups", "yearclocks", "classification", "activity", "support", "agents", "billing", "settings"] as const;
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
export const yearclockHref = (organizationId: string, yearclockId: string) => `${organizationHref(organizationId)}/yearclocks/${yearclockId}`;
export const adminHref = (organizationId: string, section: AdminSection) => `${organizationHref(organizationId)}/admin/${section}`;

/** Recent Yearclocks first (as recorded), then the rest in their order; unknown ids are dropped. */
export function sidebarYearclocks<T extends { id: string }>(yearclocks: T[], recentIds: string[] = [], recentLimit = 3): { recent: T[]; others: T[] } {
  const byId = new Map(yearclocks.map((yearclock) => [yearclock.id, yearclock]));
  const recent = recentIds.map((id) => byId.get(id)).filter((item): item is T => item !== undefined).slice(0, recentLimit);
  const shown = new Set(recent.map((item) => item.id));
  return { recent, others: yearclocks.filter((yearclock) => !shown.has(yearclock.id)) };
}
