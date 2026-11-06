import { useCallback, useEffect, useId, useState } from "react";

import { messages, workspaceMessages, type Locale, type PlannerMessages } from "../i18n";
import {
  ConflictError,
  LimitReachedError,
  createCategory,
  createEvent,
  createLane,
  createSeries,
  deleteLane,
  LaneHasEventsError,
  moveLaneEvents,
  deleteCategory,
  bulkEdit,
  loadEventHistory,
  loadChanges,
  previewVersionRestore,
  restoreVersion,
  type RestorePreview,
  linkLane,
  copyLane,
  planAgain,
  type PlanAgainInput,
  type PlanAgainResult,
  deleteEvent,
  type BulkAction,
  editOccurrence,
  endSeries,
  loadSeries,
  splitSeries,
  loadCategories,
  loadLabels,
  updateLayout,
  searchYearclock,
  type SearchResult,
  createLabel,
  LABEL_COLORS,
  type Label,
  loadDeletedEvents,
  loadEvents,
  renameLane,
  reorderCategories,
  reorderLanes,
  restoreEvent,
  restoreOccurrence,
  skipOccurrence,
  updateCategory,
  updateEvent,
  type EventInput,
  type SeriesInput,
  type WorkspaceYearclock,
  type YearclockCategory,
  type Lane,
  type YearclockEvent,
} from "../organization-client";
import { matchesText, normalizeText } from "../text-match";
import { NO_CATEGORY, applyFilters, categoryGroups, facetCounts, isFiltering, loadFilters, pruneFilters, saveFilters, toggle, type Dimension, type FilterState } from "./filters";
import { EventText } from "./EventText";
import { DescriptionEditor } from "./DescriptionEditor";
import { LinksEditor } from "./LinksEditor";
import { RichText } from "./RichText";
import { cleanLinks, linkProblems, LOCATION_MAX, type EventLink } from "./event-links";
import { EventSummary, YearclockView, dateLabel, formatDay } from "./YearclockView";
import { DisplaySwitch } from "./displays/DisplaySwitch";
import { AgendaDisplay } from "./displays/AgendaDisplay";
import { ListDisplay } from "./displays/ListDisplay";
import { TimelineDisplay } from "./displays/TimelineDisplay";
import { ExportDialog } from "../exchange/ExportDialog";
import { ExportMenu } from "../exchange/ExportMenu";
import { ImportDialog } from "../exchange/ImportDialog";
import { RateLimitedError, exportYearclock } from "../exchange/client";
import { circleImage, saveBlob } from "../exchange/image";
import { imageFileName } from "../exchange/png";
import { PrintAppendix, PrintHeader } from "../exchange/PrintSheet";
import { loadDisplay, saveDisplay, type Display } from "./displays/display-mode";
import { WINDOW_LENGTHS, addMonths, currentPeriod, planningWindow, type WindowLength } from "./geometry";
import { bulkBlocker, selectAllShown, shiftYear } from "./planning";
import { startChangePoll } from "./change-poll";
import { ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight, History, Plus, Search, Settings } from "lucide-react";
import { Link } from "react-router";
import { Alert, Badge, Button, Card, Choice, Drawer, IconButton, SegmentedControl, Select, Tabs, TextArea, TextInput, useConfirm, useToast } from "../ui";
import { changeMarks, describeActor, describeChanges, describeEntry, type ChangesPage, type HistoryItem } from "./history";

type PanelTab = "events" | "details" | "filters";
type Frequency = "" | SeriesInput["frequency"];
type EndRule = "never" | "until" | "count";

type EventDraft = {
  mode: "create" | "edit" | "occurrence" | "future";
  event: YearclockEvent | null;
  title: string;
  laneId: string;
  categoryId: string;
  labelIds: string[];
  startsOn: string;
  endsOn: string;
  startsAt: string;
  endsAt: string;
  description: string;
  descriptionFormat: "plain" | "markdown";
  location: string;
  links: EventLink[];
  frequency: Frequency;
  interval: string;
  lastDay: boolean;
  endRule: EndRule;
  until: string;
  count: string;
  /** Where a new Event came from, recorded in its first Event Revision. */
  origin?: "duplicate" | "plan_again";
};

const FIELD = "flex flex-col gap-1.5 text-[13px] font-medium text-ink";
const TITLE_LIMIT = 200;
const DESCRIPTION_LIMIT = 10_000;

export function organizationToday(timeZone: string, now = new Date()): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone, year: "numeric", month: "2-digit", day: "2-digit" }).format(now);
}

function emptyDraft(laneId: string, startsOn = ""): EventDraft {
  return { mode: "create", event: null, title: "", laneId, categoryId: "", labelIds: [], startsOn, endsOn: "", startsAt: "", endsAt: "", description: "", descriptionFormat: "markdown", location: "", links: [], frequency: "", interval: "1", lastDay: false, endRule: "never", until: "", count: "" };
}

function draftFrom(event: YearclockEvent, mode: "edit" | "occurrence" | "future"): EventDraft {
  return { ...emptyDraft(event.lane_id), mode, event, title: event.title, categoryId: event.category_id ?? "", labelIds: event.label_ids ?? [], startsOn: event.starts_on, endsOn: event.ends_on ?? "", startsAt: event.starts_at ?? "", endsAt: event.ends_at ?? "", description: event.description ?? "", descriptionFormat: event.description_format ?? "plain", location: event.location ?? "", links: (event.links ?? []).map((link) => ({ ...link })) };
}

function linkedLaneName(lane: Lane, copy: PlannerMessages): string {
  if (lane.source?.available) return `${lane.source.lane_name ?? lane.name} (${copy.linked.from(lane.source.yearclock_name ?? "")})`;
  return lane.source?.reason === "deleted" ? copy.linked.noLongerAvailable : copy.linked.notAvailable;
}

function draftCopy(event: YearclockEvent, nextYear: boolean): EventDraft {
  const shift = (value: string) => (nextYear ? shiftYear(value) : value);
  return { ...draftFrom(event, "edit"), mode: "create", event: null, startsOn: shift(event.starts_on), endsOn: event.ends_on ? shift(event.ends_on) : "", origin: nextYear ? "plan_again" : "duplicate" };
}

