import { Activity, Building2, LifeBuoy, LogOut, RotateCcw } from "lucide-react";
import { Fragment, useEffect, useState, type ReactNode } from "react";
import { NavLink, Route, Routes } from "react-router";

import { AuthenticationRequiredError } from "../auth-client";
import { messages, platformMessages, storedLocale, type Locale, type PlatformMessages } from "../i18n";
import { ROW, ROWS, Section } from "../admin/Section";
import { ShellFrame, usePageTitle } from "../shell/AppShell";
import { SignedOutLayout } from "../shell/SignedOutLayout";
import { Alert, Badge, Button, EmptyState, OverlayProvider, Select, Table, TextInput } from "../ui";

const FIELD = "flex flex-col gap-1.5 text-[13px] font-medium text-ink";
import {
  CustomerAccountError,
  loadFailedJobs,
  loadPlatformHealth,
  loadPlatformOrganizations,
  setMcpBlock,
  loadPlatformSession,
  loadSupportEvents,
  loadSupportGrants,
  loadSupportYearclocks,
  requestSupportAccess,
  platformLoginUrl,
  platformLogoutUrl,
  replayJob,
  type PlatformHealth,
  type PlatformJob,
  type PlatformOrganization,
  type PlatformSession,
  type SupportEvent,
  type SupportGrant,
  type SupportYearclock,
} from "./platform-client";

type ConsoleState =
  | { state: "loading" }
  | { state: "anonymous" }
  | { state: "customer" }
  | { state: "error" }
  | { state: "ready"; session: PlatformSession };

export function PlatformConsole() {
  const [consoleState, setConsoleState] = useState<ConsoleState>({ state: "loading" });
  const locale: Locale = consoleState.state === "ready" ? consoleState.session.locale : storedLocale();
  const text = platformMessages(locale);

  useEffect(() => {
    loadPlatformSession()
      .then((session) => setConsoleState({ state: "ready", session }))
      .catch((error) => {
        if (error instanceof AuthenticationRequiredError) setConsoleState({ state: "anonymous" });
        else if (error instanceof CustomerAccountError) setConsoleState({ state: "customer" });
        else setConsoleState({ state: "error" });
      });
  }, []);

  if (consoleState.state === "loading") return <SignedOutLayout><p role="status" className="text-[13px] text-ink-muted">{text.loading}</p></SignedOutLayout>;
  if (consoleState.state === "error") return <SignedOutLayout><Alert tone="danger" role="alert">{text.failed}</Alert></SignedOutLayout>;
  if (consoleState.state === "anonymous" || consoleState.state === "customer") {
    return (
      <SignedOutLayout labelledBy="platform-signin-title">
        <Badge tone="warning" className="w-fit">{text.badge}</Badge>
        <h1 id="platform-signin-title" className="text-xl font-semibold tracking-tight">{text.signInTitle}</h1>
        {consoleState.state === "customer" ? <Alert tone="warning" role="alert">{text.customerAccount}</Alert> : <p className="text-[13px] text-ink-muted">{text.signInDescription}</p>}
        {consoleState.state === "customer"
          ? <a className="inline-flex h-10 items-center justify-center rounded-[var(--radius-control)] border border-line bg-surface px-4 text-sm font-semibold text-ink no-underline hover:bg-surface-subtle" href="/">{text.openCustomerApp}</a>
          : <a className="inline-flex h-10 items-center justify-center rounded-[var(--radius-control)] bg-accent px-4 text-sm font-semibold text-white no-underline hover:bg-accent-hover" href={platformLoginUrl}>{text.signIn}</a>}
      </SignedOutLayout>
    );
  }
  const { session } = consoleState;
  const admin = session.roles.includes("platform_admin");
  const agent = session.roles.includes("support_agent");
  const LINK = "flex min-h-8 items-center gap-2 rounded-[6px] px-2 py-1.5 text-[13px] text-sidebar-ink no-underline hover:bg-sidebar-raised hover:text-white aria-[current=page]:bg-sidebar-raised aria-[current=page]:font-semibold aria-[current=page]:text-white pointer-coarse:min-h-11";
  const pages = [
    { to: "/platform", label: text.health, icon: <Activity size={15} aria-hidden="true" />, end: true },
    ...(admin ? [{ to: "/platform/organizations", label: text.organizations, icon: <Building2 size={15} aria-hidden="true" />, end: false }] : []),
    { to: "/platform/jobs", label: text.failedJobs, icon: <RotateCcw size={15} aria-hidden="true" />, end: false },
    ...(agent ? [{ to: "/platform/support", label: text.support.title, icon: <LifeBuoy size={15} aria-hidden="true" />, end: false }] : []),
  ];
  const sidebar = (
    <nav aria-label={messages(locale).shell.navigation} className="flex flex-col gap-0.5">
      <ul className="m-0 flex list-none flex-col gap-0.5 p-0">
        {pages.map((item) => <li key={item.to}><NavLink end={item.end} className={LINK} to={item.to}>{item.icon}{item.label}</NavLink></li>)}
      </ul>
    </nav>
  );
  const footer = <p className="m-0 text-[11px] text-sidebar-muted">{text.signedIn} {session.display_name} · {session.roles.map((role) => text.roles[role]).join(", ")}</p>;
  const account = <form action={platformLogoutUrl} method="post"><Button size="sm" type="submit" icon={<LogOut size={14} />}>{text.signOut}</Button></form>;
  return (
    <OverlayProvider labels={messages(locale).overlay}>
      <ShellFrame locale={locale} sidebar={sidebar} footer={footer} account={account} badge={<Badge tone="warning">{text.badge}</Badge>}>
        <Routes>
          <Route index element={<Page title={text.title}><Health text={text} /></Page>} />
          <Route path="organizations" element={admin ? <Page title={text.organizations}><Organizations text={text} locale={locale} /></Page> : <NotFound text={text} />} />
          <Route path="jobs" element={<Page title={text.failedJobs}><FailedJobs text={text} locale={locale} canReplay={admin} /></Page>} />
          <Route path="support" element={agent ? <Page title={text.support.title}><SupportAccessConsole text={text} locale={locale} /></Page> : <NotFound text={text} />} />
          <Route path="*" element={<NotFound text={text} />} />
        </Routes>
      </ShellFrame>
    </OverlayProvider>
  );
}

