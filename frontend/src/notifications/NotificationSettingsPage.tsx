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
  const summary = settings?.summary;
  const setSummary = (next: Partial<NonNullable<typeof summary>>) => setSettings((current) => (current ? { ...current, summary: { ...current.summary, ...next } } : null));
  const clocks = workspace.yearclocks.filter((clock) => !(clock as { archived_at?: string | null }).archived_at);
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
      {summary ? (
        <fieldset className="m-0 flex flex-col gap-2 border-0 p-0">
          <legend className="mb-1 p-0 text-[13px] font-semibold">{copy.summary.title}</legend>
          <p className="m-0 text-xs text-ink-muted">{copy.summary.description}</p>
          {(["off", "weekly", "daily"] as const).map((value) => <Choice key={value} type="radio" name="summary-frequency" checked={summary.frequency === value} onChange={() => setSummary({ frequency: value })} label={copy.summary.frequency[value]} />)}
          {summary.frequency !== "off" ? (
            <div className="ml-6 flex flex-col gap-1.5">
              <Choice type="radio" name="summary-scope" checked={summary.yearclock_ids === null} onChange={() => setSummary({ yearclock_ids: null })} label={copy.summary.allYearclocks} />
              <Choice type="radio" name="summary-scope" checked={summary.yearclock_ids !== null} onChange={() => setSummary({ yearclock_ids: summary.yearclock_ids ?? clocks.map((clock) => clock.id) })} label={copy.summary.chosenYearclocks} />
              {summary.yearclock_ids !== null ? (
                <ul className="m-0 ml-6 flex list-none flex-col gap-1 p-0" aria-label={copy.summary.chosenYearclocks}>
                  {clocks.map((clock) => <li key={clock.id}><Choice type="checkbox" checked={summary.yearclock_ids!.includes(clock.id)} onChange={(event) => setSummary({ yearclock_ids: event.target.checked ? [...summary.yearclock_ids!, clock.id] : summary.yearclock_ids!.filter((id) => id !== clock.id) })} label={clock.name} /></li>)}
                </ul>
              ) : null}
            </div>
          ) : null}
        </fieldset>
      ) : null}
      <div><Button variant="primary" disabled={!settings} onClick={() => void save()}>{copy.settings.save}</Button></div>
    </Section>
  );
}
