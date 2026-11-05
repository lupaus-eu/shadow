import { useState } from "react";
import type { SubmitEvent } from "react";
import type {
  EdgeTypeMetadataDto,
  GraphEdgeCreateRequest,
  GraphEdgeDto,
  GraphEdgeUpdateRequest,
  GraphNodeDto
} from "../../api/orgTwinStructure";
import Alert from "../../components/Alert";
import GraphNameField from "./GraphNameField";
import { graphNameTooLong } from "./graphNames";

export type EdgeFormCreatePayload = Omit<GraphEdgeCreateRequest, "attributes" | "id">;

export default function EdgeForm(props: {
  idPrefix: string;
  title: string;
  edge: GraphEdgeDto | null;
  nodes: GraphNodeDto[];
  edgeTypes: EdgeTypeMetadataDto[];
  saving: boolean;
  submitLabel: string;
  disabled?: boolean;
  sourceNodeId?: string;
  targetNodeId?: string;
  onSourceNodeIdChange?: (nodeId: string) => void;
  onTargetNodeIdChange?: (nodeId: string) => void;
  nodeClickHint?: string;
  onCreate?: (payload: EdgeFormCreatePayload) => Promise<void>;
  onUpdate?: (payload: GraphEdgeUpdateRequest) => Promise<void>;
  onDelete?: () => Promise<void>;
  lifetime?: { targetDate: string; ending: boolean };
}) {
  const defaultEdgeTypeId = props.edgeTypes[0]?.id ?? "";
  const [name, setName] = useState(props.edge?.name ?? "");
  const [description, setDescription] = useState(props.edge?.description ?? "");
  const [edgeTypeId, setEdgeTypeId] = useState(props.edge?.edgeTypeId ?? defaultEdgeTypeId);
  const [localSourceNodeId, setLocalSourceNodeId] = useState(props.edge?.sourceNodeId ?? "");
  const [localTargetNodeId, setLocalTargetNodeId] = useState(props.edge?.targetNodeId ?? "");
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [formError, setFormError] = useState("");

  const isEdit = Boolean(props.edge);
  const isCreateSelectionControlled =
    !isEdit && props.sourceNodeId !== undefined && props.targetNodeId !== undefined;
  const hasNodeChoices = props.nodes.length > 0;
  const hasEdgeTypeChoices = props.edgeTypes.length > 0;
  const sourceNodeId = isCreateSelectionControlled ? (props.sourceNodeId ?? "") : localSourceNodeId;
  const targetNodeId = isCreateSelectionControlled ? (props.targetNodeId ?? "") : localTargetNodeId;
  const hasSelfReferenceSelection =
    !isEdit && Boolean(sourceNodeId) && sourceNodeId === targetNodeId;
  const selectedEdgeTypeId = props.edgeTypes.some((edgeType) => edgeType.id === edgeTypeId)
    ? edgeTypeId
    : (props.edgeTypes[0]?.id ?? "");
  const formDisabled = props.disabled || props.saving || !hasNodeChoices || !hasEdgeTypeChoices;
  const sourceTargetDisabled = props.disabled || props.saving || !hasNodeChoices;
  const submitDisabled =
    formDisabled ||
    !name.trim() ||
    graphNameTooLong(name) ||
    !selectedEdgeTypeId ||
    !sourceNodeId ||
    !targetNodeId ||
    hasSelfReferenceSelection;
  const canDelete = isEdit && props.onDelete;
  const deleteDate = props.edge?.deleteDate ?? null;
  const removedInOrgState = Boolean(deleteDate) && deleteDate === props.lifetime?.targetDate;
  const showNoAllowedEdgeTypes =
    !isEdit &&
    hasNodeChoices &&
    props.sourceNodeId !== undefined &&
    props.targetNodeId !== undefined &&
    Boolean(sourceNodeId) &&
    Boolean(targetNodeId) &&
    !hasEdgeTypeChoices;
  const submitTooltip = hasSelfReferenceSelection ? "Self referencing edges not allowed" : "";

  async function submit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    setFormError("");

    try {
      const payload = {
        name: name.trim(),
        description: description.trim(),
        edgeTypeId: selectedEdgeTypeId,
        sourceNodeId,
        targetNodeId
      };

      if (isEdit) {
        await props.onUpdate?.(payload);
      } else {
        await props.onCreate?.(payload);
        setName("");
        setDescription("");
      }
    } catch (error) {
      setFormError(error instanceof Error ? error.message : "Could not save edge.");
    }
  }

  async function confirmDelete() {
    if (!props.onDelete) return;
    await props.onDelete();
    setConfirmingDelete(false);
  }

  return (
    <section className="detail-card" aria-labelledby={`${props.idPrefix}-title`}>
      <div className="detail-card__header">
        <h2 id={`${props.idPrefix}-title`} className="section-title">
          {props.title}
        </h2>
      </div>
      {deleteDate ? (
        <p className="muted structure-lifetime-note">
          Exists until {deleteDate}.
          {props.lifetime?.ending ? " Not shown in later org states." : ""}
        </p>
      ) : null}
      {!isEdit && props.nodeClickHint ? <p className="muted">{props.nodeClickHint}</p> : null}
      {!hasNodeChoices && !showNoAllowedEdgeTypes ? (
        <p className="muted">Create nodes and load edge type metadata before saving edges.</p>
      ) : null}
      {/* The name check counts code points; native maxlength counts UTF-16 units. */}
      <form onSubmit={submit} noValidate>
        <GraphNameField
          idPrefix={props.idPrefix}
          value={name}
          onChange={setName}
          disabled={formDisabled}
        />
        <div className="form-row">
          <label className="form-label form-label--required" htmlFor={`${props.idPrefix}-type`}>
            Type
          </label>
          <select
            id={`${props.idPrefix}-type`}
            className="select"
            value={selectedEdgeTypeId}
            onChange={(event) => setEdgeTypeId(event.target.value)}
            disabled={formDisabled}
          >
            {props.edgeTypes.length === 0 ? (
              <option value="">No allowed edge types</option>
            ) : (
              props.edgeTypes.map((edgeType) => (
                <option key={edgeType.id} value={edgeType.id}>
                  {edgeType.displayName}
                </option>
              ))
            )}
          </select>
        </div>
        <div className="structure-coordinate-grid">
          <div className="form-row">
            <label className="form-label form-label--required" htmlFor={`${props.idPrefix}-source`}>
              Source
            </label>
            <select
              id={`${props.idPrefix}-source`}
              className="select"
              value={sourceNodeId}
              onChange={(event) => {
                const nextNodeId = event.target.value;
                if (isCreateSelectionControlled) {
                  props.onSourceNodeIdChange?.(nextNodeId);
                } else {
                  setLocalSourceNodeId(nextNodeId);
                }
              }}
              disabled={sourceTargetDisabled}
            >
              {!isEdit ? <option value="">Select source node</option> : null}
              {props.nodes.map((node) => (
                <option key={node.id} value={node.id}>
                  {node.name}
                </option>
              ))}
            </select>
          </div>
          <div className="form-row">
            <label className="form-label form-label--required" htmlFor={`${props.idPrefix}-target`}>
              Target
            </label>
            <select
              id={`${props.idPrefix}-target`}
              className="select"
              value={targetNodeId}
              onChange={(event) => {
                const nextNodeId = event.target.value;
                if (isCreateSelectionControlled) {
                  props.onTargetNodeIdChange?.(nextNodeId);
                } else {
                  setLocalTargetNodeId(nextNodeId);
                }
              }}
              disabled={sourceTargetDisabled}
            >
              {!isEdit ? <option value="">Select target node</option> : null}
              {props.nodes.map((node) => (
                <option key={node.id} value={node.id}>
                  {node.name}
                </option>
              ))}
            </select>
          </div>
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
            disabled={formDisabled}
          />
        </div>
        {formError ? (
          <Alert
            variant="danger"
            role="alert"
            onDismiss={() => setFormError("")}
            message={formError}
          />
        ) : null}
        <div className="form-actions">
          <span title={submitTooltip}>
            <button className="btn btn--primary" type="submit" disabled={submitDisabled}>
              {props.saving ? "Saving..." : props.submitLabel}
            </button>
          </span>
        </div>
      </form>
      {canDelete ? (
        <section className="destructive-action-section" aria-label="Edge deletion">
          <div className="form-actions">
            {!confirmingDelete ? (
              <button
                className="btn btn--danger"
                type="button"
                disabled={props.saving || removedInOrgState}
                aria-describedby={removedInOrgState ? `${props.idPrefix}-removed-note` : undefined}
                onClick={() => setConfirmingDelete(true)}
              >
                Delete selected edge
              </button>
            ) : null}
          </div>
          {removedInOrgState ? (
            <p id={`${props.idPrefix}-removed-note`} className="muted">
              Already removed in this org state.
            </p>
          ) : null}
          {confirmingDelete ? (
            <div className="delete-confirmation" role="alertdialog">
              <p>Are you sure you want to delete the selected edge?</p>
              <div className="form-actions">
                <button
                  className="btn btn--danger"
                  type="button"
                  disabled={props.saving}
                  onClick={() => void confirmDelete()}
                >
                  {props.saving ? "Deleting..." : "Yes"}
                </button>
                <button
                  className="btn btn--secondary"
                  type="button"
                  disabled={props.saving}
                  onClick={() => setConfirmingDelete(false)}
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
}