export function YearclockPlanner({
  organizationId,
  yearclock,
  canEdit,
  locale,
  timeZone,
  onStructureChanged,
  sources = [],
  previousVisit,
}: {
  /** The Previous Visit; undefined while unknown, null on a first visit. */
  previousVisit?: string | null;
  organizationId: string;
  yearclock: WorkspaceYearclock;
  canEdit: boolean;
  locale: Locale;
  timeZone: string;
  onStructureChanged: () => void;
  sources?: WorkspaceYearclock[];
}) {
  const copy: PlannerMessages = workspaceMessages(locale).planner;
  const today = organizationToday(timeZone);
  const [length, setLength] = useState<WindowLength>(() => loadLength(yearclock.id));
  const startMonth = yearclock.start_month ?? 1;
  const [windowStart, setWindowStart] = useState(() => currentPeriod(today, loadLength(yearclock.id), startMonth));
  const plan = planningWindow(windowStart, length);
  const [events, setEvents] = useState<YearclockEvent[]>([]);
  const [deletedEvents, setDeletedEvents] = useState<YearclockEvent[]>([]);
  const [categories, setCategories] = useState<YearclockCategory[]>([]);
  const [labels, setLabels] = useState<Label[]>([]);
  const [filters, setFilters] = useState<FilterState>(() => loadFilters(yearclock.id));
  const [loaded, setLoaded] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [tab, setTab] = useState<PanelTab>("events");
  const [exporting, setExporting] = useState<"xlsx" | "csv" | "ics" | null>(null);
  const [importing, setImporting] = useState(false);
  // The display is a personal choice kept in the browser; every display shares the window, Filters, and selection (ADR-0029).
  const [display, setDisplay] = useState<Display>(() => loadDisplay(yearclock.id));
  const [changesOpen, setChangesOpen] = useState(true);
  const changesId = useId();
  const [draft, setDraft] = useState<EventDraft | null>(null);
  // Success messages go to the toast region (docs/design/ui-foundation.md); errors stay inline as `failed`.
  const toast = useToast();
  const setNotice = useCallback((message: string | null) => { if (message) toast(message); }, [toast]);
  const [failed, setFailed] = useState<string | null>(null);
  const lanes = yearclock.lanes;
  // Linked Lanes are shown with their source's name and are never offered for new content.
  const displayLanes = lanes.map((lane) => (lane.source_lane_id ? { ...lane, name: linkedLaneName(lane, copy), readOnly: true, unavailable: !lane.source?.available } : lane));
  const ownLanes = lanes.filter((lane) => !lane.source_lane_id);
  const [selecting, setSelecting] = useState(false);
  const [chosen, setChosen] = useState<Set<string>>(() => new Set());
  const bulkNoteId = useId();
  const confirm = useConfirm();
  const [changes, setChanges] = useState<ChangesPage | null>(null);
  // Changes by others after this time raise the notice; Refresh moves it to now.
  const [loadedAt, setLoadedAt] = useState(() => new Date().toISOString());
  const [othersChanged, setOthersChanged] = useState(false);
  useEffect(() => {
    if (othersChanged) return;
    const visible = () => globalThis.document?.visibilityState !== "hidden";
    const poll = startChangePoll({ intervalMs: 60_000, isVisible: visible, check: async () => (await loadChanges(organizationId, yearclock.id, loadedAt, 1)).total > 0, onChanges: () => setOthersChanged(true) });
    globalThis.document?.addEventListener("visibilitychange", poll.visibilityChanged);
    return () => { poll.stop(); globalThis.document?.removeEventListener("visibilitychange", poll.visibilityChanged); };
  }, [organizationId, yearclock.id, loadedAt, othersChanged]);
  const [seen, setSeen] = useState(false);
  useEffect(() => {
    if (!previousVisit) { setChanges(null); return; }
    let current = true;
    void loadChanges(organizationId, yearclock.id, previousVisit).then((page) => { if (current) setChanges(page); }, () => undefined);
    return () => { current = false; };
  }, [organizationId, yearclock.id, previousVisit]);

  const refresh = useCallback(async () => {
    try {
      const [loaded, loadedCategories, loadedLabels] = await Promise.all([
        loadEvents(organizationId, yearclock.id, plan.start, canEdit, length),
        loadCategories(organizationId, yearclock.id),
        loadLabels(organizationId).catch(() => [] as Label[]),
      ]);
      setEvents(loaded);
      setCategories(loadedCategories);
      setLabels(loadedLabels);
      setFilters((current) => pruneFilters(current, { lanes: yearclock.lanes.map((lane) => lane.id), categories: loadedCategories.map((category) => category.id), labels: loadedLabels.map((label) => label.id) }));
      setLoaded(true);
      if (canEdit) setDeletedEvents(await loadDeletedEvents(organizationId, yearclock.id));
      return loaded;
    } catch {
      setFailed(copy.loadFailed);
      return [];
    }
  }, [organizationId, yearclock.id, plan.start, length, canEdit, copy.loadFailed]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  async function run(action: () => Promise<unknown>, success?: string) {
    setFailed(null);
    setNotice(null);
    try {
      await action();
      if (success) setNotice(success);
      await refresh();
      return true;
    } catch (error) {
      if (error instanceof LimitReachedError) {
        setFailed(copy.limitReached(error.maximum));
      } else if (error instanceof ConflictError) {
        const latest = await refresh();
        const current = draft?.event ? latest.find((item) => item.id === draft.event!.id) : undefined;
        if (current && draft && draft.mode !== "create") setDraft(draftFrom(current, draft.mode));
        setFailed(copy.conflict);
      } else {
        setFailed(copy.saveFailed);
      }
      return false;
    }
  }

  useEffect(() => {
    setChosen((current) => {
      const present = new Set(events.filter((item) => !item.skipped && !item.deleted_at && bulkBlocker(item) === null).map((item) => item.id));
      const next = new Set([...current].filter((id) => present.has(id)));
      return next.size === current.size ? current : next;
    });
  }, [events]);

  async function runBulk(change: BulkAction, question: string, confirmLabel: string) {
    const targets = events.filter((item) => chosen.has(item.id));
    if (!targets.length || !(await confirm({ title: question, confirmLabel, destructive: change.action === "delete" }))) return;
    setFailed(null);
    setNotice(null);
    try {
      const result = await bulkEdit(organizationId, yearclock.id, targets, change);
      setNotice(copy.bulk.done(result.changed));
      if (change.action === "delete") { setChosen(new Set()); setSelectedId(null); }
      await refresh();
    } catch (error) {
      if (error instanceof LimitReachedError) {
        setFailed(error.limit === "bulk_events" ? copy.bulk.tooMany(error.maximum) : error.limit === "labels_per_event" ? copy.bulk.labelLimit(error.maximum) : copy.limitReached(error.maximum));
      } else if (error instanceof ConflictError) {
        await refresh();
        setFailed(copy.bulk.conflict);
      } else {
        setFailed(copy.saveFailed);
      }
    }
  }

  useEffect(() => { if (loaded) saveFilters(yearclock.id, filters); }, [loaded, yearclock.id, filters]);

  const selected = events.find((item) => item.id === selectedId) ?? null;
  const unfiltered = events.filter((item) => !item.skipped);
  const visible = applyFilters(unfiltered, filters);
  const skipped = events.filter((item) => item.skipped);
  const laneName = (laneId: string) => displayLanes.find((lane) => lane.id === laneId)?.name ?? copy.lane;
  const categoryOf = (categoryId: string | null) => categories.find((category) => category.id === categoryId);
  const ownCategories = categories.filter((category) => category.scope !== "linked");
  const marks = changes && !seen ? changeMarks(changes.items, events) : undefined;
  const labelsOf = (event: YearclockEvent) => (event.label_ids ?? []).map((labelId) => labels.find((label) => label.id === labelId)).filter((label): label is Label => label !== undefined);
  const sameLabels = (left: string[] | undefined, right: string[] | undefined) => new Set(left ?? []).size === new Set(right ?? []).size && (left ?? []).every((item) => (right ?? []).includes(item));

  function shiftWindow(months: number) {
    setWindowStart(addMonths(plan.start, months));
  }

  async function save() {
    if (!draft) return;
    const input: EventInput = {
      title: draft.title.trim(),
      lane_id: draft.laneId,
      category_id: draft.categoryId || null,
      starts_on: draft.startsOn,
      ends_on: draft.endsOn || null,
      starts_at: draft.startsAt || null,
      ends_at: draft.startsAt ? draft.endsAt || null : null,
      description: draft.description || null,
      description_format: draft.descriptionFormat,
      location: draft.location.trim() || null,
      links: cleanLinks(draft.links),
      label_ids: draft.labelIds,
    };
    const labelChange = draft.event && !sameLabels(draft.labelIds, draft.event.label_ids) ? { label_ids: draft.labelIds } : {};
    let ok: boolean;
    const original = draft.event;
    const changed = <K extends keyof EventInput & keyof YearclockEvent>(field: K) => original !== null && JSON.stringify(input[field]) !== JSON.stringify(original[field] ?? (field === "links" ? [] : field === "description_format" ? "plain" : null));
    if (draft.mode === "occurrence" && original?.occurrence_id) {
      const changes = { ...Object.fromEntries((["title", "starts_on", "description", "description_format", "location", "links", "starts_at", "ends_at", "lane_id", "category_id"] as const).filter(changed).map((field) => [field, input[field]])), ...labelChange };
      ok = await run(() => editOccurrence(organizationId, yearclock.id, original, changes), copy.saved);
    } else if (draft.mode === "future" && original?.series_id) {
      const changes = { ...Object.fromEntries((["title", "description", "description_format", "location", "links", "starts_at", "ends_at", "lane_id", "category_id"] as const).filter(changed).map((field) => [field, input[field]])), ...labelChange };
      ok = await run(async () => splitSeries(organizationId, yearclock.id, await loadSeries(organizationId, yearclock.id, original.series_id!), original, changes), copy.saved);
    } else if (draft.mode === "edit" && draft.event) {
      ok = await run(() => updateEvent(organizationId, yearclock.id, draft.event!, input), copy.saved);
    } else if (draft.frequency) {
      const series: SeriesInput = {
        title: input.title,
        lane_id: input.lane_id,
        category_id: input.category_id,
        description: input.description,
        description_format: input.description_format,
        location: input.location,
        links: input.links,
        starts_at: input.starts_at,
        ends_at: input.ends_at,
        starts_on: input.starts_on,
        frequency: draft.frequency,
        interval: Number(draft.interval) || 1,
        until: draft.endRule === "until" ? draft.until || null : null,
        occurrence_count: draft.endRule === "count" ? Number(draft.count) || null : null,
        last_day: draft.frequency === "MONTHLY" && draft.lastDay,
        label_ids: draft.labelIds,
      };
      ok = await run(() => createSeries(organizationId, yearclock.id, series), copy.saved);
    } else {
      ok = await run(() => createEvent(organizationId, yearclock.id, draft.origin ? { ...input, origin: draft.origin } : input), copy.saved);
    }
    if (ok) setDraft(null);
  }

  function formTitle(mode: EventDraft["mode"]): string {
    return mode === "create" ? copy.newEvent : mode === "occurrence" ? copy.editOccurrence : mode === "future" ? copy.editFuture : copy.edit;
  }

  const draftErrors: string[] = [];
  if (draft) {
    if (!draft.title.trim()) draftErrors.push(copy.titleRequired);
    if (!draft.startsOn && draft.mode !== "future") draftErrors.push(copy.startRequired);
    if (draft.endsOn && draft.startsOn && draft.endsOn < draft.startsOn) draftErrors.push(copy.endBeforeStart);
    if (draft.endsAt && !draft.startsAt) draftErrors.push(copy.endTimeNeedsStart);
    else if (draft.startsAt && draft.endsAt && (!draft.endsOn || draft.endsOn === draft.startsOn) && draft.endsAt <= draft.startsAt) draftErrors.push(copy.endTimeAfterStart);
    for (const problem of linkProblems(draft.links)) draftErrors.push(problem.kind === "tooMany" ? copy.tooManyLinks : problem.kind === "title" ? copy.linkTitleProblem(problem.row) : problem.kind === "address" ? copy.linkAddressProblem(problem.row) : copy.linkDuplicate(problem.row));
    if (draft.frequency && draft.endRule === "until" && (!draft.until || draft.until < draft.startsOn)) draftErrors.push(copy.invalidUntil);
    if (draft.frequency && draft.endRule === "count" && !(Number(draft.count) >= 1)) draftErrors.push(copy.invalidCount);
  }

  const selectEvent = (eventId: string | null) => { setDraft(null); setSelectedId(eventId); setTab(eventId ? "details" : "events"); };
  const hiddenByFilters = unfiltered.length - visible.length;
  const changesShown = changes && changes.total > 0 && !seen;

  const detailsPanel = selected ? (
    <aside className="yc-details-panel ui-native flex flex-col gap-3" aria-label={copy.details}>
      <div className="flex items-start gap-2">
        <h3 className="m-0 min-w-0 flex-1 text-base font-semibold">{selected.title}</h3>
        <Button size="sm" variant="ghost" onClick={() => selectEvent(null)}>{copy.close}</Button>
      </div>
      <dl className="yc-details m-0 grid grid-cols-[max-content_1fr] gap-x-3 gap-y-1 text-[13px] [&_dd]:m-0 [&_dt]:text-ink-muted">
        <dt>{copy.date}</dt><dd>{dateLabel(selected, locale)}</dd>
        <dt>{copy.lane}</dt><dd>{laneName(selected.lane_id)}</dd>
        <dt>{copy.category}</dt><dd>{categoryOf(selected.category_id)?.name ?? copy.none}</dd>
        {selected.location ? <><dt>{copy.location}</dt><dd>{selected.location}</dd></> : null}
        <dt>{copy.labels}</dt><dd>{labelsOf(selected).length ? <ul className="yc-label-list m-0 flex list-none flex-wrap gap-x-3 gap-y-1 p-0">{labelsOf(selected).map((label) => <li key={label.id}><span className="label-swatch inline-block size-[0.8em] rounded-full align-middle" style={{ background: label.color }} aria-hidden="true" /> {label.name}</li>)}</ul> : copy.none}</dd>
        {selected.series_id ? (
          <>
            <dt>{copy.recurrence}</dt>
            <dd>{copy.seriesDate(formatDay(selected.series_date ?? selected.starts_on, locale))}{selected.exception ? ` · ${copy.view.exception}` : ""}</dd>
          </>
        ) : null}
      </dl>
      {selected.description ? (selected.description_format === "markdown" ? <RichText text={selected.description} /> : <EventText text={selected.description} />) : null}
      {selected.links?.length ? <ul aria-label={copy.links} className="yc-links m-0 flex list-none flex-col gap-1 p-0">{selected.links.map((link) => <li key={link.url}><a href={link.url} rel="noopener noreferrer" target="_blank">{link.title}</a></li>)}</ul> : null}
      {selected.linked ? (() => {
        const source = lanes.find((lane) => lane.id === selected.lane_id)?.source;
        const sourceName = source?.yearclock_name ?? copy.lane;
        return (
          <>
            <p className="m-0 text-[13px] text-ink-muted">{copy.linked.note(sourceName)}</p>
            {selected.source_yearclock_id ? <p className="m-0"><Link to={`/organizations/${organizationId}/yearclocks/${selected.source_yearclock_id}`}>{copy.linked.openIn(sourceName)}</Link></p> : null}
          </>
        );
      })() : null}
      {canEdit && !selected.linked ? (
        <div className="flex flex-wrap gap-2">
          {selected.occurrence_id ? (
            <>
              <Button size="sm" variant="primary" onClick={() => setDraft(draftFrom(selected, "occurrence"))}>{copy.editOccurrence}</Button>
              <Button size="sm" onClick={() => setDraft(draftFrom(selected, "future"))}>{copy.editFuture}</Button>
              <Button size="sm" onClick={() => setDraft(draftCopy(selected, false))}>{copy.duplicate}</Button>
              <Button size="sm" onClick={() => setDraft(draftCopy(selected, true))}>{copy.planAgain}</Button>
              <Button size="sm" onClick={() => void run(() => skipOccurrence(organizationId, yearclock.id, selected.occurrence_id!), copy.skippedNotice).then((ok) => ok && selectEvent(null))}>{copy.skipOccurrence}</Button>
              {selected.exception ? <Button size="sm" onClick={() => void run(() => restoreOccurrence(organizationId, yearclock.id, selected), copy.saved)}>{copy.restoreSeriesValues}</Button> : null}
              <Button size="sm" variant="ghost-danger" onClick={() => { void confirm({ title: copy.confirmEndSeries(formatDay(selected.series_date ?? selected.starts_on, locale)), confirmLabel: copy.endSeries, destructive: true }).then((ok) => { if (ok) void run(async () => endSeries(organizationId, yearclock.id, await loadSeries(organizationId, yearclock.id, selected.series_id!), selected), copy.seriesEnded).then((ok) => ok && selectEvent(null)); }); }}>{copy.endSeries}</Button>
            </>
          ) : (
            <>
              <Button size="sm" variant="primary" onClick={() => setDraft(draftFrom(selected, "edit"))}>{copy.edit}</Button>
              <Button size="sm" onClick={() => setDraft(draftCopy(selected, false))}>{copy.duplicate}</Button>
              <Button size="sm" onClick={() => setDraft(draftCopy(selected, true))}>{copy.planAgain}</Button>
              <Button size="sm" variant="ghost-danger" onClick={() => { void confirm({ title: copy.confirmDelete(selected.title), confirmLabel: copy.delete, destructive: true }).then((ok) => { if (ok) void run(() => deleteEvent(organizationId, yearclock.id, selected), copy.deletedNotice).then((ok) => ok && selectEvent(null)); }); }}>{copy.delete}</Button>
            </>
          )}
        </div>
      ) : null}
      <EventHistory key={`${selected.id}-${selected.version}`} organizationId={organizationId} yearclockId={yearclock.id} event={selected} lanes={ownLanes} canRestore={canEdit && !selected.linked && !selected.occurrence_id} locale={locale} copy={copy} onRestored={() => { setNotice(copy.restoreVersion.done); void refresh(); }} onConflict={() => { setFailed(copy.restoreVersion.conflict); void refresh(); }} />
    </aside>
  ) : null;

  const bulkBar = canEdit ? (
    <BulkBar
      selecting={selecting}
      onSelecting={(value) => { setSelecting(value); if (!value) setChosen(new Set()); }}
      chosen={chosen}
      onSelectAll={() => setChosen(new Set(selectAllShown(visible)))}
      onClear={() => setChosen(new Set())}
      lanes={ownLanes}
      categories={ownCategories}
      labels={labels}
      noteId={bulkNoteId}
      onRun={(change, label) => void runBulk(change, change.action === "delete" ? copy.bulk.confirmDelete(chosen.size) : copy.bulk.confirm(chosen.size), label)}
      copy={copy}
    />
  ) : null;
  const selectionProps = canEdit && selecting ? { chosen, onToggle: (eventId: string) => setChosen((current) => { const next = new Set(current); if (next.has(eventId)) next.delete(eventId); else next.add(eventId); return next; }), blocked: (item: YearclockEvent) => bulkBlocker(item) !== null, label: copy.bulk.checkbox, noteId: bulkNoteId } : undefined;
  const eventsPanel = (
    <div className="flex flex-col gap-3">
      {bulkBar}
      <EventSummary marks={marks} locale={locale} lanes={displayLanes} categories={categories} labels={labels} events={visible} window={plan} selectedId={selectedId} onSelect={(eventId) => selectEvent(eventId)} copy={copy.view} selection={selectionProps} />
    </div>
  );
  const listView = (
    <>
      {bulkBar ? <div className="rounded-[var(--radius-card)] border border-line bg-surface p-3 shadow-[var(--shadow-card)]">{bulkBar}</div> : null}
      <ListDisplay locale={locale} window={plan} lanes={displayLanes} categories={categories} labels={labels} events={visible} selectedId={selectedId} onSelect={(eventId) => selectEvent(eventId)} selection={selectionProps} marks={marks} copy={copy.list} viewCopy={copy.view} />
    </>
  );
  async function runExport(choice: { format: "xlsx" | "csv" | "ics"; scope: "window" | "all" }): Promise<string | null> {
    try {
      const file = await exportYearclock(organizationId, yearclock.id, { ...choice, window_start: plan.start, length, filters, locale: locale === "fi" ? "fi" : "en" });
      saveBlob(file.blob, file.fileName);
      setExporting(null);
      setNotice(copy.exchange.exported);
      return null;
    } catch (error) {
      return error instanceof RateLimitedError ? copy.exchange.rateLimited(Math.max(1, Math.ceil(error.retryAfterSeconds / 60))) : copy.exchange.exportFailed;
    }
  }

  async function downloadImage() {
    const svg = document.querySelector<SVGSVGElement>(".yc-svg");
    if (!svg) return;
    setFailed(null);
    try {
      const legend = [...displayLanes.map((lane) => ({ label: lane.name })), ...categories.map((category) => ({ label: category.name, color: category.color ?? "#4a5a67" }))];
      saveBlob(await circleImage(svg, yearclock.name, copy.windowRange(formatDay(plan.start, locale), formatDay(plan.end, locale)), legend), imageFileName(yearclock.name, plan.start));
    } catch {
      setFailed(copy.exchange.imageFailed);
    }
  }

  const circleView = (
    <div className="flex justify-center rounded-[var(--radius-card)] border border-line bg-surface p-3 shadow-[var(--shadow-card)] sm:p-5">
      <YearclockView
        name={yearclock.name}
        locale={locale}
        window={plan}
        today={today}
        lanes={displayLanes}
        categories={categories}
        labels={labels}
        startMonth={startMonth}
        showWeeks={Boolean(yearclock.show_week_ring)}
        showQuarters={Boolean(yearclock.show_quarter_ring)}
        marks={marks}
        events={visible}
        selectedId={selectedId}
        onSelect={(eventId) => selectEvent(eventId)}
        onCreateAt={canEdit ? (laneId, date) => { setSelectedId(null); setTab("events"); setDraft(emptyDraft(laneId, date)); } : undefined}
        copy={copy.view}
      />
    </div>
  );
  // The main column renders the chosen display from the same visible Events; the side panel is shared (ADR-0029).
  const agendaView = (
    <>
      {circleView}
      <AgendaDisplay locale={locale} window={plan} lanes={displayLanes} categories={categories} labels={labels} events={visible} selectedId={selectedId} onSelect={(eventId) => selectEvent(eventId)} marks={marks} copy={copy.view} />
    </>
  );
  const timelineView = (
    <TimelineDisplay locale={locale} window={plan} today={today} lanes={displayLanes} categories={categories} labels={labels} events={visible} selectedId={selectedId} onSelect={(eventId) => selectEvent(eventId)}
      onCreateAt={canEdit ? (laneId, date) => { setSelectedId(null); setTab("filters"); setDraft(emptyDraft(laneId, date)); } : undefined}
      marks={marks} startMonth={startMonth} showWeeks={Boolean(yearclock.show_week_ring)} showQuarters={Boolean(yearclock.show_quarter_ring)} copy={copy.view} />
  );
  const mainDisplay = display === "list" ? listView : display === "agenda" ? agendaView : display === "timeline" ? timelineView : circleView;
  // The Events tab belongs to the displays that do not list the Events themselves.
  const showEventsTab = display === "circle";

  const panelTabs = [
    ...(showEventsTab ? [{ value: "events", label: copy.tabs.events, content: eventsPanel }] : []),
    ...(selected ? [{ value: "details", label: copy.tabs.details, content: detailsPanel }] : []),
    { value: "filters", label: isFiltering(filters) ? copy.tabs.filtersActive(hiddenByFilters) : copy.tabs.filters, content: <FilterPanel events={unfiltered} filters={filters} onChange={setFilters} lanes={displayLanes} categories={categories} labels={labels} copy={copy.filter} /> },
  ];
  const fallbackTab: PanelTab = showEventsTab ? "events" : selected ? "details" : "filters";
  const activeTab: PanelTab = (tab === "details" && !selected) || (tab === "events" && !showEventsTab) ? fallbackTab : tab;

  return (
    <section className="yc-planner flex flex-col gap-4" aria-label={yearclock.name}>
      <PrintHeader name={yearclock.name} window={plan} locale={locale} copy={copy.exchange} />
      <div className="flex flex-col gap-3 rounded-[var(--radius-card)] border border-line bg-surface p-3 shadow-[var(--shadow-card)] print:hidden">
        <div className="flex flex-wrap items-center gap-2">
          <div className="yc-toolbar flex min-w-0 max-w-full flex-wrap items-center gap-2" role="group" aria-label={copy.windowLabel}>
            <SegmentedControl label={copy.length} value={String(length)} options={WINDOW_LENGTHS.map((months) => ({ value: String(months), label: copy.lengthOption(months) }))} onChange={(value) => { const next = Number(value) as WindowLength; setLength(next); saveLength(yearclock.id, next); }} />
            <span className="flex items-center gap-1">
              <IconButton size="sm" variant="ghost" label={copy.previousPeriod} icon={<ChevronsLeft size={16} />} onClick={() => shiftWindow(-length)} />
              <IconButton size="sm" variant="ghost" label={copy.previousMonth} icon={<ChevronLeft size={16} />} onClick={() => shiftWindow(-1)} />
              <label className="inline-flex"><span className="sr-only">{copy.startMonth}</span><TextInput type="month" className="w-40" value={plan.start.slice(0, 7)} onChange={(event) => event.target.value && setWindowStart(`${event.target.value}-01`)} /></label>
              <IconButton size="sm" variant="ghost" label={copy.nextMonth} icon={<ChevronRight size={16} />} onClick={() => shiftWindow(1)} />
              <IconButton size="sm" variant="ghost" label={copy.nextPeriod} icon={<ChevronsRight size={16} />} onClick={() => shiftWindow(length)} />
            </span>
            <Button size="sm" onClick={() => setWindowStart(currentPeriod(today, length, startMonth))}>{copy.currentPeriod}</Button>
          </div>
          <DisplaySwitch value={display} onChange={(next) => { setDisplay(next); saveDisplay(yearclock.id, next); }} copy={copy.display} />
          <div className="ml-auto flex flex-wrap items-center gap-2">
            {changes && changes.total > 0 && !seen ? <Button size="sm" variant={changesOpen ? "secondary" : "ghost"} aria-expanded={changesOpen} aria-controls={changesId} onClick={() => setChangesOpen(!changesOpen)} icon={<History size={14} />}><Badge tone="accent">{copy.tabs.changes(changes.total)}</Badge></Button> : null}
            <ExportMenu copy={copy.exchange} importLabel={copy.import.menu} canDownloadImage={display === "circle"} canImport={canEdit} onPrint={() => globalThis.print()} onImage={() => void downloadImage()} onExport={(format) => setExporting(format)} onImport={() => setImporting(true)} />
            {canEdit ? <Link to={`/organizations/${organizationId}/yearclocks/${yearclock.id}/settings`} className="inline-flex h-[34px] items-center gap-1.5 rounded-[var(--radius-control)] border border-line bg-surface px-3 text-[13px] font-medium text-ink no-underline hover:bg-surface-subtle pointer-coarse:min-h-11"><Settings size={14} aria-hidden="true" />{copy.tabs.settings}</Link> : null}
            {canEdit ? <Button variant="primary" icon={<Plus size={15} />} onClick={() => { setSelectedId(null); setTab("events"); setDraft(emptyDraft(ownLanes[0]?.id ?? "")); }}>{copy.newEvent}</Button> : null}
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <SearchPanel organizationId={organizationId} yearclockId={yearclock.id} locale={locale} lanes={displayLanes} categories={categories} labels={labels} copy={copy.search} onChoose={(event) => {
            const end = event.ends_on ?? event.starts_on;
            if (end < plan.start || event.starts_on > plan.end) setWindowStart(`${event.starts_on.slice(0, 4)}-01-01`);
            selectEvent(event.id);
          }} />
          <p className="m-0 ml-auto text-[13px] text-ink-muted" aria-live="polite">{copy.windowRange(formatDay(plan.start, locale), formatDay(plan.end, locale))}</p>
        </div>
      </div>
      {othersChanged ? (
        <Alert tone="info" role="status" className="yc-change-notice print:hidden" action={<Button size="sm" onClick={() => { setOthersChanged(false); setLoadedAt(new Date().toISOString()); void refresh(); }}>{copy.changeNotice.refresh}</Button>}>
          {copy.changeNotice.text}
        </Alert>
      ) : null}
      {failed && !draft ? <Alert tone="danger" role="alert" className="print:hidden">{failed}</Alert> : null}
      {changesShown && changesOpen ? (
        <section id={changesId} className="yc-changes print:hidden flex flex-col gap-2 rounded-[var(--radius-card)] border border-line bg-surface p-4 shadow-[var(--shadow-card)]" aria-label={copy.changesPanel.title(changes.total)}>
          <h3 className="m-0 text-sm font-semibold">{copy.changesPanel.title(changes.total)}</h3>
          <ol className="m-0 flex list-none flex-col divide-y divide-line p-0">
            {changes.items.map((item) => {
              const deleted = item.kind === "deleted" && canEdit ? deletedEvents.find((event) => event.id === item.event_id) : undefined;
              return (
                <li key={`${item.event_id ?? item.series_id}-${item.kind}`} className="flex flex-wrap items-center gap-x-2 py-2 text-[13px]">
                  <span className="flex-1"><strong>{item.title}</strong>{" — "}{item.kind === "series_changed" ? copy.changesPanel.seriesChanged(item.count) : copy.changesPanel.kinds[item.kind]}
                  <span className="yc-history-meta text-xs text-ink-muted">{` · ${new Intl.DateTimeFormat(locale === "fi" ? "fi-FI" : "en-GB", { dateStyle: "medium", timeStyle: "short" }).format(new Date(item.at))} · ${describeActor(item.actor, copy.history)}`}</span></span>
                  {deleted ? <Button size="sm" onClick={() => void run(() => restoreEvent(organizationId, yearclock.id, deleted), copy.changesPanel.restored)}>{copy.changesPanel.restore}</Button> : null}
                </li>
              );
            })}
          </ol>
          {changes.more ? <p className="m-0 text-[13px] text-ink-muted">{copy.changesPanel.more(changes.total - changes.items.length)}</p> : null}
          <div><Button size="sm" onClick={() => setSeen(true)}>{copy.changesPanel.markSeen}</Button></div>
        </section>
      ) : null}
      <div className="yc-layout grid items-start gap-4 print:block lg:grid-cols-[minmax(0,1fr)_minmax(340px,400px)]">
        <div className="flex min-w-0 flex-col gap-4">{mainDisplay}</div>
        <div className="yc-side-panel print:hidden rounded-[var(--radius-card)] border border-line bg-surface shadow-[var(--shadow-card)] lg:sticky lg:top-[72px] lg:max-h-[calc(100vh-88px)] lg:overflow-y-auto">
          <Tabs label={copy.tabs.label} value={activeTab} onValueChange={(value) => setTab(value as PanelTab)} tabs={panelTabs.map((item) => ({ ...item, content: <div className="p-4">{item.content}</div> }))} />
        </div>
      </div>
      <ExportDialog open={exporting !== null} onOpenChange={(open) => { if (!open) setExporting(null); }} initialFormat={exporting ?? "xlsx"} windowRange={`${formatDay(plan.start, locale)} – ${formatDay(plan.end, locale)}`} filtering={isFiltering(filters)} copy={copy.exchange} cancelLabel={messages(locale).overlay.cancel} onExport={runExport} />
      <ImportDialog open={importing} onOpenChange={setImporting} organizationId={organizationId} yearclockId={yearclock.id} locale={locale === "fi" ? "fi" : "en"} copy={copy.import} rateLimited={copy.exchange.rateLimited} cancelLabel={messages(locale).overlay.cancel} onImported={(count) => { setNotice(copy.import.imported(count)); void refresh(); }} />
      <Drawer open={draft !== null} onOpenChange={(open) => { if (!open) setDraft(null); }} title={draft ? formTitle(draft.mode) : ""} width={480}>
        {draft ? (
          <form className="yc-form ui-native flex flex-col gap-4" aria-label={formTitle(draft.mode)} onSubmit={(event) => { event.preventDefault(); if (!draftErrors.length) void save(); }}>
            {failed ? <Alert tone="danger" role="alert">{failed}</Alert> : null}
            {draft.mode === "future" && draft.event ? <Alert tone="info">{copy.futureNote(formatDay(draft.event.series_date ?? draft.event.starts_on, locale))}</Alert> : null}
            {draft.mode === "occurrence" ? <Alert tone="info">{copy.occurrenceNote}</Alert> : null}
            <label className={FIELD}>{copy.title}<TextInput required maxLength={TITLE_LIMIT} value={draft.title} onChange={(event) => setDraft({ ...draft, title: event.target.value })} /></label>
            <div className="grid gap-4 sm:grid-cols-2">
              {draft.mode !== "future" ? <label className={FIELD}>{copy.start}<TextInput type="date" required value={draft.startsOn} onChange={(event) => setDraft({ ...draft, startsOn: event.target.value })} /></label> : null}
              {draft.mode === "create" || draft.mode === "edit" ? <label className={FIELD}>{copy.end}<TextInput type="date" min={draft.startsOn || undefined} value={draft.endsOn} onChange={(event) => setDraft({ ...draft, endsOn: event.target.value })} /></label> : null}
              <label className={FIELD}>{copy.startTime}<TextInput type="time" step={60} value={draft.startsAt} onChange={(event) => setDraft({ ...draft, startsAt: event.target.value, endsAt: event.target.value ? draft.endsAt : "" })} /></label>
              <label className={FIELD}>{copy.endTime}<TextInput type="time" step={60} disabled={!draft.startsAt} value={draft.endsAt} onChange={(event) => setDraft({ ...draft, endsAt: event.target.value })} /></label>
              <label className={FIELD}>{copy.lane}<Select value={draft.laneId} onChange={(event) => setDraft({ ...draft, laneId: event.target.value })}>{ownLanes.map((lane) => <option key={lane.id} value={lane.id}>{lane.name}</option>)}</Select></label>
              <label className={FIELD}>{copy.category}<Select value={draft.categoryId} onChange={(event) => setDraft({ ...draft, categoryId: event.target.value })}><option value="">{copy.none}</option>{ownCategories.some((category) => category.scope === "organization") ? (
                <>
                  <optgroup label={copy.sharedCategories}>{ownCategories.filter((category) => category.scope === "organization").map((category) => <option key={category.id} value={category.id}>{category.name}</option>)}</optgroup>
                  <optgroup label={copy.ownCategories}>{ownCategories.filter((category) => category.scope !== "organization").map((category) => <option key={category.id} value={category.id}>{category.name}</option>)}</optgroup>
                </>
              ) : ownCategories.map((category) => <option key={category.id} value={category.id}>{category.name}</option>)}</Select></label>
            </div>
            <LabelPicker organizationId={organizationId} labels={labels} selected={draft.labelIds} onChange={(labelIds) => setDraft((current) => (current ? { ...current, labelIds } : current))} onCreated={(label) => setLabels((current) => [...current.filter((item) => item.id !== label.id), label].sort((a, b) => a.name.localeCompare(b.name)))} copy={copy} />
            <DescriptionEditor value={draft.description} format={draft.descriptionFormat} limit={DESCRIPTION_LIMIT} onChange={(description) => setDraft((current) => (current ? { ...current, description } : current))} onFormatChange={(descriptionFormat) => setDraft((current) => (current ? { ...current, descriptionFormat } : current))} copy={copy} />
            <label className={FIELD}>{copy.location}<TextInput maxLength={LOCATION_MAX} value={draft.location} onChange={(event) => setDraft({ ...draft, location: event.target.value })} /></label>
            <LinksEditor links={draft.links} onChange={(links) => setDraft((current) => (current ? { ...current, links } : current))} copy={copy} />
            {draft.mode === "create" ? (
              <fieldset className="yc-recurrence m-0 flex flex-col gap-3 rounded-[10px] border border-line p-3">
                <legend className="px-1 text-[13px] font-semibold">{copy.repeat}</legend>
                <label className={FIELD}>{copy.repeat}<Select value={draft.frequency} onChange={(event) => setDraft({ ...draft, frequency: event.target.value as Frequency, endsOn: "" })}>
                  <option value="">{copy.doesNotRepeat}</option>
                  <option value="WEEKLY">{copy.weekly}</option>
                  <option value="MONTHLY">{copy.monthly}</option>
                  <option value="YEARLY">{copy.yearly}</option>
                </Select></label>
                {draft.frequency ? (
                  <div className="grid gap-3 sm:grid-cols-2">
                    <label className={FIELD}>{copy.every}<TextInput type="number" min={1} value={draft.interval} onChange={(event) => setDraft({ ...draft, interval: event.target.value })} /></label>
                    <label className={FIELD}>{copy.ends}<Select value={draft.endRule} onChange={(event) => setDraft({ ...draft, endRule: event.target.value as EndRule })}>
                      <option value="never">{copy.never}</option>
                      <option value="until">{copy.onDate}</option>
                      <option value="count">{copy.afterCount}</option>
                    </Select></label>
                    {draft.frequency === "MONTHLY" ? <Choice className="yc-check sm:col-span-2" checked={draft.lastDay} onChange={(event) => setDraft({ ...draft, lastDay: event.target.checked })} label={copy.lastDay} /> : null}
                    {draft.endRule === "until" ? <label className={FIELD}>{copy.untilDate}<TextInput type="date" min={draft.startsOn || undefined} value={draft.until} onChange={(event) => setDraft({ ...draft, until: event.target.value })} /></label> : null}
                    {draft.endRule === "count" ? <label className={FIELD}>{copy.occurrenceCount}<TextInput type="number" min={1} value={draft.count} onChange={(event) => setDraft({ ...draft, count: event.target.value })} /></label> : null}
                  </div>
                ) : null}
              </fieldset>
            ) : null}
            {draftErrors.length ? <ul className="yc-errors m-0 list-disc pl-5 text-[13px] text-danger" aria-live="polite">{draftErrors.map((error) => <li key={error}>{error}</li>)}</ul> : null}
            <div className="sticky bottom-0 -mx-5 -mb-4 flex justify-end gap-2 border-t border-line bg-surface px-5 py-3">
              <Button onClick={() => setDraft(null)}>{copy.cancel}</Button>
              <Button type="submit" variant="primary" disabled={draftErrors.length > 0}>{copy.save}</Button>
            </div>
          </form>
        ) : null}
      </Drawer>
      <PrintAppendix window={plan} locale={locale} display={display} lanes={displayLanes} categories={categories} events={visible} copy={copy.exchange} listCopy={copy.list} summaryTitle={copy.view.summaryTitle} recurring={copy.view.recurring} occurrences={copy.view.occurrences} />
      {canEdit && skipped.length ? (
        <Card aria-label={copy.skippedTitle} className="print:hidden flex flex-col gap-2">
          <h3 className="m-0 text-sm font-semibold">{copy.skippedTitle}</h3>
          <ul className="m-0 flex list-none flex-col divide-y divide-line p-0">{skipped.map((item) => <li key={item.id} className="flex flex-wrap items-center gap-2 py-2 text-[13px]"><span className="flex-1">{formatDay(item.starts_on, locale)} — {item.title}</span><Button size="sm" onClick={() => void run(() => skipOccurrence(organizationId, yearclock.id, item.occurrence_id!, false), copy.saved)}>{copy.restoreOccurrence}</Button></li>)}</ul>
        </Card>
      ) : null}
      {canEdit && deletedEvents.length ? (
        <Card aria-label={copy.deletedTitle} className="print:hidden flex flex-col gap-2">
          <h3 className="m-0 text-sm font-semibold">{copy.deletedTitle}</h3>
          <ul className="m-0 flex list-none flex-col divide-y divide-line p-0">{deletedEvents.map((item) => <li key={item.id} className="flex flex-wrap items-center gap-2 py-2 text-[13px]"><span className="flex-1">{dateLabel(item, locale)} — {item.title}{item.purge_after ? ` (${copy.recoverableUntil(formatDay(item.purge_after.slice(0, 10), locale))})` : ""}</span><Button size="sm" onClick={() => void run(() => restoreEvent(organizationId, yearclock.id, item), copy.saved)}>{copy.restore}</Button></li>)}</ul>
        </Card>
      ) : null}
    </section>
  );
}

/** `/organizations/:org/yearclocks/:id/settings`: Layout, Lanes (own, copied, linked), Categories, and Plan a season again. */
export function YearclockSettings({ organizationId, yearclock, locale, timeZone, sources, onStructureChanged }: { organizationId: string; yearclock: WorkspaceYearclock; locale: Locale; timeZone: string; sources: WorkspaceYearclock[]; onStructureChanged: () => void }) {
  const copy: PlannerMessages = workspaceMessages(locale).planner;
  const [categories, setCategories] = useState<YearclockCategory[]>([]);
  const [failed, setFailed] = useState(false);
  const refresh = useCallback(() => { void loadCategories(organizationId, yearclock.id).then(setCategories, () => setFailed(true)); }, [organizationId, yearclock.id]);
  useEffect(refresh, [refresh]);
  const ownLanes = yearclock.lanes.filter((lane) => !lane.source_lane_id);
  const ownCategories = categories.filter((category) => category.scope !== "linked");
  const today = organizationToday(timeZone);
  const card = "yc-settings-card ui-native rounded-[var(--radius-card)] border border-line bg-surface p-5 shadow-[var(--shadow-card)]";
  return (
    <div className="yc-structure grid gap-5 xl:grid-cols-2">
      {failed ? <Alert tone="danger" role="alert" className="xl:col-span-2">{copy.loadFailed}</Alert> : null}
      <div className={card}><LayoutManager organizationId={organizationId} yearclock={yearclock} locale={locale} copy={copy} onChanged={onStructureChanged} /></div>
      <div className={card}><LaneManager organizationId={organizationId} yearclock={yearclock} copy={copy} onChanged={onStructureChanged} /></div>
      <div className={card}><CategoryManager organizationId={organizationId} yearclockId={yearclock.id} categories={ownCategories} copy={copy} onChanged={refresh} /></div>
      <div className={card}><PlanAgainPanel organizationId={organizationId} yearclockId={yearclock.id} seasonNow={currentPeriod(today, 12, yearclock.start_month ?? 1)} lanes={ownLanes} categories={ownCategories} locale={locale} copy={copy} onCreated={() => undefined} /></div>
      <div className={card}><LaneCopier organizationId={organizationId} yearclock={yearclock} sources={sources.length ? sources : [yearclock]} copy={copy} onCopied={() => { onStructureChanged(); refresh(); }} /></div>
      <div className={card}><LaneLinker organizationId={organizationId} yearclock={yearclock} sources={sources} copy={copy} onLinked={() => { onStructureChanged(); refresh(); }} /></div>
    </div>
  );
}

function CategoryManager({ organizationId, yearclockId, categories: all, copy, onChanged }: { organizationId: string; yearclockId: string; categories: YearclockCategory[]; copy: PlannerMessages; onChanged: () => void }) {
  const confirm = useConfirm();
  const shared = all.filter((category) => category.scope === "organization");
  const categories = all.filter((category) => category.scope !== "organization");
  const [name, setName] = useState("");
  const [color, setColor] = useState("#336699");
  const [failed, setFailed] = useState(false);
  async function act(action: () => Promise<unknown>) {
    setFailed(false);
    try { await action(); onChanged(); } catch { setFailed(true); }
  }
  function move(index: number, delta: number) {
    const ids = categories.map((category) => category.id);
    [ids[index], ids[index + delta]] = [ids[index + delta], ids[index]];
    void act(() => reorderCategories(organizationId, yearclockId, categories, ids));
  }
  return (
    <section aria-label={copy.categories}>
      <h5>{copy.categories}</h5>
      {failed ? <p role="alert">{copy.saveFailed}</p> : null}
      {shared.length ? (
        <>
          <h6>{copy.sharedCategories}</h6>
          <p className="m-0 mt-1 text-xs text-ink-muted">{copy.sharedCategoryNote}</p>
          <ul aria-label={copy.sharedCategories}>{shared.map((category) => <li key={category.id}><span className="yc-swatch inline-block size-[0.8em] rounded-[2px] border border-ink align-[-0.05em]" style={{ background: category.color ?? "#4a5a67" }} aria-hidden="true" /> {category.name}</li>)}</ul>
          <h6>{copy.ownCategories}</h6>
        </>
      ) : null}
      <ul>
        {categories.map((category, index) => (
          <li key={`${category.id}-${category.version}`}>
            <CategoryRow category={category} copy={copy} onSave={(nextName, nextColor) => act(() => updateCategory(organizationId, yearclockId, category, nextName, nextColor))} />
            {index > 0 ? <button type="button" aria-label={`${copy.up}: ${category.name}`} onClick={() => move(index, -1)}>{copy.up}</button> : null}
            {index < categories.length - 1 ? <button type="button" aria-label={`${copy.down}: ${category.name}`} onClick={() => move(index, 1)}>{copy.down}</button> : null}
            <button type="button" aria-label={`${copy.delete}: ${category.name}`} onClick={() => { void confirm({ title: copy.confirmCategoryDelete(category.name), confirmLabel: copy.delete, destructive: true }).then((ok) => { if (ok) void act(() => deleteCategory(organizationId, yearclockId, category)); }); }}>{copy.delete}</button>
          </li>
        ))}
      </ul>
      <label>{copy.name} <input maxLength={120} value={name} onChange={(event) => setName(event.target.value)} /></label>{" "}
      <label>{copy.color} <input type="color" value={color} onChange={(event) => setColor(event.target.value)} /></label>{" "}
      <button type="button" disabled={!name.trim()} onClick={() => void act(() => createCategory(organizationId, yearclockId, name.trim(), color)).then(() => setName(""))}>{copy.addCategory}</button>
    </section>
  );
}

function CategoryRow({ category, copy, onSave }: { category: YearclockCategory; copy: PlannerMessages; onSave: (name: string, color: string | null) => Promise<void> }) {
  const [name, setName] = useState(category.name);
  const [color, setColor] = useState(category.color ?? "#4a5a67");
  return (
    <>
      <span className="yc-swatch inline-block size-[0.8em] rounded-[2px] border border-ink align-[-0.05em]" style={{ background: category.color ?? "#4a5a67" }} aria-hidden="true" />{" "}
      <label><span className="sr-only">{`${copy.name}: ${category.name}`}</span><input maxLength={120} value={name} onChange={(event) => setName(event.target.value)} /></label>{" "}
      <label><span className="sr-only">{`${copy.color}: ${category.name}`}</span><input type="color" value={color} onChange={(event) => setColor(event.target.value)} /></label>{" "}
      <button type="button" disabled={!name.trim()} onClick={() => void onSave(name.trim(), color)}>{copy.save}</button>{" "}
    </>
  );
}

function LaneManager({ organizationId, yearclock, copy, onChanged }: { organizationId: string; yearclock: WorkspaceYearclock; copy: PlannerMessages; onChanged: () => void }) {
  const [name, setName] = useState("");
  const [failed, setFailed] = useState(false);
  const [blocked, setBlocked] = useState<{ laneId: string; events: number; series: number } | null>(null);
  const [target, setTarget] = useState("");
  async function act(action: () => Promise<unknown>) {
    setFailed(false);
    try { await action(); onChanged(); } catch { setFailed(true); }
  }
  async function remove(lane: WorkspaceYearclock["lanes"][number]) {
    setFailed(false);
    try {
      await deleteLane(organizationId, yearclock.id, lane);
      setBlocked(null);
      onChanged();
    } catch (error) {
      if (error instanceof LaneHasEventsError) {
        setBlocked({ laneId: lane.id, events: error.events, series: error.series });
        setTarget(yearclock.lanes.find((item) => item.id !== lane.id)?.id ?? "");
      } else {
        setFailed(true);
      }
    }
  }
  async function moveThenRemove(lane: WorkspaceYearclock["lanes"][number]) {
    setFailed(false);
    try {
      await moveLaneEvents(organizationId, yearclock.id, lane, target);
      await deleteLane(organizationId, yearclock.id, { ...lane, version: lane.version + 1 });
      setBlocked(null);
      onChanged();
    } catch {
      setFailed(true);
      onChanged();
    }
  }
  function move(index: number, delta: number) {
    const ids = yearclock.lanes.map((lane) => lane.id);
    [ids[index], ids[index + delta]] = [ids[index + delta], ids[index]];
    void act(() => reorderLanes(organizationId, yearclock, ids));
  }
  return (
    <section aria-label={copy.lanes}>
      <h5>{copy.lanes}</h5>
      {failed ? <p role="alert">{copy.saveFailed}</p> : null}
      <ol>
        {yearclock.lanes.map((lane, index) => (
          <li key={`${lane.id}-${lane.version}`}>
            <LaneRow lane={lane} copy={copy} onSave={(next, appearance) => act(() => renameLane(organizationId, yearclock.id, lane, next, appearance))} />
            {lane.source_lane_id ? <span className="yc-linked-marker text-xs text-ink-muted">{`${copy.linked.marker}: ${linkedLaneName(lane, copy)}`}</span> : null}{" "}
            {index > 0 ? <button type="button" aria-label={`${copy.up}: ${lane.name}`} onClick={() => move(index, -1)}>{copy.up}</button> : null}
            {index < yearclock.lanes.length - 1 ? <button type="button" aria-label={`${copy.down}: ${lane.name}`} onClick={() => move(index, 1)}>{copy.down}</button> : null}
            {yearclock.lanes.length > 1 ? <button type="button" aria-label={`${copy.delete}: ${lane.name}`} onClick={() => void remove(lane)}>{copy.delete}</button> : null}
            {blocked?.laneId === lane.id ? (
              <div className="yc-lane-move" role="group" aria-label={copy.moveEventsTitle(lane.name)}>
                <p>{copy.laneHasEvents(blocked.events, blocked.series)}</p>
                <label>{copy.moveTo} <select value={target} onChange={(event) => setTarget(event.target.value)}>{yearclock.lanes.filter((item) => item.id !== lane.id).map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>{" "}
                <button type="button" disabled={!target} onClick={() => void moveThenRemove(lane)}>{copy.moveAndDelete}</button>{" "}
                <button type="button" onClick={() => setBlocked(null)}>{copy.cancel}</button>
              </div>
            ) : null}
          </li>
        ))}
      </ol>
      <label>{copy.newLane} <input maxLength={200} value={name} onChange={(event) => setName(event.target.value)} /></label>{" "}
      <button type="button" disabled={!name.trim()} onClick={() => void act(() => createLane(organizationId, yearclock.id, name.trim())).then(() => setName(""))}>{copy.addLane}</button>
    </section>
  );
}

function EventHistory({ organizationId, yearclockId, event, lanes, canRestore, locale, copy, onRestored, onConflict }: { organizationId: string; yearclockId: string; event: YearclockEvent; lanes: Lane[]; canRestore: boolean; locale: Locale; copy: PlannerMessages; onRestored: () => void; onConflict: () => void }) {
  const text = copy.historyPanel;
  const eventId = event.id;
  const [restoring, setRestoring] = useState<{ item: HistoryItem; preview: RestorePreview } | null>(null);
  const [restoreFailed, setRestoreFailed] = useState(false);
  async function startRestore(item: HistoryItem) {
    setRestoreFailed(false);
    try {
      setRestoring({ item, preview: await previewVersionRestore(organizationId, yearclockId, eventId, item.id) });
    } catch {
      setRestoreFailed(true);
    }
  }
  const [items, setItems] = useState<HistoryItem[] | null>(null);
  const [next, setNext] = useState<number | null>(null);
  const [failed, setFailed] = useState(false);
  const [busy, setBusy] = useState(false);
  const stamp = new Intl.DateTimeFormat(locale === "fi" ? "fi-FI" : "en-GB", { dateStyle: "medium", timeStyle: "short" });
  async function load(offset: number) {
    setBusy(true);
    setFailed(false);
    try {
      const page = await loadEventHistory(organizationId, yearclockId, eventId, offset);
      setItems((current) => [...(offset ? current ?? [] : []), ...page.items]);
      setNext(page.next_offset);
    } catch {
      setFailed(true);
    } finally {
      setBusy(false);
    }
  }
  return (
    <details className="yc-history mt-1" onToggle={(event) => { if (event.currentTarget.open && items === null && !busy) void load(0); }}>
      <summary>{text.title}</summary>
      <p role="status" className="m-0 mt-1 text-xs text-ink-muted">{busy && items === null ? text.loading : failed ? text.failed : items?.length === 0 ? text.empty : ""}</p>
      {items?.length ? (
        <ol className="yc-history-list my-2 flex flex-col gap-2 pl-4">
          {items.map((item, index) => (
            <li key={item.id}>
              <strong>{describeEntry(item, copy.history)}</strong>{" "}
              <span className="yc-history-meta text-xs text-ink-muted">{text.at(stamp.format(new Date(item.created_at)), describeActor(item.actor, copy.history))}</span>
              {item.changes.length ? <ul>{describeChanges(item.changes, copy.history, (value) => formatDay(value, locale)).map((line) => <li key={line}>{line}</li>)}</ul> : null}
              {canRestore && !event.deleted_at && index > 0 ? <p><button type="button" aria-label={copy.restoreVersion.label(stamp.format(new Date(item.created_at)))} onClick={() => void startRestore(item)}>{copy.restoreVersion.action}</button></p> : null}
              {restoring?.item.id === item.id ? <RestoreVersionPanel organizationId={organizationId} yearclockId={yearclockId} event={event} item={item} preview={restoring.preview} lanes={lanes} when={stamp.format(new Date(item.created_at))} locale={locale} copy={copy} onDone={onRestored} onConflict={onConflict} onCancel={() => setRestoring(null)} /> : null}
            </li>
          ))}
        </ol>
      ) : null}
      {restoreFailed ? <p role="alert">{copy.restoreVersion.failed}</p> : null}
      {next !== null ? <button type="button" disabled={busy} onClick={() => void load(next)}>{text.more}</button> : null}
    </details>
  );
}

function RestoreVersionPanel({ organizationId, yearclockId, event, item, preview, lanes, when, locale, copy, onDone, onConflict, onCancel }: { organizationId: string; yearclockId: string; event: YearclockEvent; item: HistoryItem; preview: RestorePreview; lanes: Lane[]; when: string; locale: Locale; copy: PlannerMessages; onDone: () => void; onConflict: () => void; onCancel: () => void }) {
  const text = copy.restoreVersion;
  const [laneId, setLaneId] = useState(lanes[0]?.id ?? "");
  const [failed, setFailed] = useState(false);
  const laneField = useId();
  const lines = describeChanges(preview.changes, copy.history, (value) => formatDay(value, locale));
  const nothing = !lines.length && !preview.lane_missing && !preview.category_removed && !preview.labels_removed;
  async function confirm() {
    setFailed(false);
    try {
      await restoreVersion(organizationId, yearclockId, event, item.id, preview.lane_missing ? laneId : undefined);
      onDone();
    } catch (error) {
      if (error instanceof ConflictError) onConflict(); else setFailed(true);
    }
  }
  return (
    <div className="yc-restore my-1.5 rounded-[10px] border border-line px-3 py-2" role="group" aria-label={text.title(when)}>
      <h5>{text.title(when)}</h5>
      {nothing ? <p>{text.nothing}</p> : <ul>{lines.map((line) => <li key={line}>{line}</li>)}</ul>}
      {preview.category_removed ? <p className="m-0 mt-1 text-xs text-ink-muted">{text.categoryRemoved}</p> : null}
      {preview.labels_removed ? <p className="m-0 mt-1 text-xs text-ink-muted">{text.labelsRemoved(preview.labels_removed)}</p> : null}
      {preview.lane_missing ? <p><label htmlFor={laneField}>{text.chooseLane}</label>{" "}<select id={laneField} value={laneId} onChange={(change) => setLaneId(change.target.value)}>{lanes.map((lane) => <option key={lane.id} value={lane.id}>{lane.name}</option>)}</select></p> : null}
      <p className="yc-actions flex flex-wrap gap-2">
        <button type="button" className="primary-button" disabled={nothing || (preview.lane_missing && !laneId)} onClick={() => void confirm()}>{text.confirm}</button>
        <button type="button" onClick={onCancel}>{text.cancel}</button>
      </p>
      {failed ? <p role="alert">{text.failed}</p> : null}
    </div>
  );
}

function LaneLinker({ organizationId, yearclock, sources, copy, onLinked }: { organizationId: string; yearclock: WorkspaceYearclock; sources: WorkspaceYearclock[]; copy: PlannerMessages; onLinked: () => void }) {
  const text = copy.linkLane;
  const already = new Set(yearclock.lanes.map((lane) => lane.source_lane_id).filter(Boolean));
  const candidates = sources.filter((item) => item.id !== yearclock.id).map((item) => ({ ...item, lanes: item.lanes.filter((lane) => !lane.source_lane_id && !already.has(lane.id)) })).filter((item) => item.lanes.length);
  const [sourceId, setSourceId] = useState("");
  const [laneId, setLaneId] = useState("");
  const [notice, setNotice] = useState<{ ok: boolean; text: string } | null>(null);
  const ids = { yearclock: useId(), lane: useId() };
  const source = candidates.find((item) => item.id === sourceId) ?? candidates[0];
  const lane = source?.lanes.find((item) => item.id === laneId) ?? source?.lanes[0];
  async function run() {
    if (!lane) return;
    setNotice(null);
    try {
      await linkLane(organizationId, yearclock.id, lane.id);
      setNotice({ ok: true, text: text.done });
      setLaneId("");
      onLinked();
    } catch (error) {
      setNotice({ ok: false, text: error instanceof LimitReachedError ? text.limit(error.maximum) : text.failed });
    }
  }
  return (
    <section aria-label={text.title}>
      <h5>{text.title}</h5>
      <p className="m-0 mt-1 text-xs text-ink-muted">{text.description}</p>
      {source ? (
        <>
          <p>
            <label htmlFor={ids.yearclock}>{text.yearclock}</label>{" "}
            <select id={ids.yearclock} value={source.id} onChange={(event) => { setSourceId(event.target.value); setLaneId(""); setNotice(null); }}>{candidates.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select>{" "}
            <label htmlFor={ids.lane}>{text.lane}</label>{" "}
            <select id={ids.lane} value={lane?.id ?? ""} onChange={(event) => { setLaneId(event.target.value); setNotice(null); }}>{source.lanes.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select>
          </p>
          <p><button type="button" disabled={!lane} onClick={() => void run()}>{text.link}</button></p>
        </>
      ) : <p>{text.none}</p>}
      {notice ? <p role={notice.ok ? "status" : "alert"}>{notice.text}</p> : null}
    </section>
  );
}

function LaneCopier({ organizationId, yearclock, sources, copy, onCopied }: { organizationId: string; yearclock: WorkspaceYearclock; sources: WorkspaceYearclock[]; copy: PlannerMessages; onCopied: () => void }) {
  const text = copy.copyLane;
  const [sourceId, setSourceId] = useState(() => sources.find((item) => item.id !== yearclock.id)?.id ?? sources[0]?.id ?? "");
  const source = sources.find((item) => item.id === sourceId) ?? sources[0];
  const [laneId, setLaneId] = useState("");
  const [includeEvents, setIncludeEvents] = useState(true);
  const [notice, setNotice] = useState<{ ok: boolean; text: string } | null>(null);
  const ids = { yearclock: useId(), lane: useId() };
  const lane = source?.lanes.find((item) => item.id === laneId) ?? source?.lanes[0];
  async function run() {
    if (!lane) return;
    setNotice(null);
    try {
      const result = await copyLane(organizationId, yearclock.id, lane.id, includeEvents);
      setNotice({ ok: true, text: text.done(result.events, result.series) });
      onCopied();
    } catch (error) {
      setNotice({ ok: false, text: error instanceof LimitReachedError ? text.limit(text.limitNames[error.limit] ?? error.limit, error.maximum) : text.failed });
    }
  }
  return (
    <section aria-label={text.title}>
      <h5>{text.title}</h5>
      <p>
        <label htmlFor={ids.yearclock}>{text.yearclock}</label>{" "}
        <select id={ids.yearclock} value={source?.id ?? ""} onChange={(event) => { setSourceId(event.target.value); setLaneId(""); setNotice(null); }}>{sources.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select>{" "}
        <label htmlFor={ids.lane}>{text.lane}</label>{" "}
        <select id={ids.lane} value={lane?.id ?? ""} onChange={(event) => { setLaneId(event.target.value); setNotice(null); }}>{(source?.lanes ?? []).map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select>
      </p>
      <p><label><input type="checkbox" checked={includeEvents} onChange={(event) => setIncludeEvents(event.target.checked)} /> {text.includeEvents}</label></p>
      <p><button type="button" disabled={!lane} onClick={() => void run()}>{text.copy}</button></p>
      {notice ? <p role={notice.ok ? "status" : "alert"}>{notice.text}</p> : null}
    </section>
  );
}

function LaneRow({ lane, copy, onSave }: { lane: WorkspaceYearclock["lanes"][number]; copy: PlannerMessages; onSave: (name: string, appearance: { tint: string | null; height: "normal" | "tall" }) => Promise<void> }) {
  const [name, setName] = useState(lane.name);
  const [tint, setTint] = useState<string>(lane.tint ?? "");
  const [height, setHeight] = useState<"normal" | "tall">(lane.height ?? "normal");
  const tintId = useId();
  const heightId = useId();
  const linked = Boolean(lane.source_lane_id);
  const changed = (!linked && name.trim() !== lane.name) || tint !== (lane.tint ?? "") || height !== (lane.height ?? "normal");
  return (
    <>
      {linked ? null : <><label><span className="sr-only">{`${copy.name}: ${lane.name}`}</span><input maxLength={200} value={name} onChange={(event) => setName(event.target.value)} /></label>{" "}</>}
      <label htmlFor={tintId} className="sr-only">{`${copy.tint}: ${lane.name}`}</label>
      <select id={tintId} value={tint} onChange={(event) => setTint(event.target.value)}>
        <option value="">{copy.noTint}</option>
        {LABEL_COLORS.map((color, index) => <option key={color} value={color}>{copy.tintNames[index] ?? color}</option>)}
      </select>{" "}
      <label htmlFor={heightId} className="sr-only">{`${copy.height}: ${lane.name}`}</label>
      <select id={heightId} value={height} onChange={(event) => setHeight(event.target.value as "normal" | "tall")}>
        <option value="normal">{copy.normalHeight}</option>
        <option value="tall">{copy.tallHeight}</option>
      </select>{" "}
      <button type="button" disabled={!name.trim() || !changed} onClick={() => void onSave(name.trim(), { tint: tint || null, height })}>{copy.save}</button>{" "}
    </>
  );
}

const MAX_EVENT_LABELS = 10;

/** Choose up to ten Organization Labels, or create a new one from the search text. */
function LabelPicker({ organizationId, labels, selected, onChange, onCreated, copy }: { organizationId: string; labels: Label[]; selected: string[]; onChange: (labelIds: string[]) => void; onCreated: (label: Label) => void; copy: PlannerMessages }) {
  const [query, setQuery] = useState("");
  const [failed, setFailed] = useState<string | null>(null);
  const searchId = useId();
  const trimmed = query.trim();
  const shown = labels.filter((label) => selected.includes(label.id) || matchesText(trimmed, label.name));
  const exact = labels.some((label) => normalizeText(label.name) === normalizeText(trimmed));
  const full = selected.length >= MAX_EVENT_LABELS;
  function toggle(labelId: string, on: boolean) {
    onChange(on ? [...selected, labelId] : selected.filter((item) => item !== labelId));
  }
  async function create() {
    setFailed(null);
    try {
      const label = await createLabel(organizationId, trimmed, LABEL_COLORS[labels.length % LABEL_COLORS.length]);
      onCreated(label);
      if (!selected.includes(label.id)) onChange([...selected, label.id]);
      setQuery("");
    } catch (error) {
      setFailed(error instanceof LimitReachedError ? copy.limitReached(error.maximum) : copy.saveFailed);
    }
  }
  return (
    <fieldset className="yc-label-picker flex flex-col gap-1.5">
      <legend>{copy.labels} <span className="text-xs font-normal text-ink-muted">{copy.labelCount(selected.length, MAX_EVENT_LABELS)}</span></legend>
      <label htmlFor={searchId}>{copy.findLabel}</label>
      <input id={searchId} type="search" maxLength={60} value={query} onChange={(event) => setQuery(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") { event.preventDefault(); if (trimmed && !exact && !full) void create(); } }} />
      {full ? <p className="m-0 mt-1 text-xs text-ink-muted" role="status">{copy.labelsFull(MAX_EVENT_LABELS)}</p> : null}
      {shown.length === 0 && !trimmed ? null : shown.length === 0 ? <p className="m-0 mt-1 text-xs text-ink-muted">{copy.noLabelMatch}</p> : null}
      <ul className="yc-label-options flex-row flex-wrap gap-x-3 gap-y-1">
        {shown.map((label) => (
          <li key={label.id}>
            <label><input type="checkbox" checked={selected.includes(label.id)} disabled={full && !selected.includes(label.id)} onChange={(event) => toggle(label.id, event.target.checked)} /> <span className="label-swatch inline-block size-[0.8em] rounded-full align-middle" style={{ background: label.color }} aria-hidden="true" /> {label.name}</label>
          </li>
        ))}
      </ul>
      {trimmed && !exact && !full ? <><button type="button" onClick={() => void create()}>{copy.createLabel(trimmed)}</button> <span className="text-xs font-normal text-ink-muted">{copy.labelsVisible}</span></> : null}
      {failed ? <p role="alert">{failed}</p> : null}
    </fieldset>
  );
}

/** Show-only checkboxes for Lanes, Categories, and Labels with live counts (replaces the Category legend). */
function BulkBar({ selecting, onSelecting, chosen, onSelectAll, onClear, lanes, categories, labels, noteId, onRun, copy }: { selecting: boolean; onSelecting: (value: boolean) => void; chosen: ReadonlySet<string>; onSelectAll: () => void; onClear: () => void; lanes: Lane[]; categories: YearclockCategory[]; labels: Label[]; noteId: string; onRun: (change: BulkAction, confirmLabel: string) => void; copy: PlannerMessages }) {
  const [laneId, setLaneId] = useState("");
  const [categoryId, setCategoryId] = useState("");
  const [labelId, setLabelId] = useState("");
  const ids = { lane: useId(), category: useId(), label: useId() };
  const none = chosen.size === 0;
  const lane = laneId || lanes[0]?.id || "";
  const label = labelId || labels[0]?.id || "";
  const row = "flex flex-wrap items-center gap-2";
  return (
    <section className="yc-bulk flex flex-col gap-3" aria-label={copy.bulk.title}>
      <div className={row}>
        <Button size="sm" variant={selecting ? "primary" : "secondary"} aria-pressed={selecting} onClick={() => onSelecting(!selecting)}>{copy.bulk.select}</Button>
        {selecting ? <span role="status" className="text-[13px] font-medium">{copy.bulk.count(chosen.size)}</span> : null}
      </div>
      {selecting ? (
        <div className="flex flex-col gap-3 rounded-[10px] border border-line bg-surface-subtle p-3">
          <p id={noteId} className="m-0 text-xs text-ink-muted">{copy.bulk.note}</p>
          <div className={row}>
            <Button size="sm" onClick={onSelectAll}>{copy.bulk.selectAllShown}</Button>
            <Button size="sm" variant="ghost" onClick={onClear} disabled={none}>{copy.bulk.clear}</Button>
          </div>
          <div className="yc-bulk-actions flex flex-col gap-2">
            <div className={row}>
              <label htmlFor={ids.lane} className="w-28 text-[13px] font-medium">{copy.bulk.moveTo}</label>
              <Select id={ids.lane} className="w-40" value={lane} onChange={(event) => setLaneId(event.target.value)}>{lanes.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</Select>
              <Button size="sm" disabled={none} onClick={() => onRun({ action: "move", lane_id: lane }, copy.bulk.move)}>{copy.bulk.move}</Button>
            </div>
            <div className={row}>
              <label htmlFor={ids.category} className="w-28 text-[13px] font-medium">{copy.bulk.setCategory}</label>
              <Select id={ids.category} className="w-40" value={categoryId} onChange={(event) => setCategoryId(event.target.value)}><option value="">{copy.none}</option>{categories.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</Select>
              <Button size="sm" disabled={none} onClick={() => onRun({ action: "categorize", category_id: categoryId || null }, copy.bulk.applyCategory)}>{copy.bulk.applyCategory}</Button>
            </div>
            {labels.length ? (
              <div className={row}>
                <label htmlFor={ids.label} className="w-28 text-[13px] font-medium">{copy.bulk.label}</label>
                <Select id={ids.label} className="w-40" value={label} onChange={(event) => setLabelId(event.target.value)}>{labels.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</Select>
                <Button size="sm" disabled={none} onClick={() => onRun({ action: "label", add_label_ids: [label] }, copy.bulk.addLabel)}>{copy.bulk.addLabel}</Button>
                <Button size="sm" variant="ghost" disabled={none} onClick={() => onRun({ action: "label", remove_label_ids: [label] }, copy.bulk.removeLabel)}>{copy.bulk.removeLabel}</Button>
              </div>
            ) : null}
            <div><Button size="sm" variant="ghost-danger" disabled={none} onClick={() => onRun({ action: "delete" }, copy.delete)}>{copy.bulk.deleteSelected}</Button></div>
          </div>
        </div>
      ) : null}
    </section>
  );
}

function FilterPanel({ events, filters, onChange, lanes, categories, labels, copy }: { events: YearclockEvent[]; filters: FilterState; onChange: (filters: FilterState) => void; lanes: Lane[]; categories: YearclockCategory[]; labels: Label[]; copy: PlannerMessages["filter"] }) {
  const hidden = events.length - applyFilters(events, filters).length;
  const hasUncategorized = events.some((event) => !event.category_id);
  const [ownCategories, ...linkedGroups] = categoryGroups(categories);
  const categoryOption = (category: YearclockCategory) => ({ id: category.id, name: category.name, color: category.color ?? "#4a5a67" });
  const sections: Array<{ key: string; dimension: Dimension; title: string; options: Array<{ id: string; name: string; color?: string | null }> }> = [
    { key: "lanes", dimension: "lanes", title: copy.lanes, options: lanes.map((lane) => ({ id: lane.id, name: lane.name })) },
    { key: "categories", dimension: "categories", title: copy.categories, options: [...ownCategories.items.map(categoryOption), ...(hasUncategorized || filters.categories.includes(NO_CATEGORY) ? [{ id: NO_CATEGORY, name: copy.noCategory }] : [])] },
    ...linkedGroups.map((group, index) => ({ key: `linked-${index}`, dimension: "categories" as const, title: copy.linkedCategories(group.source ?? ""), options: group.items.map(categoryOption) })),
    { key: "labels", dimension: "labels", title: copy.labels, options: labels.map((label) => ({ id: label.id, name: label.name, color: label.color })) },
  ];
  return (
    <section className="yc-filters flex flex-col gap-3" aria-label={copy.title}>
      <p className="m-0 text-xs text-ink-muted">{copy.description}</p>
      <p role="status" className="yc-filter-status m-0 flex flex-wrap items-center gap-2 text-[13px]">
        {isFiltering(filters) ? <>{copy.hidden(hidden)} <Button size="sm" onClick={() => onChange({ lanes: [], categories: [], labels: [] })}>{copy.showAll}</Button></> : null}
      </p>
      <div className="yc-filter-groups flex flex-col gap-4">
        {sections.filter((section) => section.options.length > 0).map((section) => {
          const counts = facetCounts(events, filters, section.dimension);
          return (
            <fieldset key={section.key} className="m-0 flex flex-col gap-1 border-0 p-0">
              <legend className="mb-1 p-0 text-xs font-semibold uppercase tracking-wide text-ink-muted">{section.title}</legend>
              <ul className="m-0 flex list-none flex-col p-0">
                {section.options.map((option) => (
                  <li key={option.id}>
                    <Choice checked={filters[section.dimension].includes(option.id)} onChange={(event) => onChange(toggle(filters, section.dimension, option.id, event.target.checked))} label={<span className="inline-flex items-center gap-1.5">{option.color ? <span className="inline-block size-3 rounded-[3px]" style={{ background: option.color }} aria-hidden="true" /> : null}{copy.option(option.name, counts.get(option.id) ?? 0)}</span>} />
                  </li>
                ))}
              </ul>
            </fieldset>
          );
        })}
      </div>
    </section>
  );
}

/** Search the whole Yearclock; choosing a result moves the Planning Window to it and opens it. */
function SearchPanel({ organizationId, yearclockId, locale, lanes, categories, labels, copy, onChoose }: { organizationId: string; yearclockId: string; locale: Locale; lanes: Lane[]; categories: YearclockCategory[]; labels: Label[]; copy: PlannerMessages["search"]; onChoose: (event: YearclockEvent) => void }) {
  const [query, setQuery] = useState("");
  const [result, setResult] = useState<SearchResult | null>(null);
  const [failed, setFailed] = useState(false);
  const [busy, setBusy] = useState(false);
  const fieldId = useId();
  const tooShort = query.trim().length < 2;
  async function load(offset: number) {
    setFailed(false);
    setBusy(true);
    try {
      const page = await searchYearclock(organizationId, yearclockId, query.trim(), offset);
      setResult((current) => (offset > 0 && current ? { ...page, items: [...current.items, ...page.items] } : page));
    } catch {
      setFailed(true);
    } finally {
      setBusy(false);
    }
  }
  const laneName = (laneId: string) => lanes.find((lane) => lane.id === laneId)?.name ?? "";
  const categoryName = (categoryId: string | null) => categories.find((category) => category.id === categoryId)?.name;
  const labelNames = (event: YearclockEvent) => (event.label_ids ?? []).map((labelId) => labels.find((label) => label.id === labelId)?.name).filter(Boolean).join(", ");
  return (
    <div className="yc-search relative min-w-0 flex-1 basis-64">
      <form role="search" aria-label={copy.label} className="flex flex-wrap items-center gap-2" onSubmit={(event) => { event.preventDefault(); if (!tooShort) void load(0); }}>
        <label htmlFor={fieldId} className="sr-only">{copy.field}</label>
        <span className="relative min-w-48 flex-1">
          <Search size={14} aria-hidden="true" className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-ink-muted" />
          <TextInput id={fieldId} type="search" className="w-full pl-8" placeholder={copy.field} maxLength={200} value={query} onChange={(event) => setQuery(event.target.value)} />
        </span>
        <Button type="submit" size="sm" disabled={tooShort || busy}>{copy.submit}</Button>
        {query.trim().length === 1 ? <span className="text-xs text-ink-muted">{copy.tooShort}</span> : null}
      </form>
      <p role="status" className="m-0 text-[13px] text-ink-muted">{failed ? copy.failed : result ? (result.total ? copy.results(result.total) : copy.empty) : ""}</p>
      {result && result.items.length ? (
        <div className="mt-2 flex max-h-80 flex-col gap-2 overflow-y-auto rounded-[10px] border border-line bg-surface p-2">
          {result.includes_recurring ? <p className="m-0 px-2 text-xs text-ink-muted">{copy.recurringNote}</p> : null}
          <ol className="yc-search-results m-0 flex list-none flex-col p-0">
            {result.items.map((event) => (
              <li key={event.id}>
                <button type="button" className="w-full cursor-pointer rounded-[6px] border-0 bg-transparent px-2 py-1.5 text-left text-[13px] hover:bg-surface-sunken" onClick={() => { onChoose(event); setResult(null); setQuery(""); }}>
                  <span className="text-ink-muted">{dateLabel(event, locale)}</span> <strong>{event.title}</strong>
                  <span className="yc-summary-meta text-ink-muted"> — {laneName(event.lane_id)}{categoryName(event.category_id) ? ` · ${categoryName(event.category_id)}` : ""}{labelNames(event) ? ` · ${labelNames(event)}` : ""}</span>
                </button>
              </li>
            ))}
          </ol>
          {result.next_offset !== null ? <div><Button size="sm" disabled={busy} onClick={() => void load(result.next_offset!)}>{copy.more}</Button></div> : null}
        </div>
      ) : null}
    </div>
  );
}

const lengthKey = (yearclockId: string) => `yearclock.length.${yearclockId}`;

/** The user's chosen Planning Window length for this Yearclock, 12 months when none is stored or storage is blocked. */
function loadLength(yearclockId: string): WindowLength {
  try {
    const stored = Number(globalThis.localStorage?.getItem(lengthKey(yearclockId)));
    return (WINDOW_LENGTHS as readonly number[]).includes(stored) ? (stored as WindowLength) : 12;
  } catch {
    return 12;
  }
}

function saveLength(yearclockId: string, length: WindowLength): void {
  try {
    if (length === 12) globalThis.localStorage?.removeItem(lengthKey(yearclockId));
    else globalThis.localStorage?.setItem(lengthKey(yearclockId), String(length));
  } catch {
    // Blocked storage: the length is simply not remembered.
  }
}

/** Shared Yearclock layout: the month its planning year starts (Yearclock V2). */
function PlanAgainPanel({ organizationId, yearclockId, seasonNow, lanes, categories, locale, copy, onCreated }: { organizationId: string; yearclockId: string; seasonNow: string; lanes: Lane[]; categories: YearclockCategory[]; locale: Locale; copy: PlannerMessages; onCreated: () => void }) {
  const text = copy.planAgainPanel;
  const seasons = [-12, 0, 12].map((months) => addMonths(seasonNow, months));
  const [season, setSeason] = useState(seasonNow);
  const [laneIds, setLaneIds] = useState<string[] | null>(null);
  const [categoryIds, setCategoryIds] = useState<string[] | null>(null);
  const [uncategorized, setUncategorized] = useState(true);
  const [rule, setRule] = useState<PlanAgainInput["date_rule"]>("same_date");
  const [preview, setPreview] = useState<PlanAgainResult | null>(null);
  const [notice, setNotice] = useState<{ ok: boolean; text: string } | null>(null);
  const seasonId = useId();
  const chosenLanes = laneIds ?? lanes.map((lane) => lane.id);
  const chosenCategories = categoryIds ?? categories.map((category) => category.id);
  const input: PlanAgainInput = { season_start: season, lane_ids: chosenLanes, category_ids: chosenCategories, include_uncategorized: uncategorized, date_rule: rule };
  const range = (start: string) => { const window = planningWindow(start, 12); return [formatDay(window.start, locale), formatDay(window.end, locale)] as const; };
  const changed = (apply: () => void) => { apply(); setPreview(null); setNotice(null); };
  const toggle = (list: string[], id: string, on: boolean) => (on ? [...list, id] : list.filter((item) => item !== id));
  async function send(dryRun: boolean) {
    setNotice(null);
    try {
      const result = await planAgain(organizationId, yearclockId, input, dryRun);
      if (dryRun) { setPreview(result); return; }
      setPreview(null);
      setNotice({ ok: true, text: text.done(result.to_create) });
      onCreated();
    } catch (error) {
      setPreview(null);
      setNotice({ ok: false, text: error instanceof LimitReachedError ? text.limit(error.maximum) : copy.saveFailed });
    }
  }
  const target = range(addMonths(season, 12));
  return (
    <section aria-label={text.title}>
      <h5>{text.title}</h5>
      <p>
        <label htmlFor={seasonId}>{text.season}</label>{" "}
        <select id={seasonId} value={season} onChange={(event) => changed(() => setSeason(event.target.value))}>
          {seasons.map((start) => <option key={start} value={start}>{text.seasonOption(...range(start))}</option>)}
        </select>
      </p>
      <fieldset>
        <legend>{text.lanes}</legend>
        {lanes.map((lane) => <label key={lane.id}><input type="checkbox" checked={chosenLanes.includes(lane.id)} onChange={(event) => changed(() => setLaneIds(toggle(chosenLanes, lane.id, event.target.checked)))} /> {lane.name}</label>)}
      </fieldset>
      <fieldset>
        <legend>{text.categories}</legend>
        {categories.map((category) => <label key={category.id}><input type="checkbox" checked={chosenCategories.includes(category.id)} onChange={(event) => changed(() => setCategoryIds(toggle(chosenCategories, category.id, event.target.checked)))} /> {category.name}</label>)}
        <label><input type="checkbox" checked={uncategorized} onChange={(event) => changed(() => setUncategorized(event.target.checked))} /> {text.noCategory}</label>
      </fieldset>
      <fieldset>
        <legend>{text.rule}</legend>
        <label><input type="radio" name={`${seasonId}-rule`} checked={rule === "same_date"} onChange={() => changed(() => setRule("same_date"))} /> {text.sameDate}</label>
        <label><input type="radio" name={`${seasonId}-rule`} checked={rule === "same_weekday"} onChange={() => changed(() => setRule("same_weekday"))} /> {text.sameWeekday}</label>
        <p className="m-0 mt-1 text-xs text-ink-muted">{text.ruleHint}</p>
      </fieldset>
      <p><button type="button" disabled={!chosenLanes.length} onClick={() => void send(true)}>{text.preview}</button></p>
      {preview ? (
        <div role="status">
          <p>{preview.limit_exceeded ? text.limit(preview.maximum) : preview.to_create ? text.result(preview.to_create, preview.skipped_existing, ...target) : text.nothing(preview.skipped_existing)}</p>
          {!preview.limit_exceeded && preview.to_create ? <button type="button" className="primary-button" onClick={() => void send(false)}>{text.create(preview.to_create)}</button> : null}
        </div>
      ) : null}
      {notice ? <p role={notice.ok ? "status" : "alert"}>{notice.text}</p> : null}
    </section>
  );
}

function LayoutManager({ organizationId, yearclock, locale, copy, onChanged }: { organizationId: string; yearclock: WorkspaceYearclock; locale: Locale; copy: PlannerMessages; onChanged: () => void }) {
  const [startMonth, setStartMonth] = useState(yearclock.start_month ?? 1);
  const [weeks, setWeeks] = useState(Boolean(yearclock.show_week_ring));
  const [quarters, setQuarters] = useState(Boolean(yearclock.show_quarter_ring));
  useEffect(() => { setStartMonth(yearclock.start_month ?? 1); setWeeks(Boolean(yearclock.show_week_ring)); setQuarters(Boolean(yearclock.show_quarter_ring)); }, [yearclock.start_month, yearclock.show_week_ring, yearclock.show_quarter_ring, yearclock.version]);
  const [notice, setNotice] = useState<{ ok: boolean; text: string } | null>(null);
  const monthName = new Intl.DateTimeFormat(locale === "fi" ? "fi-FI" : "en-GB", { month: "long", timeZone: "UTC" });
  const startId = useId();
  const dirty = startMonth !== (yearclock.start_month ?? 1) || weeks !== Boolean(yearclock.show_week_ring) || quarters !== Boolean(yearclock.show_quarter_ring);
  async function save() {
    setNotice(null);
    try {
      await updateLayout(organizationId, yearclock, { start_month: startMonth, show_week_ring: weeks, show_quarter_ring: quarters });
      setNotice({ ok: true, text: copy.layoutSaved });
    } catch (error) {
      setNotice({ ok: false, text: error instanceof ConflictError ? copy.conflict : copy.saveFailed });
    }
    onChanged();
  }
  return (
    <section aria-label={copy.layout}>
      <h5>{copy.layout}</h5>
      <label htmlFor={startId}>{copy.yearStart}</label>{" "}
      <select id={startId} value={startMonth} onChange={(event) => setStartMonth(Number(event.target.value))}>
        {Array.from({ length: 12 }, (_, index) => <option key={index + 1} value={index + 1}>{monthName.format(new Date(Date.UTC(2026, index, 1)))}</option>)}
      </select>{" "}
      <label><input type="checkbox" checked={weeks} onChange={(event) => setWeeks(event.target.checked)} /> {copy.weekRing}</label>{" "}
      <label><input type="checkbox" checked={quarters} onChange={(event) => setQuarters(event.target.checked)} /> {copy.quarterRing}</label>{" "}
      <button type="button" disabled={!dirty} onClick={() => void save()}>{copy.saveLayout}</button>
      {notice ? <p role={notice.ok ? "status" : "alert"}>{notice.text}</p> : null}
    </section>
  );
}
