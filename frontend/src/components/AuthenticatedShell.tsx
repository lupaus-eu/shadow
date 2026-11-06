import { Route, Routes } from "react-router";

import type { UserAccount } from "../auth-client";
import type { Locale } from "../i18n";
import { DataTransferPage } from "../data-transfer/DataTransferPage";
import { AdministrationPage } from "../admin/AdministrationPage";
import { NotificationSettingsPage } from "../notifications/NotificationSettingsPage";
import { NotificationsPage } from "../notifications/NotificationsPage";
import { AccountProvider } from "../shell/AppShell";
import { SignedOutLayout } from "../shell/SignedOutLayout";
import { OrganizationActivation } from "./OrganizationActivation";
import {
  InvitationAcceptance,
  OrganizationHome,
  OrganizationLayout,
  OrganizationMembershipEntry,
  OrganizationNotFound,
  YearclockPage,
  YearclockSettingsPage,
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
        <Route path="/data-transfer" element={<DataTransferPage />} />
        <Route path="/organization-signups/*" element={<SignedOutLayout wide><OrganizationActivation userAccount={userAccount} locale={locale} /></SignedOutLayout>} />
        <Route path="/organizations/:organizationId" element={<OrganizationLayout />}>
          <Route index element={<OrganizationHome />} />
          <Route path="yearclocks/:yearclockId" element={<YearclockPage />} />
          <Route path="yearclocks/:yearclockId/settings" element={<YearclockSettingsPage />} />
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
