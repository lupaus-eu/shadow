import { Fragment, useEffect, useMemo, useState } from "react";
import type { SubmitEvent } from "react";
import type {
  GraphEdgeDto,
  GraphNodeDto,
  GraphNodeUpdateRequest,
  NodeTypeMetadataDto,
  EdgeTypeMetadataDto
} from "../../api/orgTwinStructure";
import {
  createTimeserie,
  deleteTimeserie,
  fetchTimeserieExists,
  fetchTimeserieSummaries,
  updateTimeserieShortName
} from "../../api/timeseries";
import type {
  TimeserieCreateRequest,
  TimeserieTimeUnit,
  TimeserieValueUnit
} from "../../api/timeseries";
import Alert from "../../components/Alert";
import SearchableSelect from "../../components/SearchableSelect";

const TIME_UNIT_OPTIONS: TimeserieTimeUnit[] = ["day", "week", "month", "year"];
const VALUE_UNIT_OPTIONS: TimeserieValueUnit[] = ["number", "string", "boolean"];
const LINK_PLACEHOLDER = "Select existing timeseries id";

type TimeserieSlot = "primary" | "secondary";

type EffectiveTimeserieItem = {
  slot: TimeserieSlot;
  label: string;
  id: string;
  inheritedId: string;
  source: "node" | "type" | "none";
  // A saved node link without a pending dropdown selection can be unlinked.
  canUnlink: boolean;
};

type TimeserieOption = { id: string; name: string };

// While loading, the state keeps the panel's own creates and deletes to apply to the list.
type TimeserieOptionsState =
  | { status: "loading"; created: TimeserieOption[]; deletedIds: string[] }
  | { status: "ready"; items: TimeserieOption[] }
  | { status: "error" };

type ExistenceStatus =
  | { state: "loading" }
  | { state: "exists"; shortName: string; shortNameEditable: boolean }
  | { state: "missing" }
  | { state: "error"; message: string };

function messageFromError(error: unknown): string {
  return error instanceof Error ? error.message : "Unknown error";
}

function trimmed(value: string | null | undefined): string {
  return value?.trim() ?? "";
}

function inputValueToPayload(value: string): string | null {
  const nextValue = value.trim();
  return nextValue || null;
}

function uniqueValues(values: string[]): string[] {
  return values.filter((value, index) => value && values.indexOf(value) === index);
}

function withOption(items: TimeserieOption[], option: TimeserieOption): TimeserieOption[] {
  return items.some((item) => item.id === option.id) ? items : [...items, option];
}

function withoutOption(items: TimeserieOption[], timeserieId: string): TimeserieOption[] {
  return items.filter((item) => item.id !== timeserieId);
}

function slotLinkPatch(slot: TimeserieSlot, timeserieId: string | null): GraphNodeUpdateRequest {
  return slot === "primary" ? { timeserieId } : { timeserieSecondaryId: timeserieId };
}

// The effective id is the pending dropdown selection, else the saved node link, else the type default.
function effectiveItem(
  slot: TimeserieSlot,
  label: string,
  selection: string,
  linkedId: string,
  inheritedId: string
): EffectiveTimeserieItem {
  const nodeId = selection || linkedId;
  return {
    slot,
    label,
    id: nodeId || inheritedId,
    inheritedId,
    source: nodeId ? "node" : inheritedId ? "type" : "none",
    canUnlink: Boolean(linkedId) && !selection
  };
}

function statusLabel(status: ExistenceStatus | undefined, id: string): string {
  if (!id) return "No id";
  if (!status || status.state === "loading") return "Checking...";
  if (status.state === "exists") return "Exists";
  if (status.state === "missing") return "Missing";
  return "Error";
}

function statusClass(status: ExistenceStatus | undefined, id: string): string {
  if (!id) return "badge badge--neutral";
  if (!status || status.state === "loading") return "badge badge--neutral";
  if (status.state === "exists") return "badge badge--accent";
  if (status.state === "missing") return "badge badge--neutral";
  return "badge badge--neutral";
}

