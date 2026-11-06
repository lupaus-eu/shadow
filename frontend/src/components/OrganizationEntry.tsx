import { useCallback, useEffect, useId, useState } from "react";
import { ChevronLeft } from "lucide-react";
import { Link, Outlet, useMatch, useNavigate, useParams } from "react-router";

import type { UserAccount } from "../auth-client";
import { messages, workspaceMessages, type Locale } from "../i18n";
import {
  acceptInvitation,
  loadOrganizations,
  loadOrganizationWorkspace,
  recordYearclockVisit,
  restoreOrganization,
  type OrganizationSummary,
  type OrganizationWorkspace,
  type WorkspaceYearclock,
} from "../organization-client";
import { matchesText } from "../text-match";
import { OrganizationActivation } from "./OrganizationActivation";
import { YearclockPlanner, YearclockSettings } from "../yearclock/YearclockPlanner";
import { MyGroups } from "./GroupsPanel";
import { SubscriptionNotice } from "../admin/SubscriptionNotice";
import { Section } from "../admin/Section";
import { Alert, Button, EmptyState, TextInput } from "../ui";
import { NotificationBell } from "../notifications/NotificationBell";
import { AppShell, useAccount, usePageTitle } from "../shell/AppShell";
import { OrganizationSidebar } from "../shell/OrganizationSidebar";
import { SignedOutLayout } from "../shell/SignedOutLayout";
import { organizationHref, yearclockHref } from "../shell/nav";
import { useOrganization, type OrganizationOutlet } from "../shell/organization-outlet";

/** `/`: the Organization list; a single active Organization opens directly, none starts onboarding. */
export function OrganizationMembershipEntry({
  userAccount,
  locale,
}: {
  userAccount: UserAccount;
  locale: Locale;
}) {
  const labels = messages(locale);
  const navigate = useNavigate();
  const [organizations, setOrganizations] = useState<
    OrganizationSummary[] | null
  >(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    void loadOrganizations(controller.signal)
      .then((result) => {
        if (result.length === 1 && (result[0].status ?? "active") === "active") {
          navigate(organizationHref(result[0].id), { replace: true });
          return;
        }
        setOrganizations(result);
      })
      .catch((error) => {
        if (!(error instanceof DOMException && error.name === "AbortError")) {
          setFailed(true);
        }
      });
    return () => controller.abort();
  }, [navigate]);

  if (organizations !== null && organizations.length === 0) {
    return <SignedOutLayout wide><OrganizationActivation userAccount={userAccount} locale={locale} /></SignedOutLayout>;
  }
  return (
    <AppShell>
      <PageTitle title={labels.title} />
      {failed ? <Alert tone="danger" role="alert">{labels.organizationContextUnavailable}</Alert> : null}
      {!failed && organizations === null ? <p role="status" className="text-ink-muted">{labels.organizationLoading}</p> : null}
      {organizations !== null ? (
        <Section title={labels.chooseOrganization} description={labels.chooseOrganizationDescription} className="organization-selector">
          <ul className="m-0 grid list-none gap-3 p-0 sm:grid-cols-2">
            {organizations.map((organization) => (
              <li key={organization.id} className="relative flex flex-col gap-1 rounded-[10px] border border-line bg-surface p-4 hover:border-accent focus-within:border-accent">
                {organization.status === "pending_deletion" ? (
                  <PendingDeletion organization={organization} locale={locale} />
                ) : (
                  <Link className="flex flex-col gap-0.5 text-ink no-underline after:absolute after:inset-0 after:content-['']" to={organizationHref(organization.id)}>
                    <strong className="text-sm font-semibold">{organization.name}</strong>
                    <span className="text-xs text-ink-muted">{labels.organizationRole[organization.role]}</span>
                  </Link>
                )}
              </li>
            ))}
          </ul>
          <div><Link className="inline-flex h-[34px] items-center rounded-[var(--radius-control)] border border-line bg-surface px-3 text-[13px] font-medium text-ink no-underline hover:bg-surface-subtle pointer-coarse:min-h-11" to="/organization-signups/new">{labels.createAnotherOrganization}</Link></div>
        </Section>
      ) : null}
    </AppShell>
  );
}