function Page({ title, children }: { title: string; children: ReactNode }) {
  usePageTitle(title);
  return <div className="flex flex-col gap-5">{children}</div>;
}

function NotFound({ text }: { text: PlatformMessages }) {
  usePageTitle(text.title);
  return <Alert tone="danger" role="alert">{text.notFound}</Alert>;
}

function useLoad<T>(load: () => Promise<T>) {
  const [value, setValue] = useState<T | null>(null);
  const [failed, setFailed] = useState(false);
  const refresh = () => { setFailed(false); load().then(setValue).catch(() => setFailed(true)); };
  useEffect(refresh, []);
  return { value, failed, refresh };
}

function Health({ text }: { text: PlatformMessages }) {
  const { value, failed } = useLoad<PlatformHealth>(loadPlatformHealth);
  const counts = (queue: Record<string, number>) => Object.entries(queue).filter(([, count]) => count > 0).map(([status, count]) => `${text.queue[status as keyof PlatformMessages["queue"]] ?? status} ${count}`).join(", ") || "—";
  const rows: Array<[string, string]> = value ? [
    [text.database, value.database],
    [text.email, counts(value.email)],
    ...Object.entries(value.jobs).map(([type, queue]) => [`${text.jobs}: ${type}`, counts(queue)] as [string, string]),
    [text.webhooks, Object.entries(value.webhooks).map(([outcome, count]) => `${outcome} ${count}`).join(", ") || "—"],
    [text.organizationsByStatus, Object.entries(value.organizations).map(([status, count]) => `${status} ${count}`).join(", ") || "—"],
  ] : [];
  return (
    <Section title={text.health}>
      {failed ? <Alert tone="danger" role="alert">{text.failed}</Alert> : null}
      {value ? (
        <dl className="m-0 grid gap-x-6 gap-y-2 sm:grid-cols-[220px_1fr]">
          {rows.map(([label, detail]) => <Fragment key={label}><dt className="text-[13px] text-ink-muted">{label}</dt><dd className="m-0 text-[13px] font-medium">{detail}</dd></Fragment>)}
        </dl>
      ) : null}
    </Section>
  );
}