function displayNodeLabel(node: GraphNodeDto, nodeTypes: NodeTypeMetadataDto[]): string {
  const nodeType = nodeTypes.find((item) => item.id === node.nodeTypeId);
  return `${node.name} (${nodeType?.displayName ?? node.nodeTypeId})`;
}

function hasRelationshipEdgeTypeIds(edgeTypes: EdgeTypeMetadataDto[]): Set<string> {
  return new Set(
    edgeTypes
      .filter((edgeType) => trimmed(edgeType.displayName).toLowerCase() === "has")
      .map((edgeType) => edgeType.id)
  );
}

function matchingSourceNodes(
  targetNodeId: string,
  edges: GraphEdgeDto[],
  nodesById: Map<string, GraphNodeDto>,
  hasEdgeTypeIds: Set<string>
): GraphNodeDto[] {
  const sourceNodesById = new Map<string, GraphNodeDto>();
  for (const edge of edges) {
    if (edge.targetNodeId === targetNodeId && hasEdgeTypeIds.has(edge.edgeTypeId)) {
      const sourceNode = nodesById.get(edge.sourceNodeId);
      if (sourceNode) sourceNodesById.set(sourceNode.id, sourceNode);
    }
  }
  return [...sourceNodesById.values()];
}

function ruleLineValue(
  candidates: GraphNodeDto[],
  nodeTypes: NodeTypeMetadataDto[],
  singularFallback: string,
  pluralFallback: string
): string {
  if (candidates.length === 1) return displayNodeLabel(candidates[0], nodeTypes);
  return candidates.length === 0 ? singularFallback : pluralFallback;
}

function ruleLinesForNode(props: {
  node: GraphNodeDto;
  nodes: GraphNodeDto[];
  edges: GraphEdgeDto[];
  nodeTypes: NodeTypeMetadataDto[];
  edgeTypes: EdgeTypeMetadataDto[];
}): string[] {
  const nodesById = new Map(props.nodes.map((node) => [node.id, node]));
  const hasEdgeTypeIds = hasRelationshipEdgeTypeIds(props.edgeTypes);
  const goalCandidates = matchingSourceNodes(props.node.id, props.edges, nodesById, hasEdgeTypeIds);
  const goalLineValue = ruleLineValue(
    goalCandidates,
    props.nodeTypes,
    "No linked goal",
    "Multiple linked goals"
  );
  const organisationCandidates =
    goalCandidates.length === 1
      ? matchingSourceNodes(goalCandidates[0].id, props.edges, nodesById, hasEdgeTypeIds)
      : [];
  const organisationLineValue = ruleLineValue(
    organisationCandidates,
    props.nodeTypes,
    goalCandidates.length === 1
      ? "No linked organisation node"
      : "No unambiguous linked organisation node",
    "Multiple linked organisation nodes"
  );

  return [`Measured by from ${goalLineValue}`, `Has goal from ${organisationLineValue}`];
}

