import type { ReactNode } from "react";
import { useParams } from "react-router";

import { GroupsPanel } from "../components/GroupsPanel";
import { messages } from "../i18n";
import { usePageTitle } from "../shell/AppShell";
import { isAdminSection, type AdminSection } from "../shell/nav";
import { useOrganization } from "../shell/organization-outlet";
import { Alert } from "../ui";
import { ActivityLog } from "./ActivityPage";
import { ConnectAgent } from "./AgentsPage";
import { BillingContact, SeatCapacity, PaymentHistory, SubscriptionCard } from "./BillingPage";
import { Classification } from "./ClassificationPage";
import { LegalDocuments, LegalDueBanner } from "./LegalPage";
import { Invitations, Memberships } from "./PeoplePage";
import { AdminPage } from "./Section";
import { OrganizationDeletion, OrganizationDetails, OrganizationExport } from "./SettingsPage";
import { SubscriptionNotice } from "./SubscriptionNotice";
import { SupportAccess } from "./SupportPage";
import { YearclockManagement } from "./YearclocksPage";

/** `/organizations/:organizationId/admin/:section`: one administration area, if the role allows it. */
export function AdministrationPage() {
  const { workspace, locale, revision, reload } = useOrganization();
  const { section } = useParams();
  const text = messages(locale).shell;
  const role = workspace.membership.role;
  const organizationId = workspace.organization.id;
  const writable = workspace.subscription.writable;
  const isOwner = role === "owner";
  const allowed = isAdminSection(section, role);
  usePageTitle(allowed ? text.sections[section] : messages(locale).title);
  if (!allowed) return <Alert tone="danger" role="alert">{text.notFound}</Alert>;
  const pages: Record<AdminSection, ReactNode> = {
    people: <>{writable ? <Invitations organizationId={organizationId} locale={locale} isOwner={isOwner} /> : null}<Memberships organizationId={organizationId} locale={locale} isOwner={isOwner} readOnly={!writable} onChanged={reload} /></>,
    groups: <GroupsPanel organizationId={organizationId} locale={locale} writable={writable} />,
    yearclocks: writable ? <YearclockManagement organizationId={organizationId} locale={locale} revision={revision} onChanged={reload} /> : null,
    classification: <Classification organizationId={organizationId} locale={locale} writable={writable} />,
    activity: <ActivityLog organizationId={organizationId} locale={locale} />,
    support: <SupportAccess organizationId={organizationId} locale={locale} />,
    agents: <ConnectAgent organizationId={organizationId} locale={locale} />,
    billing: <><SubscriptionCard organizationId={organizationId} subscription={workspace.subscription} locale={locale} onChanged={reload} /><SeatCapacity organizationId={organizationId} locale={locale} /><PaymentHistory organizationId={organizationId} locale={locale} /><BillingContact organizationId={organizationId} locale={locale} /></>,
    settings: <><OrganizationDetails workspace={workspace} locale={locale} /><OrganizationExport organizationId={organizationId} locale={locale} />{isOwner ? <LegalDocuments organizationId={organizationId} locale={locale} /> : null}<OrganizationDeletion organizationId={organizationId} name={workspace.organization.name} locale={locale} /></>,
  };
  return (
    <AdminPage intro={text.descriptions[section]}>
      {section !== "billing" ? <SubscriptionNotice organizationId={organizationId} subscription={workspace.subscription} isOwner={isOwner} locale={locale} /> : null}
      {section === "billing" ? <LegalDueBanner organizationId={organizationId} locale={locale} isOwner={isOwner} /> : null}
      {pages[section]}
    </AdminPage>
  );
}