function PageTitle({ title }: { title: string }) {
  usePageTitle(title);
  return null;
}

/** `/organizations/:organizationId/*`: loads the Organization once and renders its pages inside the shell. */
export function OrganizationLayout() {
  const { locale } = useAccount();
  const { organizationId = "" } = useParams();
  const labels = messages(locale);
  const [workspace, setWorkspace] = useState<OrganizationWorkspace | null>(null);
  const [failed, setFailed] = useState(false);
  const [revision, setRevision] = useState(0);
  const reload = useCallback(() => setRevision((value) => value + 1), []);
  const yearclockPage = useMatch("/organizations/:organizationId/yearclocks/:yearclockId/*") !== null;

  useEffect(() => {
    const controller = new AbortController();
    setFailed(false);
    void loadOrganizationWorkspace(organizationId, controller.signal)
      .then(setWorkspace)
      .catch((error) => {
        if (!(error instanceof DOMException && error.name === "AbortError")) {
          setFailed(true);
        }
      });
    return () => controller.abort();
  }, [organizationId, revision]);

  const current = workspace?.organization.id === organizationId ? workspace : null;
  return (
    <AppShell wide={yearclockPage} actions={current ? <NotificationBell organizationId={current.organization.id} locale={locale} /> : null} sidebar={current ? <OrganizationSidebar workspace={current} locale={locale} /> : null}>
      {failed ? <><PageTitle title={labels.title} /><Alert tone="danger" role="alert">{labels.organizationNotFound}</Alert></> : null}
      {!failed && !current ? <p role="status" className="text-ink-muted">{labels.organizationLoading}</p> : null}
      {!failed && current ? <Outlet context={{ workspace: current, locale, revision, reload } satisfies OrganizationOutlet} /> : null}
    </AppShell>
  );
}

/** `/organizations/:organizationId`: the overview: Yearclocks, recently opened, and My groups. */
export function OrganizationHome() {
  const { workspace, locale } = useOrganization();
  const organizationId = workspace.organization.id;
  usePageTitle(workspace.organization.name);
  return (
    <div className="grid grid-cols-[minmax(0,1fr)] gap-5">
      <SubscriptionNotice organizationId={organizationId} subscription={workspace.subscription} isOwner={workspace.membership.role === "owner"} locale={locale} />
      <YearclockOverview workspace={workspace} locale={locale} />
      <MyGroups organizationId={organizationId} locale={locale} />
    </div>
  );
}

/** Unknown addresses inside an Organization. */
export function OrganizationNotFound() {
  const { locale } = useOrganization();
  const labels = messages(locale);
  usePageTitle(labels.title);
  return <Alert tone="danger" role="alert">{labels.shell.notFound}</Alert>;
}