export default function TimeseriePanel(props: {
  orgId: string;
  scenarioId: string;
  node: GraphNodeDto;
  nodeType: NodeTypeMetadataDto | undefined;
  nodes: GraphNodeDto[];
  edges: GraphEdgeDto[];
  nodeTypes: NodeTypeMetadataDto[];
  edgeTypes: EdgeTypeMetadataDto[];
  saving: boolean;
  disabled?: boolean;
  onUpdateLinks: (payload: GraphNodeUpdateRequest) => Promise<void>;
  onTimeserieDeleted: (timeserieId: string) => void;
}) {
  const [primarySelection, setPrimarySelection] = useState("");
  const [secondarySelection, setSecondarySelection] = useState("");
  const [timeseriesOptions, setTimeseriesOptions] = useState<TimeserieOptionsState>({
    status: "loading",
    created: [],
    deletedIds: []
  });
  const [optionsError, setOptionsError] = useState("");
  const [linkError, setLinkError] = useState("");
  const [createIdDrafts, setCreateIdDrafts] = useState<
    Partial<Record<TimeserieSlot, { baseId: string; value: string }>>
  >({});
  // A timeserie each slot created whose link has not succeeded; the create form may unmount
  // while a selection hides it, so the panel keeps this for retrying only the link.
  const [unlinkedCreatedIds, setUnlinkedCreatedIds] = useState<Record<TimeserieSlot, string>>({
    primary: "",
    secondary: ""
  });
  const [existenceById, setExistenceById] = useState<Record<string, ExistenceStatus>>({});
  const [panelError, setPanelError] = useState("");
  const [busySlot, setBusySlot] = useState<TimeserieSlot | null>(null);
  const [confirmingDeleteId, setConfirmingDeleteId] = useState<string | null>(null);
  const [editingShortNameId, setEditingShortNameId] = useState<string | null>(null);
  const [shortNameDraft, setShortNameDraft] = useState("");

  const effectiveItems = useMemo<EffectiveTimeserieItem[]>(
    () => [
      effectiveItem(
        "primary",
        "Primary",
        primarySelection,
        trimmed(props.node.timeserieId),
        trimmed(props.nodeType?.timeserieId)
      ),
      effectiveItem(
        "secondary",
        "Secondary",
        secondarySelection,
        trimmed(props.node.timeserieSecondaryId),
        trimmed(props.nodeType?.timeserieSecondaryId)
      )
    ],
    [
      primarySelection,
      props.node.timeserieId,
      props.node.timeserieSecondaryId,
      props.nodeType?.timeserieId,
      props.nodeType?.timeserieSecondaryId,
      secondarySelection
    ]
  );

  const effectiveIds = useMemo(
    () => uniqueValues(effectiveItems.map((item) => item.id)),
    [effectiveItems]
  );
  const effectiveIdSignature = effectiveIds.join("\n");
  const formDisabled = props.disabled || props.saving;
  const actionsDisabled = formDisabled || busySlot !== null;
  const linkSelectDisabled = formDisabled || timeseriesOptions.status !== "ready";
  const linkOptions = useMemo(
    () =>
      timeseriesOptions.status === "ready"
        ? [...timeseriesOptions.items]
            .sort((left, right) => left.id.localeCompare(right.id))
            .map((item) => ({ value: item.id, label: `${item.id} – ${item.name}` }))
        : [],
    [timeseriesOptions]
  );
  // The existence check has no name, so the cards take it from the timeseries list.
  const timeserieNames = useMemo(
    () =>
      new Map(
        timeseriesOptions.status === "ready"
          ? timeseriesOptions.items.map((item) => [item.id, item.name])
          : []
      ),
    [timeseriesOptions]
  );
  const ruleLines = useMemo(
    () =>
      ruleLinesForNode({
        node: props.node,
        nodes: props.nodes,
        edges: props.edges,
        nodeTypes: props.nodeTypes,
        edgeTypes: props.edgeTypes
      }),
    [props.edgeTypes, props.edges, props.node, props.nodeTypes, props.nodes]
  );
  const nodeSourceLabel = displayNodeLabel(props.node, props.nodeTypes);

  useEffect(() => {
    const ids = effectiveIdSignature ? effectiveIdSignature.split("\n") : [];
    if (ids.length === 0) return;

    const ac = new AbortController();

    for (const id of ids) {
      void fetchTimeserieExists(props.orgId, props.scenarioId, id, ac.signal)
        .then((response) => {
          if (!response.exists) {
            setExistenceById((current) => ({
              ...current,
              [id]: { state: "missing" }
            }));
            return;
          }

          setExistenceById((current) => ({
            ...current,
            [id]: {
              state: "exists",
              shortName: response.shortName,
              shortNameEditable: response.shortNameEditable !== false
            }
          }));
        })
        .catch((error) => {
          const err = error as { name?: string };
          if (err.name === "AbortError") return;
          setExistenceById((current) => ({
            ...current,
            [id]: { state: "error", message: messageFromError(error) }
          }));
        });
    }

    return () => ac.abort();
  }, [effectiveIdSignature, props.orgId, props.scenarioId]);

  useEffect(() => {
    if (!props.scenarioId) return;

    const ac = new AbortController();
    // Only ids and names are needed, so the values-free list is enough.
    fetchTimeserieSummaries(props.orgId, props.scenarioId, ac.signal)
      .then((timeseries) => {
        const loaded = timeseries.map((item) => ({ id: item.id, name: item.name }));
        setTimeseriesOptions((current) => {
          if (current.status !== "loading") return { status: "ready", items: loaded };
          // The list may predate timeseries created or deleted here while it loaded,
          // so those replace or remove its entries with the same id.
          const localIds = new Set([
            ...current.deletedIds,
            ...current.created.map((item) => item.id)
          ]);
          const remaining = loaded.filter((item) => !localIds.has(item.id));
          return { status: "ready", items: [...remaining, ...current.created] };
        });
      })
      .catch((error) => {
        const err = error as { name?: string };
        if (err.name === "AbortError") return;
        setTimeseriesOptions({ status: "error" });
        setOptionsError(messageFromError(error));
      });

    return () => ac.abort();
  }, [props.orgId, props.scenarioId]);

  function addOption(option: TimeserieOption) {
    setTimeseriesOptions((current) => {
      if (current.status === "ready") {
        return { status: "ready", items: withOption(current.items, option) };
      }
      if (current.status === "loading") {
        return {
          status: "loading",
          created: withOption(current.created, option),
          deletedIds: current.deletedIds.filter((id) => id !== option.id)
        };
      }
      return current;
    });
  }

  function removeOption(timeserieId: string) {
    setTimeseriesOptions((current) => {
      if (current.status === "ready") {
        return { status: "ready", items: withoutOption(current.items, timeserieId) };
      }
      if (current.status === "loading") {
        return {
          status: "loading",
          created: withoutOption(current.created, timeserieId),
          deletedIds: [...current.deletedIds, timeserieId]
        };
      }
      return current;
    });
  }

  function createIdFor(item: EffectiveTimeserieItem): string {
    const draft = createIdDrafts[item.slot];
    return draft && draft.baseId === item.id ? draft.value : item.id;
  }

  async function saveLinks(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    setLinkError("");
    const payload: GraphNodeUpdateRequest = {};
    if (primarySelection) payload.timeserieId = primarySelection;
    if (secondarySelection) payload.timeserieSecondaryId = secondarySelection;

    try {
      await props.onUpdateLinks(payload);
      // Saving the current link does not remount the panel, so reset the dropdowns here.
      setPrimarySelection("");
      setSecondarySelection("");
    } catch (error) {
      setLinkError(messageFromError(error));
    }
  }

  async function unlink(item: EffectiveTimeserieItem) {
    try {
      setPanelError("");
      setBusySlot(item.slot);
      await props.onUpdateLinks(slotLinkPatch(item.slot, null));
    } catch (error) {
      setPanelError(messageFromError(error));
    } finally {
      setBusySlot(null);
    }
  }

  // The create form shows create and link errors, so these rethrow without a panel error.
  async function createSlotTimeserie(
    item: EffectiveTimeserieItem,
    payload: TimeserieCreateRequest
  ) {
    try {
      setBusySlot(item.slot);
      await createTimeserie(props.orgId, props.scenarioId, payload);
      if (payload.id !== item.inheritedId) {
        setUnlinkedCreatedIds((current) => ({ ...current, [item.slot]: payload.id }));
      }
      setExistenceById((current) => ({
        ...current,
        [payload.id]: {
          state: "exists",
          shortName: payload.shortName?.trim() ?? "",
          shortNameEditable: true
        }
      }));
      addOption({ id: payload.id, name: payload.name });
    } finally {
      setBusySlot(null);
    }
  }

  async function linkSlotTimeserie(slot: TimeserieSlot, timeserieId: string) {
    try {
      setBusySlot(slot);
      await props.onUpdateLinks(slotLinkPatch(slot, timeserieId));
    } finally {
      setBusySlot(null);
    }
  }

  async function confirmDelete(item: EffectiveTimeserieItem) {
    const timeserieId = item.id;
    try {
      setPanelError("");
      setBusySlot(item.slot);
      await deleteTimeserie(props.orgId, props.scenarioId, timeserieId);
      setExistenceById((current) => ({
        ...current,
        [timeserieId]: { state: "missing" }
      }));
      removeOption(timeserieId);
      setPrimarySelection((current) => (current === timeserieId ? "" : current));
      setSecondarySelection((current) => (current === timeserieId ? "" : current));
      setUnlinkedCreatedIds((current) => ({
        primary: current.primary === timeserieId ? "" : current.primary,
        secondary: current.secondary === timeserieId ? "" : current.secondary
      }));
      props.onTimeserieDeleted(timeserieId);
      setConfirmingDeleteId(null);
    } catch (error) {
      setPanelError(messageFromError(error));
    } finally {
      setBusySlot(null);
    }
  }

  async function saveShortName(item: EffectiveTimeserieItem) {
    const timeserieId = item.id;
    try {
      setPanelError("");
      setBusySlot(item.slot);
      const updated = await updateTimeserieShortName(
        props.orgId,
        props.scenarioId,
        timeserieId,
        inputValueToPayload(shortNameDraft)
      );
      setExistenceById((current) => ({
        ...current,
        [timeserieId]: {
          state: "exists",
          shortName: updated.shortName ?? "",
          shortNameEditable: updated.shortNameEditable !== false
        }
      }));
      setEditingShortNameId(null);
    } catch (error) {
      setPanelError(messageFromError(error));
    } finally {
      setBusySlot(null);
    }
  }

  return (
    <div className="structure-editor-stack">
      <section className="detail-card" aria-labelledby="structure-timeserie-link-title">
        <div className="detail-card__header">
          <h2 id="structure-timeserie-link-title" className="section-title">
            Link to existing timeserie(s)
          </h2>
        </div>

        {optionsError ? (
          <Alert
            variant="danger"
            role="alert"
            title="Timeserie list error"
            message={optionsError}
            onDismiss={() => setOptionsError("")}
          />
        ) : null}

        <form onSubmit={saveLinks}>
          {(
            [
              ["primary", "Primary", primarySelection, setPrimarySelection],
              ["secondary", "Secondary", secondarySelection, setSecondarySelection]
            ] as const
          ).map(([slot, label, selection, setSelection]) => (
            <div key={slot} className="form-row">
              <label className="form-label" htmlFor={`structure-timeserie-${slot}`}>
                {label} link
              </label>
              <div className="timeserie-link-control">
                <SearchableSelect
                  id={`structure-timeserie-${slot}`}
                  options={linkOptions}
                  value={selection}
                  onChange={setSelection}
                  placeholder={LINK_PLACEHOLDER}
                  searchLabel={`Search ${slot} timeseries`}
                  disabled={linkSelectDisabled}
                />
                <button
                  className="btn btn--secondary"
                  type="button"
                  aria-label={`Clear ${slot} link selection`}
                  disabled={linkSelectDisabled || !selection}
                  onClick={() => {
                    setSelection("");
                    // The button disables itself, so focus returns to the dropdown.
                    document.getElementById(`structure-timeserie-${slot}`)?.focus();
                  }}
                >
                  Clear
                </button>
              </div>
            </div>
          ))}
          <div className="form-actions">
            <button
              className="btn btn--primary"
              type="submit"
              disabled={formDisabled || (!primarySelection && !secondarySelection)}
            >
              {props.saving ? "Saving..." : "Save link(s)"}
            </button>
          </div>
          {linkError ? (
            <Alert
              variant="danger"
              role="alert"
              message={linkError}
              onDismiss={() => setLinkError("")}
            />
          ) : null}
        </form>

        {props.nodeType?.timeserieIdRule ? (
          <dl className="detail-meta">
            <div className="detail-meta__row">
              <dt>Rule</dt>
              <dd>
                {ruleLines.map((line, index) => (
                  <Fragment key={line}>
                    {index > 0 ? <br /> : null}
                    {line}
                  </Fragment>
                ))}
              </dd>
            </div>
          </dl>
        ) : null}
      </section>

      <section className="detail-card" aria-labelledby="structure-timeserie-edit-title">
        <div className="detail-card__header">
          <h2 id="structure-timeserie-edit-title" className="section-title">
            Create/edit timeserie(s)
          </h2>
        </div>

        {panelError ? (
          <Alert
            variant="danger"
            role="alert"
            title="Timeserie error"
            message={panelError}
            onDismiss={() => setPanelError("")}
          />
        ) : null}

        <div className="timeserie-status-list">
          {effectiveItems.map((item) => {
            const status = item.id ? existenceById[item.id] : undefined;
            const isBusy = busySlot === item.slot;
            const isDeleting = confirmingDeleteId === item.id;
            const showCreateForm = !item.id || status?.state === "missing";
            const createIdPrefix = `structure-${item.slot}-timeserie`;
            const timeserieName =
              status?.state === "exists" ? timeserieNames.get(item.id) : undefined;

            return (
              <section
                key={item.slot}
                className="timeserie-status-card"
                aria-label={`${item.label} timeserie`}
              >
                <div className="timeserie-status-card__header">
                  <div
                    className={
                      showCreateForm
                        ? "timeserie-status-card__title timeserie-status-card__title--editable"
                        : "timeserie-status-card__title"
                    }
                  >
                    <h3>{item.label}</h3>
                    {showCreateForm ? (
                      <>
                        <label className="visually-hidden" htmlFor={`${createIdPrefix}-id`}>
                          {item.label} timeserie id
                        </label>
                        {/* Shown in the card header, but submitted with the create form below. */}
                        <input
                          id={`${createIdPrefix}-id`}
                          className="input"
                          form={`${createIdPrefix}-form`}
                          required
                          value={createIdFor(item)}
                          onChange={(event) => {
                            const value = event.target.value;
                            setCreateIdDrafts((current) => ({
                              ...current,
                              [item.slot]: { baseId: item.id, value }
                            }));
                          }}
                          disabled={actionsDisabled}
                        />
                      </>
                    ) : (
                      <code className="metadata-code">{item.id}</code>
                    )}
                  </div>
                  <span className={statusClass(status, item.id)}>
                    {statusLabel(status, item.id)}
                  </span>
                </div>
                {item.source !== "none" || status?.state === "exists" ? (
                  <dl className="detail-meta">
                    {timeserieName ? (
                      <div className="detail-meta__row">
                        <dt>Name</dt>
                        <dd>{timeserieName}</dd>
                      </div>
                    ) : null}
                    {item.source !== "none" ? (
                      <div className="detail-meta__row">
                        <dt>Source</dt>
                        <dd>{item.source === "node" ? nodeSourceLabel : "Type default"}</dd>
                      </div>
                    ) : null}
                    {item.inheritedId && item.source === "node" ? (
                      <div className="detail-meta__row">
                        <dt>Default</dt>
                        <dd>{item.inheritedId}</dd>
                      </div>
                    ) : null}
                    {status?.state === "exists" ? (
                      <div className="detail-meta__row">
                        <dt>Short name</dt>
                        <dd>{status.shortName || "Not set"}</dd>
                      </div>
                    ) : null}
                  </dl>
                ) : null}
                {status?.state === "exists" || item.canUnlink ? (
                  <div className="form-actions">
                    {status?.state !== "exists" ? null : status.shortNameEditable ? (
                      editingShortNameId === item.id ? (
                        <>
                          <label className="visually-hidden" htmlFor={`short-name-${item.slot}`}>
                            Short name for {item.label}
                          </label>
                          <input
                            id={`short-name-${item.slot}`}
                            className="input"
                            value={shortNameDraft}
                            onChange={(event) => setShortNameDraft(event.target.value)}
                            disabled={isBusy || formDisabled}
                          />
                          <button
                            className="btn btn--secondary"
                            type="button"
                            disabled={isBusy || formDisabled}
                            onClick={() => void saveShortName(item)}
                          >
                            {isBusy ? "Saving..." : "Save shortname"}
                          </button>
                        </>
                      ) : (
                        <button
                          className="btn btn--secondary"
                          type="button"
                          disabled={actionsDisabled}
                          onClick={() => {
                            setShortNameDraft(status.shortName);
                            setEditingShortNameId(item.id);
                          }}
                        >
                          Set shortname
                        </button>
                      )
                    ) : (
                      <span className="muted">Short name is locked by a derived metric.</span>
                    )}
                    {item.canUnlink ? (
                      <button
                        className="btn btn--secondary"
                        type="button"
                        disabled={actionsDisabled}
                        onClick={() => void unlink(item)}
                      >
                        Unlink
                      </button>
                    ) : null}
                  </div>
                ) : null}
                {status?.state === "error" ? <p className="muted">{status.message}</p> : null}
                {showCreateForm ? (
                  <MissingTimeserieForm
                    key={`${item.slot}:${item.id}`}
                    formId={`${createIdPrefix}-form`}
                    idPrefix={createIdPrefix}
                    timeserieId={createIdFor(item)}
                    defaultId={item.inheritedId}
                    createdId={unlinkedCreatedIds[item.slot]}
                    nodeName={props.node.name}
                    slotLabel={item.label}
                    saving={isBusy}
                    disabled={actionsDisabled}
                    onCreate={(payload) => createSlotTimeserie(item, payload)}
                    onLink={(timeserieId) => linkSlotTimeserie(item.slot, timeserieId)}
                  />
                ) : null}
                {item.id && status?.state === "exists" ? (
                  <section
                    className="destructive-action-section"
                    aria-label={`${item.label} deletion`}
                  >
                    <div className="form-actions">
                      {!isDeleting ? (
                        <button
                          className="btn btn--danger"
                          type="button"
                          disabled={actionsDisabled}
                          onClick={() => setConfirmingDeleteId(item.id)}
                        >
                          Delete timeserie
                        </button>
                      ) : null}
                    </div>
                    {isDeleting ? (
                      <div className="delete-confirmation" role="alertdialog">
                        <p>Are you sure you want to delete this timeserie?</p>
                        <div className="form-actions">
                          <button
                            className="btn btn--danger"
                            type="button"
                            disabled={formDisabled || isBusy}
                            onClick={() => void confirmDelete(item)}
                          >
                            {isBusy ? "Deleting..." : "Yes"}
                          </button>
                          <button
                            className="btn btn--secondary"
                            type="button"
                            disabled={formDisabled || isBusy}
                            onClick={() => setConfirmingDeleteId(null)}
                          >
                            No
                          </button>
                        </div>
                      </div>
                    ) : null}
                  </section>
                ) : null}
              </section>
            );
          })}
        </div>
      </section>
    </div>
  );
}

