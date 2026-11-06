import { useEffect, useState } from "react";
import { Link } from "react-router";

import { Section, ROW, ROWS } from "../admin/Section";
import { workspaceMessages } from "../i18n";
import { organizationHref } from "../shell/nav";
import { usePageTitle } from "../shell/AppShell";
import { useOrganization } from "../shell/organization-outlet";
import { Alert, Button, Choice, useToast } from "../ui";
import { loadSettings, saveSettings, type SettingItem, type Settings } from "./client";

/** `/organizations/:id/notification-settings`: which kinds of notification arrive in the app and by email. */
export function NotificationSettingsPage() {
  const { workspace, locale } = useOrganization();
  const copy = workspaceMessages(locale).notifications;
  const organizationId = workspace.organization.id;
  usePageTitle(copy.settings.title);
  const toast = useToast();
  const [settings, setSettings] = useState<Settings | null>(null);
  const items = settings?.items ?? null;
  const [failed, setFailed] = useState(false);
  useEffect(() => { void loadSettings(organizationId).then(setSettings, () => setFailed(true)); }, [organizationId]);
  const change = (key: string, channel: "in_app" | "email", value: boolean) => setSettings((current) => (current ? { ...current, items: current.items.map((item) => (item.key === key ? { ...item, [channel]: value } : item)) } : null));
  async function save() {
    if (!settings) return;
    setFailed(false);
    try { setSettings(await saveSettings(organizationId, settings)); toast(copy.settings.saved); } catch { setFailed(true); }
  }
  const group = (audience: SettingItem["audience"], title: string) => {
    const rows = (items ?? []).filter((item) => item.audience === audience);
    if (rows.length === 0) return null;
    return (
      <fieldset className="m-0 flex flex-col gap-2 border-0 p-0">
        <legend className="mb-1 p-0 text-[13px] font-semibold">{title}</legend>
        <ul className={ROWS}>
          {rows.map((item) => {
            const type = copy.settings.types[item.key as keyof typeof copy.settings.types];
            return (
              <li key={item.key} className={ROW}>
                <span className="flex min-w-0 flex-1 flex-col"><span className="text-[13px] font-medium">{type.name}</span><span className="text-xs text-ink-muted">{type.hint}</span></span>
                <Choice type="checkbox" checked={item.in_app} onChange={(event) => change(item.key, "in_app", event.target.checked)} label={<><span className="sr-only">{type.name}: </span>{copy.settings.inApp}</>} />
                <Choice type="checkbox" checked={item.email} onChange={(event) => change(item.key, "email", event.target.checked)} label={<><span className="sr-only">{type.name}: </span>{copy.settings.email}</>} />
              </li>
            );
          })}
        </ul>
      </fieldset>
    );
  };
  return (
    <Section title={copy.settings.title} description={copy.settings.description} actions={<Link to={`${organizationHref(organizationId)}/notifications`} className="text-[13px]">{copy.title}</Link>}>
      {failed ? <Alert tone="danger" role="alert">{copy.settings.failed}</Alert> : null}
      {group("everyone", copy.settings.groupEveryone)}
      {group("managers", copy.settings.groupManagers)}
      <div><Button variant="primary" disabled={!settings} onClick={() => void save()}>{copy.settings.save}</Button></div>
    </Section>
  );
}