function YearclockOverview({ workspace, locale }: { workspace: OrganizationWorkspace; locale: Locale }) {
  const text = workspaceMessages(locale).overview;
  const [query, setQuery] = useState("");
  const searchId = useId();
  const byId = new Map(workspace.yearclocks.map((yearclock) => [yearclock.id, yearclock]));
  const recent = (workspace.recent_yearclock_ids ?? []).map((id) => byId.get(id)).filter((item): item is WorkspaceYearclock => item !== undefined);
  const matching = workspace.yearclocks.filter((yearclock) => matchesText(query, yearclock.name));
  const card = (yearclock: WorkspaceYearclock) => (
    <li key={yearclock.id} className="relative flex flex-col gap-1 rounded-[10px] border border-line bg-surface p-4 hover:border-accent focus-within:border-accent">
      <Link className="text-sm font-semibold text-ink no-underline after:absolute after:inset-0 after:content-['']" to={yearclockHref(workspace.organization.id, yearclock.id)}>{yearclock.name}</Link>
      <span className="text-xs text-ink-muted">{text.lanes(yearclock.lanes.map((lane) => lane.name).join(", "))}</span>
    </li>
  );
  const GRID = "m-0 grid list-none gap-3 p-0 sm:grid-cols-2 xl:grid-cols-3";
  if (workspace.yearclocks.length === 0) return <Section title={text.title} className="yearclock-overview"><EmptyState title={text.empty} /></Section>;
  return (
    <Section title={text.title} className="yearclock-overview" actions={<div className="flex flex-col gap-1.5"><label htmlFor={searchId} className="sr-only">{text.search}</label><TextInput id={searchId} type="search" className="w-64" placeholder={text.search} value={query} onChange={(event) => setQuery(event.target.value)} /></div>}>
      {recent.length > 0 && !query ? (
        <nav aria-labelledby="yearclock-recent-title" className="flex flex-col gap-2">
          <h3 id="yearclock-recent-title" className="m-0 text-xs font-semibold uppercase tracking-wide text-ink-muted">{text.recent}</h3>
          <ol className={GRID}>{recent.map(card)}</ol>
        </nav>
      ) : null}
      <div className="flex flex-col gap-2">
        <h3 id="yearclock-all-title" className="m-0 text-xs font-semibold uppercase tracking-wide text-ink-muted">{text.all}</h3>
        {matching.length === 0 ? <p role="status" className="m-0 text-[13px] text-ink-muted">{text.noMatches}</p> : <ul className={GRID} aria-labelledby="yearclock-all-title">{matching.map(card)}</ul>}
      </div>
    </Section>
  );
}

/** `/organizations/:organizationId/yearclocks/:yearclockId`: the planner; opening it records the visit. */
export function YearclockPage() {
  const { workspace, locale, reload } = useOrganization();
  const { yearclockId } = useParams();
  const text = workspaceMessages(locale).overview;
  const yearclock = workspace.yearclocks.find((item) => item.id === yearclockId);
  usePageTitle(yearclock?.name ?? workspace.organization.name);
  // The Previous Visit sets which changes by others are marked as new; undefined until the visit is recorded.
  const [previousVisit, setPreviousVisit] = useState<string | null | undefined>(undefined);
  useEffect(() => {
    if (!yearclock) return;
    setPreviousVisit(undefined);
    void recordYearclockVisit(workspace.organization.id, yearclock.id).then((visit) => setPreviousVisit(visit.previous_visited_at), () => setPreviousVisit(null));
  }, [workspace.organization.id, yearclock?.id]);
  return (
    <div className="grid grid-cols-[minmax(0,1fr)] gap-5">
      <Link className="inline-flex w-fit items-center gap-1 text-[13px] font-medium text-ink-muted no-underline hover:text-ink pointer-coarse:min-h-11 print:hidden" to={organizationHref(workspace.organization.id)}><ChevronLeft size={14} aria-hidden="true" />{text.back(workspace.organization.name)}</Link>
      {yearclock ? (
        <>
          <SubscriptionNotice organizationId={workspace.organization.id} subscription={workspace.subscription} isOwner={workspace.membership.role === "owner"} locale={locale} />
          <YearclockPlanner key={yearclock.id} organizationId={workspace.organization.id} yearclock={yearclock} canEdit={workspace.subscription.writable && (workspace.membership.role !== "member" || yearclock.access_role === "editor")} locale={locale} timeZone={workspace.organization.time_zone} onStructureChanged={reload} sources={workspace.yearclocks} previousVisit={previousVisit} />
        </>
      ) : (
        <p role="alert">{text.notFound}</p>
      )}
    </div>
  );
}

