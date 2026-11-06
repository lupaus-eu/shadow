/** Readable Access Sources for the access overview (Yearclock V2). */
export type AccessSource = { kind: "role" | "direct" | "group" | "organization"; role: "editor" | "viewer"; organization_role?: string | null; group_id?: string | null; group_name?: string | null };

export type AccessSourceMessages = { role: (organizationRole: string) => string; direct: string; group: (name: string) => string; organization: string; roles: { editor: string; viewer: string }; organizationRoles: Record<string, string> };

export function describeSource(source: AccessSource, copy: AccessSourceMessages): string {
  const role = copy.roles[source.role];
  if (source.kind === "role") return copy.role(copy.organizationRoles[source.organization_role ?? ""] ?? source.organization_role ?? "");
  if (source.kind === "group") return `${copy.group(source.group_name ?? "")}: ${role}`;
  if (source.kind === "organization") return `${copy.organization}: ${role}`;
  return `${copy.direct}: ${role}`;
}
