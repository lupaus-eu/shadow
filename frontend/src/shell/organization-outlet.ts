import { useOutletContext } from "react-router";

import type { Locale } from "../i18n";
import type { OrganizationWorkspace } from "../organization-client";

/** What `OrganizationLayout` hands to the pages nested under `/organizations/:organizationId`. */
export type OrganizationOutlet = { workspace: OrganizationWorkspace; locale: Locale; revision: number; reload: () => void };

export const useOrganization = () => useOutletContext<OrganizationOutlet>();