function PendingDeletion({ organization, locale }: { organization: OrganizationSummary; locale: Locale }) {
  const text = workspaceMessages(locale).deletion;
  const [state, setState] = useState<"pending" | "restored" | "failed">("pending");
  const formatDate = (value: string) => new Intl.DateTimeFormat(locale === "fi" ? "fi-FI" : "en-GB", { dateStyle: "long" }).format(new Date(value));
  async function restore() {
    try { await restoreOrganization(organization.id); setState("restored"); } catch { setState("failed"); }
  }
  if (state === "restored") return <p role="status" className="m-0 text-[13px]"><Link to={organizationHref(organization.id)}>{organization.name}</Link> — {text.restored}</p>;
  return <div className="pending-deletion flex flex-wrap items-center gap-2">
    <strong className="text-sm font-semibold">{organization.name}</strong>
    <span className="text-xs text-ink-muted">{organization.purge_after ? text.pending(formatDate(organization.purge_after)) : null}</span>
    <Button size="sm" aria-label={`${text.restore}: ${organization.name}`} onClick={() => void restore()}>{text.restore}</Button>
    {state === "failed" ? <Alert tone="danger" role="alert" className="w-full">{text.restoreFailed}</Alert> : null}
  </div>;
}

/** `/invitations/:token`: accept an invitation with the signed-in account. */
export function InvitationAcceptance({ locale }: { locale: Locale }) {
  const { token = "" } = useParams();
  const copy = workspaceMessages(locale);
  const [state, setState] = useState<"ready" | "accepted" | "failed">("ready");
  async function accept() { try { await acceptInvitation(token); setState("accepted"); } catch { setState("failed"); } }
  const heading = "m-0 text-xl font-semibold tracking-tight";
  if (state === "accepted") return <section className="flex flex-col gap-3"><h2 className={heading}>{copy.invitationAccepted}</h2><p className="m-0 text-[13px] text-ink-muted">{copy.invitationAccessGranted}</p><Link className="inline-flex h-10 w-fit items-center rounded-[var(--radius-control)] bg-accent px-4 text-sm font-semibold text-white no-underline hover:bg-accent-hover" to="/">{copy.openYearclock}</Link></section>;
  return <section className="flex flex-col gap-3"><h2 className={heading}>{copy.organizationInvitation}</h2><p className="m-0 text-[13px] text-ink-muted">{copy.invitationAcceptanceDescription}</p>{state === "failed" ? <Alert tone="danger" role="alert">{copy.invitationAcceptanceFailed}</Alert> : null}<div><Button variant="primary" onClick={() => void accept()}>{copy.acceptInvitation}</Button></div></section>;
}

/** `/organizations/:organizationId/yearclocks/:yearclockId/settings`: Yearclock structure for Editors. */
export function YearclockSettingsPage() {
  const { workspace, locale, reload } = useOrganization();
  const { yearclockId } = useParams();
  const text = workspaceMessages(locale);
  const yearclock = workspace.yearclocks.find((item) => item.id === yearclockId);
  const canEdit = Boolean(yearclock) && workspace.subscription.writable && (workspace.membership.role !== "member" || yearclock?.access_role === "editor");
  usePageTitle(yearclock ? `${text.planner.tabs.settings}: ${yearclock.name}` : workspace.organization.name);
  return (
    <div className="organization-workspace">
      {yearclock ? <Link className="inline-flex w-fit items-center gap-1 text-[13px] font-medium text-ink-muted no-underline hover:text-ink pointer-coarse:min-h-11 print:hidden" to={yearclockHref(workspace.organization.id, yearclock.id)}><ChevronLeft size={14} aria-hidden="true" />{text.overview.back(yearclock.name)}</Link> : null}
      {yearclock && canEdit ? (
        <YearclockSettings organizationId={workspace.organization.id} yearclock={yearclock} locale={locale} timeZone={workspace.organization.time_zone} sources={workspace.yearclocks} onStructureChanged={reload} />
      ) : (
        <Alert tone="danger" role="alert">{text.overview.notFound}</Alert>
      )}
    </div>
  );
}
