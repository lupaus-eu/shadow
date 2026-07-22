import { useEffect, useMemo, useState } from "react";
import type { FormEvent } from "react";
import type {
  GraphNodeDto,
  GraphNodeUpdateRequest,
  NodeTypeMetadataDto
} from "../../api/orgTwinStructure";
import {
  createTimeserie,
  deleteTimeserie,
  fetchTimeserieExists
} from "../../api/timeseries";
import type {
  TimeserieCreateRequest,
  TimeserieTimeUnit,
  TimeserieValueUnit
} from "../../api/timeseries";

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
  | { state: "exists" }
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

export default function TimeseriePanel(props: {
  orgId: string;
  scenarioId: string;
  node: GraphNodeDto;
  nodeType: NodeTypeMetadataDto | undefined;
  saving: boolean;
  disabled?: boolean;
  onUpdateLinks: (payload: GraphNodeUpdateRequest) => Promise<void>;
  onTimeserieDeleted: (timeserieId: string) => void;
}) {
  const [primaryId, setPrimaryId] = useState(props.node.timeserieId ?? "");
  const [secondaryId, setSecondaryId] = useState(
    props.node.timeserieSecondaryId ?? ""
  );
  const [existenceById, setExistenceById] = useState<
    Record<string, ExistenceStatus>
  >({});
  const [panelError, setPanelError] = useState("");
  const [busyTimeserieId, setBusyTimeserieId] = useState<string | null>(null);
  const [confirmingDeleteId, setConfirmingDeleteId] = useState<string | null>(null);

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
  }, [
    primaryId,
    props.nodeType?.timeserieId,
    props.nodeType?.timeserieSecondaryId,
    secondaryId
  ]);

  const effectiveIds = useMemo(
    () => uniqueValues(effectiveItems.map((item) => item.id)),
    [effectiveItems]
  );
  const effectiveIdSignature = effectiveIds.join("\n");
  const formDisabled = props.disabled || props.saving;

  useEffect(() => {
    const ids = effectiveIdSignature ? effectiveIdSignature.split("\n") : [];
    if (ids.length === 0) return;

    const ac = new AbortController();

    for (const id of ids) {
      void fetchTimeserieExists(props.orgId, props.scenarioId, id, ac.signal)
        .then((response) => {
          setExistenceById((current) => ({
            ...current,
            [id]: { state: response.exists ? "exists" : "missing" }
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

  async function saveLinks(event: FormEvent<HTMLFormElement>) {
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
        [payload.id]: { state: "exists" }
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
            <dd>{props.nodeType.timeserieIdRule}</dd>
          </div>
        </dl>
      ) : null}

      {panelError ? (
        <div className="alert alert--danger" role="alert">
          <p className="alert__title">Timeserie error</p>
          <p className="alert__text">{panelError}</p>
        </div>
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
                  <code>{item.id || "No id"}</code>
                </div>
                <span className={statusClass(status, item.id)}>
                  {statusLabel(status, item.id)}
                </span>
              </div>
              {item.source !== "none" ? (
                <dl className="detail-meta">
                  <div className="detail-meta__row">
                    <dt>Source</dt>
                    <dd>{item.source === "node" ? "Node link" : "Type default"}</dd>
                  </div>
                  {item.inheritedId && item.source === "node" ? (
                    <div className="detail-meta__row">
                      <dt>Default</dt>
                      <dd>{item.inheritedId}</dd>
                    </div>
                  ) : null}
                </dl>
              ) : null}
              {status?.state === "error" ? (
                <p className="muted">{status.message}</p>
              ) : null}
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
                <section className="state-delete-form" aria-label={`${item.label} deletion`}>
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
  const [description, setDescription] = useState("");
  const [unit, setUnit] = useState("");
  const [timeUnit, setTimeUnit] = useState<TimeserieTimeUnit>("month");
  const [valueUnit, setValueUnit] = useState<TimeserieValueUnit>("number");
  const [formError, setFormError] = useState("");
  const submitDisabled = props.disabled || !name.trim();

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFormError("");

    try {
      await props.onCreate({
        id: props.timeserieId,
        name: name.trim(),
        description: inputValueToPayload(description),
        unit: inputValueToPayload(unit),
        timeUnit,
        valueUnit
      });
    } catch (error) {
      setFormError(
        error instanceof Error ? error.message : "Could not create timeserie."
      );
    }
  }

  return (
    <form className="timeserie-create-form" onSubmit={submit}>
      <div className="form-row">
        <label
          className="form-label form-label--required"
          htmlFor={`${props.idPrefix}-name`}
        >
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
            onChange={(event) =>
              setValueUnit(event.target.value as TimeserieValueUnit)
            }
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
        <div className="alert alert--danger" role="alert">
          <p className="alert__text">{formError}</p>
        </div>
      ) : null}
      <div className="form-actions">
        <button className="btn btn--primary" type="submit" disabled={submitDisabled}>
          {props.saving ? "Creating..." : "Create timeserie"}
        </button>
      </div>
    </form>
  );
}
