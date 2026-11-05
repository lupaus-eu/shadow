import { useMemo, useState } from "react";
import type { SubmitEvent } from "react";
import type {
  GraphNodeCreateRequest,
  GraphNodeDto,
  GraphNodeUpdateRequest,
  NodeTypeMetadataDto
} from "../../api/orgTwinStructure";
import Alert from "../../components/Alert";
import GraphNameField from "./GraphNameField";
import { graphNameTooLong } from "./graphNames";

export type NodeFormCreatePayload = Omit<GraphNodeCreateRequest, "attributes" | "id" | "position">;

export default function NodeForm(props: {
  idPrefix: string;
  title: string;
  node: GraphNodeDto | null;
  nodeTypes: NodeTypeMetadataDto[];
  preferredNodeTypeId?: string;
  saving: boolean;
  submitLabel: string;
  disabled?: boolean;
  onCreate?: (payload: NodeFormCreatePayload) => Promise<void>;
  onUpdate?: (payload: GraphNodeUpdateRequest) => Promise<void>;
  onDelete?: () => Promise<void>;
  lifetime?: { targetDate: string; ending: boolean };
}) {
  const defaultNodeTypeId = props.nodeTypes[0]?.id ?? "";
  const [name, setName] = useState(props.node?.name ?? "");
  const [description, setDescription] = useState(props.node?.description ?? "");
  const [nodeTypeId, setNodeTypeId] = useState(
    props.node?.nodeTypeId ?? props.preferredNodeTypeId ?? defaultNodeTypeId
  );
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [formError, setFormError] = useState("");

  const hasNodeTypes = props.nodeTypes.length > 0;
  const isEdit = Boolean(props.node);
  const canDelete = isEdit && props.onDelete;
  const deleteDate = props.node?.deleteDate ?? null;
  const removedInOrgState = Boolean(deleteDate) && deleteDate === props.lifetime?.targetDate;
  const formDisabled = props.disabled || props.saving || !hasNodeTypes;
  const submitDisabled = formDisabled || !name.trim() || graphNameTooLong(name) || !nodeTypeId;
  const nodeTypeHelp = useMemo(() => {
    if (hasNodeTypes) return "";
    return "Node type metadata is required before nodes can be saved.";
  }, [hasNodeTypes]);

  async function submit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    setFormError("");

    try {
      const payload = {
        name: name.trim(),
        description: description.trim(),
        nodeTypeId
      };

      if (isEdit) {
        await props.onUpdate?.(payload);
      } else {
        await props.onCreate?.(payload);
        setName("");
        setDescription("");
      }
    } catch (error) {
      setFormError(error instanceof Error ? error.message : "Could not save node.");
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
      {nodeTypeHelp ? <p className="muted">{nodeTypeHelp}</p> : null}
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
            value={nodeTypeId}
            onChange={(event) => setNodeTypeId(event.target.value)}
            disabled={formDisabled}
          >
            {props.nodeTypes.map((nodeType) => (
              <option key={nodeType.id} value={nodeType.id}>
                {nodeType.displayName}
              </option>
            ))}
          </select>
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
          <button className="btn btn--primary" type="submit" disabled={submitDisabled}>
            {props.saving ? "Saving..." : props.submitLabel}
          </button>
        </div>
      </form>
      {canDelete ? (
        <section className="destructive-action-section" aria-label="Node deletion">
          <div className="form-actions">
            {!confirmingDelete ? (
              <button
                className="btn btn--danger"
                type="button"
                disabled={props.saving || removedInOrgState}
                aria-describedby={removedInOrgState ? `${props.idPrefix}-removed-note` : undefined}
                onClick={() => setConfirmingDelete(true)}
              >
                Delete selected node
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
              <p>Are you sure you want to delete the selected node?</p>
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
