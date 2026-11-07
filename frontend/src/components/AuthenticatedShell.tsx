import { Route, Routes } from "react-router";

import type { UserAccount } from "../auth-client";
import type { Locale } from "../i18n";
import { AdministrationPage } from "../admin/AdministrationPage";
import { NotificationSettingsPage } from "../notifications/NotificationSettingsPage";
import { NotificationsPage } from "../notifications/NotificationsPage";
import { AccountProvider } from "../shell/AppShell";
import { SignedOutLayout } from "../shell/SignedOutLayout";
import { AnalysisPage } from "../models/AnalysisPage";
import { MetricsPage } from "../models/MetricsPage";
import { TypesPage } from "../models/TypesPage";
import { ModelCanvas } from "../models/ModelCanvas";
import { ModelShell } from "../models/ModelShell";
import { SimulationsPage } from "../models/SimulationsPage";
import { ModelsPage } from "../models/ModelsPage";
import { OrganizationActivation } from "./OrganizationActivation";
import {
  InvitationAcceptance,
  OrganizationHome,
  OrganizationLayout,
  OrganizationMembershipEntry,
  OrganizationNotFound,
} from "./OrganizationEntry";

/** Customer routes for a signed-in person; onboarding and invitations use the signed-out card. */
export function AuthenticatedShell({
  userAccount,
  onLocaleChange,
  onLogout,
}: {
  userAccount: UserAccount;
  onLocaleChange: (locale: Locale) => Promise<void>;
  onLogout: () => void;
}) {
  const locale: Locale = userAccount.locale === "fi" ? "fi" : "en";
  return (
    <AccountProvider value={{ userAccount, locale, onLocaleChange, onLogout }}>
      <Routes>
        <Route path="/invitations/:token" element={<SignedOutLayout wide><InvitationAcceptance locale={locale} /></SignedOutLayout>} />
        <Route path="/organization-signups/*" element={<SignedOutLayout wide><OrganizationActivation userAccount={userAccount} locale={locale} /></SignedOutLayout>} />
        <Route path="/organizations/:organizationId" element={<OrganizationLayout />}>
          <Route index element={<OrganizationHome />} />
          <Route path="models" element={<ModelsPage />} />
          <Route path="models/:modelId" element={<ModelShell />}>
            <Route index element={<ModelCanvas />} />
            <Route path="types" element={<TypesPage />} />
            <Route path="metrics" element={<MetricsPage />} />
            <Route path="simulations" element={<SimulationsPage />} />
            <Route path="analysis" element={<AnalysisPage />} />
          </Route>
          <Route path="notifications" element={<NotificationsPage />} />
          <Route path="notification-settings" element={<NotificationSettingsPage />} />
          <Route path="admin/:section" element={<AdministrationPage />} />
          <Route path="*" element={<OrganizationNotFound />} />
        </Route>
        <Route path="*" element={<OrganizationMembershipEntry userAccount={userAccount} locale={locale} />} />
      </Routes>
    </AccountProvider>
  );
}