function Organizations({ text, locale }: { text: PlatformMessages; locale: Locale }) {
  const { value, failed, refresh } = useLoad<PlatformOrganization[]>(loadPlatformOrganizations);
  const [blockFailed, setBlockFailed] = useState(false);
  async function block(organization: PlatformOrganization) {
    setBlockFailed(false);
    try { await setMcpBlock(organization.id, !organization.mcp_platform_blocked); refresh(); } catch { setBlockFailed(true); }
  }
  const format = (value: string | null) => (value ? new Intl.DateTimeFormat(locale === "fi" ? "fi-FI" : "en-GB", { dateStyle: "medium" }).format(new Date(value)) : "—");
  return (
    <Section title={text.organizations}>
      {failed || blockFailed ? <Alert tone="danger" role="alert">{text.failed}</Alert> : null}
      <Table caption={text.organizations}>
        <thead><tr><th scope="col">{text.name}</th><th scope="col">{text.status}</th><th scope="col">{text.subscription}</th><th scope="col" className="text-right">{text.seats}</th><th scope="col" className="text-right">{text.members}</th><th scope="col" className="text-right">{text.yearclocks}</th><th scope="col">{text.deletion}</th><th scope="col">{text.mcp}</th></tr></thead>
        <tbody>{(value ?? []).map((organization) => (
          <tr key={organization.id}>
            <th scope="row" className="text-left font-semibold">{organization.name}</th>
            <td><Badge tone={organization.status === "active" ? "success" : "neutral"}>{organization.status}</Badge></td>
            <td>{organization.subscription.state}{organization.subscription.cancel_at_period_end ? ` · ${text.cancelScheduled}` : ""}</td>
            <td className="text-right tabular-nums">{organization.purchased_seats}</td>
            <td className="text-right tabular-nums">{organization.members}</td>
            <td className="text-right tabular-nums">{organization.yearclocks}</td>
            <td>{format(organization.deletion_requested_at)}</td>
            <td>
              <span className="flex flex-wrap items-center gap-2">
                <Badge tone={organization.mcp_platform_blocked ? "danger" : organization.mcp_enabled ? "success" : "neutral"}>{organization.mcp_platform_blocked ? text.mcpBlocked : organization.mcp_enabled ? text.mcpAllowed : text.mcpOff}</Badge>
                <Button size="sm" variant={organization.mcp_platform_blocked ? "primary" : "ghost-danger"} onClick={() => void block(organization)}>{organization.mcp_platform_blocked ? text.unblockMcp : text.blockMcp}</Button>
              </span>
            </td>
          </tr>
        ))}</tbody>
      </Table>
    </Section>
  );
}

