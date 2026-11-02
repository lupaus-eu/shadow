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
  updateTimeserieShortName
} from "../../api/timeseries";
import type {
  TimeserieCreateRequest,
  TimeserieTimeUnit,
  TimeserieValueUnit
} from "../../api/timeseries";
import Alert from "../../components/Alert";

const TIME_UNIT_OPTIONS: TimeserieTimeUnit[] = ["day", "week", "month", "year"];
const VALUE_UNIT_OPTIONS: TimeserieValueUnit[] = ["number", "string", "boolean"];

type TimeserieSlot = "primary" | "secondary";

type EffectiveTimeserieItem = {
  slot: TimeserieSlot;
  label: string;
  id: string;
  inheritedId: string;
  source: "node" | "type" | "none";
};

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
  const [primaryId, setPrimaryId] = useState(props.node.timeserieId ?? "");
  const [secondaryId, setSecondaryId] = useState(props.node.timeserieSecondaryId ?? "");
  const [existenceById, setExistenceById] = useState<Record<string, ExistenceStatus>>({});
  const [panelError, setPanelError] = useState("");
  const [busyTimeserieId, setBusyTimeserieId] = useState<string | null>(null);
  const [confirmingDeleteId, setConfirmingDeleteId] = useState<string | null>(null);
  const [editingShortNameId, setEditingShortNameId] = useState<string | null>(null);
  const [shortNameDraft, setShortNameDraft] = useState("");

  const effectiveItems = useMemo<EffectiveTimeserieItem[]>(() => {
    const inheritedPrimaryId = trimmed(props.nodeType?.timeserieId);
    const inheritedSecondaryId = trimmed(props.nodeType?.timeserieSecondaryId);
    const explicitPrimaryId = primaryId.trim();
    const explicitSecondaryId = secondaryId.trim();

    return [
      {
        slot: "primary",
        label: "Primary",
        id: explicitPrimaryId || inheritedPrimaryId,
        inheritedId: inheritedPrimaryId,
        source: explicitPrimaryId ? "node" : inheritedPrimaryId ? "type" : "none"
      },
      {
        slot: "secondary",
        label: "Secondary",
        id: explicitSecondaryId || inheritedSecondaryId,
        inheritedId: inheritedSecondaryId,
        source: explicitSecondaryId ? "node" : inheritedSecondaryId ? "type" : "none"
      }
    ];
  }, [primaryId, props.nodeType?.timeserieId, props.nodeType?.timeserieSecondaryId, secondaryId]);

  const effectiveIds = useMemo(
    () => uniqueValues(effectiveItems.map((item) => item.id)),
    [effectiveItems]
  );
  const effectiveIdSignature = effectiveIds.join("\n");
  const formDisabled = props.disabled || props.saving;
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

  async function saveLinks(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    setPanelError("");

    try {
      await props.onUpdateLinks({
        timeserieId: inputValueToPayload(primaryId),
        timeserieSecondaryId: inputValueToPayload(secondaryId)
      });
    } catch (error) {
      setPanelError(messageFromError(error));
    }
  }

  async function createMissingTimeserie(payload: TimeserieCreateRequest) {
    try {
      setPanelError("");
      setBusyTimeserieId(payload.id);
      await createTimeserie(props.orgId, props.scenarioId, payload);
      setExistenceById((current) => ({
        ...current,
        [payload.id]: {
          state: "exists",
          shortName: payload.shortName?.trim() ?? "",
          shortNameEditable: true
        }
      }));
    } catch (error) {
      setPanelError(messageFromError(error));
      throw error;
    } finally {
      setBusyTimeserieId(null);
    }
  }

  async function confirmDelete(timeserieId: string) {
    try {
      setPanelError("");
      setBusyTimeserieId(timeserieId);
      await deleteTimeserie(props.orgId, props.scenarioId, timeserieId);
      setExistenceById((current) => ({
        ...current,
        [timeserieId]: { state: "missing" }
      }));
      props.onTimeserieDeleted(timeserieId);
      setConfirmingDeleteId(null);
    } catch (error) {
      setPanelError(messageFromError(error));
    } finally {
      setBusyTimeserieId(null);
    }
  }

  async function saveShortName(timeserieId: string) {
    try {
      setPanelError("");
      setBusyTimeserieId(timeserieId);
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
      setBusyTimeserieId(null);
    }
  }

  return (
    <section className="detail-card" aria-labelledby="structure-timeserie-title">
      <div className="detail-card__header">
        <h2 id="structure-timeserie-title" className="section-title">
          Timeserie
        </h2>
      </div>

      <form onSubmit={saveLinks}>
        <div className="form-row">
          <label className="form-label" htmlFor="structure-timeserie-primary">
            Primary link
          </label>
          <input
            id="structure-timeserie-primary"
            className="input"
            value={primaryId}
            onChange={(event) => setPrimaryId(event.target.value)}
            disabled={formDisabled}
          />
        </div>
        <div className="form-row">
          <label className="form-label" htmlFor="structure-timeserie-secondary">
            Secondary link
          </label>
          <input
            id="structure-timeserie-secondary"
            className="input"
            value={secondaryId}
            onChange={(event) => setSecondaryId(event.target.value)}
            disabled={formDisabled}
          />
        </div>
        <div className="form-actions">
          <button className="btn btn--primary" type="submit" disabled={formDisabled}>
            {props.saving ? "Saving..." : "Save links"}
          </button>
        </div>
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
          const isBusy = busyTimeserieId === item.id;
          const isDeleting = confirmingDeleteId === item.id;

          return (
            <section
              key={item.slot}
              className="timeserie-status-card"
              aria-label={`${item.label} timeserie`}
            >
              <div className="timeserie-status-card__header">
                <div className="timeserie-status-card__title">
                  <h3>{item.label}</h3>
                  <code className="metadata-code">{item.id || "No id"}</code>
                </div>
                <span className={statusClass(status, item.id)}>{statusLabel(status, item.id)}</span>
              </div>
              {item.source !== "none" || status?.state === "exists" ? (
                <dl className="detail-meta">
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
              {item.id && status?.state === "exists" ? (
                <div className="form-actions">
                  {status.shortNameEditable ? (
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
                          onClick={() => void saveShortName(item.id)}
                        >
                          {isBusy ? "Saving..." : "Save shortname"}
                        </button>
                      </>
                    ) : (
                      <button
                        className="btn btn--secondary"
                        type="button"
                        disabled={formDisabled || Boolean(busyTimeserieId)}
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
                </div>
              ) : null}
              {status?.state === "error" ? <p className="muted">{status.message}</p> : null}
              {item.id && status?.state === "missing" ? (
                <MissingTimeserieForm
                  key={`${item.slot}:${item.id}`}
                  idPrefix={`structure-${item.slot}-timeserie`}
                  timeserieId={item.id}
                  nodeName={props.node.name}
                  slotLabel={item.label}
                  saving={isBusy}
                  disabled={formDisabled || Boolean(busyTimeserieId)}
                  onCreate={createMissingTimeserie}
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
                        disabled={formDisabled || Boolean(busyTimeserieId)}
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
                          onClick={() => void confirmDelete(item.id)}
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
  );
}

function MissingTimeserieForm(props: {
  idPrefix: string;
  timeserieId: string;
  nodeName: string;
  slotLabel: string;
  saving: boolean;
  disabled: boolean;
  onCreate: (payload: TimeserieCreateRequest) => Promise<void>;
}) {
  const [name, setName] = useState(`${props.nodeName} ${props.slotLabel}`);
  const [shortName, setShortName] = useState("");
  const [description, setDescription] = useState("");
  const [unit, setUnit] = useState("");
  const [timeUnit, setTimeUnit] = useState<TimeserieTimeUnit>("month");
  const [valueUnit, setValueUnit] = useState<TimeserieValueUnit>("number");
  const [formError, setFormError] = useState("");
  const submitDisabled = props.disabled || !name.trim();

  async function submit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    setFormError("");

    try {
      await props.onCreate({
        id: props.timeserieId,
        name: name.trim(),
        shortName: inputValueToPayload(shortName),
        description: inputValueToPayload(description),
        unit: inputValueToPayload(unit),
        timeUnit,
        valueUnit
      });
    } catch (error) {
      setFormError(error instanceof Error ? error.message : "Could not create timeserie.");
    }
  }

  return (
    <form className="timeserie-create-form" onSubmit={submit}>
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