function MissingTimeserieForm(props: {
  formId: string;
  idPrefix: string;
  // The id input sits in the card header and belongs to this form through its form attribute.
  timeserieId: string;
  defaultId: string;
  // A timeserie this slot created whose link failed; submitting it again retries the link only.
  createdId: string;
  nodeName: string;
  slotLabel: string;
  saving: boolean;
  disabled: boolean;
  onCreate: (payload: TimeserieCreateRequest) => Promise<void>;
  onLink: (timeserieId: string) => Promise<void>;
}) {
  const [name, setName] = useState(`${props.nodeName} ${props.slotLabel}`);
  const [shortName, setShortName] = useState("");
  const [description, setDescription] = useState("");
  const [unit, setUnit] = useState("");
  const [timeUnit, setTimeUnit] = useState<TimeserieTimeUnit>("month");
  const [valueUnit, setValueUnit] = useState<TimeserieValueUnit>("number");
  const [formError, setFormError] = useState("");
  const submitDisabled = props.disabled || !name.trim() || !props.timeserieId.trim();

  async function submit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    setFormError("");
    const timeserieId = props.timeserieId.trim();

    if (timeserieId !== props.createdId) {
      try {
        await props.onCreate({
          id: timeserieId,
          name: name.trim(),
          shortName: inputValueToPayload(shortName),
          description: inputValueToPayload(description),
          unit: inputValueToPayload(unit),
          timeUnit,
          valueUnit
        });
      } catch (error) {
        setFormError(error instanceof Error ? error.message : "Could not create timeserie.");
        return;
      }
    }

    // A timeserie with the type default id is inherited, so it needs no explicit link.
    if (timeserieId === props.defaultId) return;

    try {
      await props.onLink(timeserieId);
    } catch (error) {
      setFormError(
        `Timeserie ${timeserieId} was created but could not be linked: ${messageFromError(error)}`
      );
    }
  }

  return (
    <form id={props.formId} className="timeserie-create-form" onSubmit={submit}>
      <div className="form-row">
        <label className="form-label form-label--required" htmlFor={`${props.idPrefix}-name`}>
          Name
        </label>
        <input
          id={`${props.idPrefix}-name`}
          className="input"
          value={name}
          onChange={(event) => setName(event.target.value)}
          disabled={props.disabled}
        />
      </div>
      <div className="form-row">
        <label className="form-label" htmlFor={`${props.idPrefix}-short-name`}>
          Short name
        </label>
        <input
          id={`${props.idPrefix}-short-name`}
          className="input"
          value={shortName}
          onChange={(event) => setShortName(event.target.value)}
          disabled={props.disabled}
        />
      </div>
      <div className="form-row">
        <label className="form-label" htmlFor={`${props.idPrefix}-description`}>
          Description
        </label>
        <textarea
          id={`${props.idPrefix}-description`}
          className="textarea"
          value={description}
          onChange={(event) => setDescription(event.target.value)}
          disabled={props.disabled}
        />
      </div>
      <div className="form-row">
        <label className="form-label" htmlFor={`${props.idPrefix}-unit`}>
          Unit
        </label>
        <input
          id={`${props.idPrefix}-unit`}
          className="input"
          value={unit}
          onChange={(event) => setUnit(event.target.value)}
          disabled={props.disabled}
        />
      </div>
      <div className="timeserie-create-form__units">
        <div className="form-row">
          <label
            className="form-label form-label--required"
            htmlFor={`${props.idPrefix}-time-unit`}
          >
            Time unit
          </label>
          <select
            id={`${props.idPrefix}-time-unit`}
            className="select"
            value={timeUnit}
            onChange={(event) => setTimeUnit(event.target.value as TimeserieTimeUnit)}
            disabled={props.disabled}
          >
            {TIME_UNIT_OPTIONS.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
        </div>
        <div className="form-row">
          <label
            className="form-label form-label--required"
            htmlFor={`${props.idPrefix}-value-unit`}
          >
            Value unit
          </label>
          <select
            id={`${props.idPrefix}-value-unit`}
            className="select"
            value={valueUnit}
            onChange={(event) => setValueUnit(event.target.value as TimeserieValueUnit)}
            disabled={props.disabled}
          >
            {VALUE_UNIT_OPTIONS.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
        </div>
      </div>
      {formError ? (
        <Alert
          variant="danger"
          role="alert"
          message={formError}
          onDismiss={() => setFormError("")}
        />
      ) : null}
      <div className="form-actions">
        <button className="btn btn--primary" type="submit" disabled={submitDisabled}>
          {props.saving ? "Creating..." : "Create timeserie"}
        </button>
      </div>
    </form>
  );
}