function FailedJobs({ text, locale, canReplay }: { text: PlatformMessages; locale: Locale; canReplay: boolean }) {
  const { value, failed, refresh } = useLoad<PlatformJob[]>(loadFailedJobs);
  const [notice, setNotice] = useState<string | null>(null);
  const format = (value: string) => new Intl.DateTimeFormat(locale === "fi" ? "fi-FI" : "en-GB", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
  async function replay(job: PlatformJob) {
    setNotice(null);
    try { await replayJob(job); setNotice(text.replayed); refresh(); } catch { setNotice(text.failed); }
  }
  return (
    <Section title={text.failedJobs}>
      {failed ? <Alert tone="danger" role="alert">{text.failed}</Alert> : null}
      {notice ? <Alert tone={notice === text.failed ? "danger" : "success"} role="status">{notice}</Alert> : null}
      {value && value.length === 0 ? <EmptyState title={text.noFailedJobs} /> : null}
      {value && value.length ? (
        <ul className={ROWS}>{value.map((job) => (
          <li key={job.id} className={ROW}>
            <div className="flex min-w-0 flex-1 flex-col gap-0.5">
              <span><strong className="font-semibold">{job.type}</strong> <span className="text-[13px] text-ink-muted">· {format(job.created_at)} · {text.attempts} {job.attempts}</span></span>
              {job.last_error ? <code className="text-xs break-all text-danger">{`${text.error}: ${job.last_error}`}</code> : null}
            </div>
            {canReplay ? <Button size="sm" aria-label={`${text.replay}: ${job.type}`} onClick={() => void replay(job)}>{text.replay}</Button> : null}
          </li>
        ))}</ul>
      ) : null}
    </Section>
  );
}

function SupportAccessConsole({ text, locale }: { text: PlatformMessages; locale: Locale }) {
  const copy = text.support;
  const { value, failed, refresh } = useLoad<SupportGrant[]>(loadSupportGrants);
  const [form, setForm] = useState({ organization_id: "", case_reference: "", scope: "read" as "read" | "write", hours: 1 });
  const [notice, setNotice] = useState<string | null>(null);
  const [open, setOpen] = useState<SupportGrant | null>(null);
  const format = (value: string) => new Intl.DateTimeFormat(locale === "fi" ? "fi-FI" : "en-GB", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
  async function submit() {
    setNotice(null);
    try { await requestSupportAccess(form); setNotice(copy.requested); setForm({ ...form, case_reference: "" }); refresh(); } catch { setNotice(text.failed); }
  }
  return (
    <Section title={copy.title}>
      <form className="support-request flex flex-col gap-3 rounded-[10px] border border-line p-4" onSubmit={(event) => { event.preventDefault(); void submit(); }}>
        <h3 className="m-0 text-[13px] font-semibold">{copy.request}</h3>
        <div className="grid gap-3 sm:grid-cols-2">
          <label className={FIELD}>{copy.organizationId}<TextInput required value={form.organization_id} onChange={(event) => setForm({ ...form, organization_id: event.target.value.trim() })} /></label>
          <label className={FIELD}>{copy.case}<TextInput required maxLength={200} value={form.case_reference} onChange={(event) => setForm({ ...form, case_reference: event.target.value })} /></label>
          <label className={FIELD}>{copy.scope}<Select value={form.scope} onChange={(event) => setForm({ ...form, scope: event.target.value as "read" | "write" })}><option value="read">{copy.read}</option><option value="write">{copy.write}</option></Select></label>
          <label className={FIELD}>{copy.hours}<TextInput type="number" min={1} max={24} value={form.hours} onChange={(event) => setForm({ ...form, hours: Math.min(24, Math.max(1, Number(event.target.value) || 1)) })} /></label>
        </div>
        <div><Button type="submit" variant="primary">{copy.submit}</Button></div>
      </form>
      {notice ? <Alert tone={notice === text.failed ? "danger" : "success"} role="status">{notice}</Alert> : null}
      {failed ? <Alert tone="danger" role="alert">{text.failed}</Alert> : null}
      <h3 className="m-0 text-[13px] font-semibold">{copy.mine}</h3>
      {value && value.length === 0 ? <p className="m-0 text-[13px] text-ink-muted">{copy.empty}</p> : null}
      {value && value.length ? (
        <ul className={ROWS}>{value.map((grant) => (
          <li key={grant.id} className={ROW}>
            <span className="min-w-0 flex-1 text-[13px]"><strong className="font-semibold">{grant.case_reference}</strong> · <code className="text-xs">{grant.organization_id}</code> · {grant.scope === "write" ? copy.write : copy.read} · {copy.status[grant.status]}
            {grant.status === "approved" && grant.expires_at ? ` ${copy.until(format(grant.expires_at))}` : ""}</span>
            {grant.status === "approved" ? <Button size="sm" onClick={() => setOpen(grant)}>{copy.open}</Button> : null}
          </li>
        ))}</ul>
      ) : null}
      {open ? <SupportContent grant={open} text={text} onClose={() => { setOpen(null); refresh(); }} /> : null}
    </Section>
  );
}

function SupportContent({ grant, text, onClose }: { grant: SupportGrant; text: PlatformMessages; onClose: () => void }) {
  const copy = text.support;
  const [clocks, setClocks] = useState<SupportYearclock[] | null>(null);
  const [events, setEvents] = useState<Record<string, SupportEvent[]>>({});
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    loadSupportYearclocks(grant.id)
      .then(async (items) => {
        setClocks(items);
        const loaded = await Promise.all(items.map(async (clock) => [clock.id, await loadSupportEvents(grant.id, clock.id)] as const));
        setEvents(Object.fromEntries(loaded));
      })
      .catch(() => setFailed(true));
  }, [grant.id]);
  return (
    <section className="support-content flex flex-col gap-3 rounded-[10px] border border-warning-line bg-warning-soft/40 p-4" aria-labelledby="support-content-title">
      <h3 id="support-content-title" className="m-0 text-sm font-semibold">{grant.case_reference}</h3>
      <p className="m-0 text-xs text-ink-muted">{copy.audited}</p>
      {failed ? <Alert tone="danger" role="alert">{text.failed}</Alert> : null}
      {(clocks ?? []).map((clock) => (
        <article key={clock.id} className="flex flex-col gap-1 rounded-[10px] border border-line bg-surface p-3">
          <h4 className="m-0 text-[13px] font-semibold">{clock.name}</h4>
          <p className="m-0 text-xs text-ink-muted">{copy.lanes}: {clock.lanes.map((lane) => lane.name).join(", ")}</p>
          <p className="m-0 text-xs font-semibold">{copy.events}</p>
          {(events[clock.id] ?? []).length === 0 ? <p className="m-0 text-[13px] text-ink-muted">{copy.noEvents}</p> : null}
          <ul className="m-0 flex list-none flex-col gap-0.5 p-0 text-[13px]">{(events[clock.id] ?? []).map((event) => <li key={event.id}>{event.starts_on}{event.ends_on ? ` – ${event.ends_on}` : ""} · {event.title}</li>)}</ul>
        </article>
      ))}
      <div><Button size="sm" onClick={onClose}>{copy.close}</Button></div>
    </section>
  );
}
