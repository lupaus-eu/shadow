import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { KeyboardEvent, SubmitEvent } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import {
  createOrganisation,
  deleteOrganisation,
  fetchOrganisations,
  updateOrganisation
} from "../api/organisations";
import type { OrganisationDto } from "../api/organisations";
import { WORKSPACE_TABS } from "../workspace/workspaceTabs";
import Alert from "./Alert";

type OrganisationAction = "rename" | "delete" | "create" | null;

type OrganisationDropdownProps = {
  orgId: string;
  organisationName: string;
  onOrganisationNameChange: (name: string) => void;
};

function sortOrganisations(items: OrganisationDto[]): OrganisationDto[] {
  return [...items].sort((left, right) => {
    const nameComparison = left.name.localeCompare(right.name, undefined, {
      sensitivity: "base"
    });
    return nameComparison || left.id.localeCompare(right.id);
  });
}

function messageFromError(error: unknown): string {
  return error instanceof Error ? error.message : "Unknown error";
}

function organisationStorageKey(orgId: string): string {
  return `shadow:organisationName:${orgId}`;
}

function storeOrganisationName(orgId: string, name: string): void {
  try {
    sessionStorage.setItem(organisationStorageKey(orgId), name);
  } catch {
    // Session storage is only a display convenience.
  }
}

function removeStoredOrganisationName(orgId: string): void {
  try {
    sessionStorage.removeItem(organisationStorageKey(orgId));
  } catch {
    // Session storage is only a display convenience.
  }
}

export default function OrganisationDropdown(props: OrganisationDropdownProps) {
  const { orgId, organisationName, onOrganisationNameChange } = props;
  const navigate = useNavigate();
  const location = useLocation();
  const rootRef = useRef<HTMLDivElement | null>(null);
  const panelRef = useRef<HTMLDivElement | null>(null);
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const renameButtonRef = useRef<HTMLButtonElement | null>(null);
  const deleteButtonRef = useRef<HTMLButtonElement | null>(null);
  const addButtonRef = useRef<HTMLButtonElement | null>(null);
  const renameInputRef = useRef<HTMLInputElement | null>(null);
  const deleteInputRef = useRef<HTMLInputElement | null>(null);
  const createInputRef = useRef<HTMLInputElement | null>(null);
  const focusFirstOptionRef = useRef(false);

  const [open, setOpen] = useState(false);
  const [organisations, setOrganisations] = useState<OrganisationDto[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState("");
  const [action, setAction] = useState<OrganisationAction>(null);
  const [actionError, setActionError] = useState("");
  const [renameName, setRenameName] = useState("");
  const [deleteConfirmation, setDeleteConfirmation] = useState("");
  const [createName, setCreateName] = useState("");
  const [pendingAction, setPendingAction] = useState<Exclude<OrganisationAction, null> | null>(
    null
  );

  const currentOrganisation = useMemo(
    () => organisations.find((organisation) => organisation.id === orgId) ?? null,
    [organisations, orgId]
  );
  const displayedName = currentOrganisation?.name ?? organisationName;
  const busy = pendingAction !== null;

  const resetActions = useCallback((): void => {
    setAction(null);
    setActionError("");
    setRenameName("");
    setDeleteConfirmation("");
    setCreateName("");
  }, []);

  const closeDropdown = useCallback(
    (restoreFocus: boolean): void => {
      if (busy) return;
      focusFirstOptionRef.current = false;
      setOpen(false);
      resetActions();
      if (restoreFocus) queueMicrotask(() => triggerRef.current?.focus());
    },
    [busy, resetActions]
  );

  useEffect(() => {
    const controller = new AbortController();
    let ignore = false;

    async function loadOrganisations() {
      try {
        setLoading(true);
        setLoadError("");
        const items = sortOrganisations(await fetchOrganisations(controller.signal));
        if (ignore) return;

        setOrganisations(items);
        const current = items.find((item) => item.id === orgId);
        if (current) {
          onOrganisationNameChange(current.name);
          storeOrganisationName(current.id, current.name);
        }
      } catch (error) {
        if (ignore || (error as { name?: string }).name === "AbortError") return;
        setLoadError(messageFromError(error));
      } finally {
        if (!ignore) setLoading(false);
      }
    }

    void loadOrganisations();
    return () => {
      ignore = true;
      controller.abort();
    };
  }, [orgId, onOrganisationNameChange]);

  useEffect(() => {
    if (!open) return;

    function onPointerDown(event: PointerEvent) {
      if (event.target instanceof Node && !rootRef.current?.contains(event.target)) {
        closeDropdown(false);
      }
    }

    function onKeyDown(event: globalThis.KeyboardEvent) {
      if (event.key !== "Escape") return;
      event.preventDefault();
      closeDropdown(true);
    }

    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [closeDropdown, open]);

  useEffect(() => {
    if (!open || !focusFirstOptionRef.current) return;
    const firstOption = panelRef.current?.querySelector<HTMLButtonElement>(
      "[data-organisation-option]"
    );
    if (!firstOption) return;
    focusFirstOptionRef.current = false;
    firstOption.focus();
  }, [open, organisations]);

  useEffect(() => {
    if (action === "rename") {
      renameInputRef.current?.focus();
      renameInputRef.current?.select();
    } else if (action === "delete") {
      deleteInputRef.current?.focus();
    } else if (action === "create") {
      createInputRef.current?.focus();
    }
  }, [action]);

  function currentTabSignature(): string {
    const candidate = location.pathname.split("/").filter(Boolean).at(-1);
    return WORKSPACE_TABS.some((tab) => tab.signature === candidate) ? candidate! : "org-states";
  }

  function navigateToOrganisation(organisation: OrganisationDto): void {
    storeOrganisationName(organisation.id, organisation.name);
    onOrganisationNameChange(organisation.name);
    navigate(`/shadow/${encodeURIComponent(organisation.id)}/${currentTabSignature()}`, {
      state: { organisationName: organisation.name }
    });
  }

  function onTriggerKeyDown(event: KeyboardEvent<HTMLButtonElement>): void {
    if (event.key !== "ArrowDown") return;
    event.preventDefault();
    focusFirstOptionRef.current = true;
    setOpen(true);
  }

  function selectOrganisation(organisation: OrganisationDto): void {
    if (busy) return;
    if (organisation.id !== orgId) navigateToOrganisation(organisation);
    closeDropdown(false);
  }

  function openRename(): void {
    if (!currentOrganisation || busy) return;
    setActionError("");
    setRenameName(currentOrganisation.name);
    setAction("rename");
  }

  function openDelete(): void {
    if (!currentOrganisation || busy) return;
    setActionError("");
    setDeleteConfirmation("");
    setAction("delete");
  }

  function openCreate(): void {
    if (busy) return;
    setActionError("");
    setCreateName("");
    setAction("create");
  }

  function cancelAction(): void {
    const cancelledAction = action;
    resetActions();
    queueMicrotask(() => {
      if (cancelledAction === "rename") renameButtonRef.current?.focus();
      if (cancelledAction === "delete") deleteButtonRef.current?.focus();
      if (cancelledAction === "create") addButtonRef.current?.focus();
    });
  }

  async function onRenameSubmit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!currentOrganisation || busy) return;
    const name = renameName.trim();
    if (!name || name === currentOrganisation.name) return;

    try {
      setPendingAction("rename");
      setActionError("");
      const updated = await updateOrganisation(currentOrganisation.id, { name });
      setOrganisations((current) =>
        sortOrganisations(
          current.map((organisation) => (organisation.id === updated.id ? updated : organisation))
        )
      );
      storeOrganisationName(updated.id, updated.name);
      onOrganisationNameChange(updated.name);
      navigate(location.pathname, {
        replace: true,
        state: { organisationName: updated.name }
      });
      resetActions();
    } catch (error) {
      setActionError(messageFromError(error));
    } finally {
      setPendingAction(null);
    }
  }

  async function onDeleteSubmit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!currentOrganisation || busy || deleteConfirmation !== "DELETE") {
      return;
    }

    try {
      setPendingAction("delete");
      setActionError("");
      await deleteOrganisation(currentOrganisation.id);

      const remaining = sortOrganisations(
        organisations.filter((organisation) => organisation.id !== currentOrganisation.id)
      );
      removeStoredOrganisationName(currentOrganisation.id);
      setOrganisations(remaining);
      resetActions();
      setOpen(false);

      if (remaining[0]) {
        navigateToOrganisation(remaining[0]);
      } else {
        navigate("/");
      }
    } catch (error) {
      setActionError(messageFromError(error));
    } finally {
      setPendingAction(null);
    }
  }

  async function onCreateSubmit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    const name = createName.trim();
    if (!name) return;

    try {
      setPendingAction("create");
      setActionError("");
      const created = await createOrganisation({ name });
      setOrganisations((current) =>
        sortOrganisations([
          ...current.filter((organisation) => organisation.id !== created.id),
          created
        ])
      );
      resetActions();
      setOpen(false);
      navigateToOrganisation(created);
    } catch (error) {
      setActionError(messageFromError(error));
    } finally {
      setPendingAction(null);
    }
  }

  const trimmedRenameName = renameName.trim();
  const renameDisabled =
    busy ||
    !currentOrganisation ||
    !trimmedRenameName ||
    trimmedRenameName === currentOrganisation.name;

  return (
    <div className="dropdown-shell organisation-dropdown" ref={rootRef}>
      <button
        ref={triggerRef}
        className="context-chip context-chip--interactive dropdown-trigger"
        type="button"
        title={`Organisation: ${displayedName}`}
        aria-label={`Organisation: ${displayedName}`}
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-controls="organisation-dropdown-panel"
        disabled={busy}
        onClick={() => {
          if (busy) return;
          setOpen((value) => !value);
          if (open) resetActions();
        }}
        onKeyDown={onTriggerKeyDown}
      >
        <span className="context-chip__label" aria-hidden="true">
          Organisation
        </span>
        <span className="context-chip__value">{displayedName}</span>
        <ChevronIcon />
      </button>

      {open ? (
        <div
          id="organisation-dropdown-panel"
          className="dropdown-panel organisation-dropdown__panel"
          role="dialog"
          aria-label="Organisation selector"
          ref={panelRef}
        >
          <div className="organisation-dropdown__list" aria-label="Organisations">
            {loading ? <p className="muted">Loading organisations...</p> : null}
            {!loading && organisations.length === 0 && !loadError ? (
              <p className="muted">No organisations available.</p>
            ) : null}
            {organisations.map((organisation) => {
              const isCurrent = organisation.id === orgId;
              return (
                <div
                  className={`organisation-dropdown__row${
                    isCurrent ? " organisation-dropdown__row--current" : ""
                  }`}
                  key={organisation.id}
                >
                  <button
                    className="dropdown-option organisation-dropdown__option"
                    type="button"
                    data-organisation-option
                    aria-current={isCurrent ? "true" : undefined}
                    onClick={() => selectOrganisation(organisation)}
                    disabled={busy}
                  >
                    <span>{organisation.name}</span>
                    {isCurrent ? (
                      <span className="organisation-dropdown__current">Current</span>
                    ) : null}
                  </button>
                  {isCurrent ? (
                    <div className="organisation-dropdown__actions">
                      <button
                        ref={renameButtonRef}
                        className="icon-button"
                        type="button"
                        aria-label="Rename organisation"
                        title="Rename organisation"
                        onClick={openRename}
                        disabled={busy}
                      >
                        <PenIcon />
                      </button>
                      <button
                        ref={deleteButtonRef}
                        className="icon-button icon-button--danger"
                        type="button"
                        aria-label="Delete organisation"
                        title="Delete organisation"
                        onClick={openDelete}
                        disabled={busy}
                      >
                        <TrashIcon />
                      </button>
                    </div>
                  ) : null}
                </div>
              );
            })}
          </div>

          {loadError ? (
            <Alert
              key={loadError}
              variant="danger"
              role="alert"
              className="organisation-dropdown__alert"
              title="Organisation load error"
              message={loadError}
            />
          ) : null}

          {action === "rename" && currentOrganisation ? (
            <form
              className="organisation-dropdown__form"
              aria-label="Rename organisation"
              onSubmit={onRenameSubmit}
            >
              <label className="form-label" htmlFor="organisation-rename-name">
                Organisation name
              </label>
              <input
                ref={renameInputRef}
                id="organisation-rename-name"
                className="input"
                value={renameName}
                onChange={(event) => setRenameName(event.target.value)}
                disabled={busy}
              />
              <ActionError message={actionError} onClose={() => setActionError("")} />
              <div className="form-actions">
                <button
                  className="btn btn--secondary btn--compact"
                  type="button"
                  onClick={cancelAction}
                  disabled={busy}
                >
                  Cancel
                </button>
                <button
                  className="btn btn--primary btn--compact"
                  type="submit"
                  disabled={renameDisabled}
                >
                  {pendingAction === "rename" ? "Saving..." : "Save name"}
                </button>
              </div>
            </form>
          ) : null}

          {action === "delete" && currentOrganisation ? (
            <form
              className="organisation-dropdown__form organisation-dropdown__form--danger"
              role="alertdialog"
              aria-labelledby="organisation-delete-title"
              onSubmit={onDeleteSubmit}
            >
              <p id="organisation-delete-title">
                Soft-delete <strong>{currentOrganisation.name}</strong>?
              </p>
              <label className="form-label" htmlFor="organisation-delete-confirm">
                Confirmation
              </label>
              <input
                ref={deleteInputRef}
                id="organisation-delete-confirm"
                className="input"
                value={deleteConfirmation}
                onChange={(event) => setDeleteConfirmation(event.target.value)}
                placeholder="Type DELETE to confirm"
                autoComplete="off"
                disabled={busy}
              />
              <ActionError message={actionError} onClose={() => setActionError("")} />
              <div className="form-actions">
                <button
                  className="btn btn--secondary btn--compact"
                  type="button"
                  onClick={cancelAction}
                  disabled={busy}
                >
                  Cancel
                </button>
                <button
                  className="btn btn--danger btn--compact"
                  type="submit"
                  disabled={busy || deleteConfirmation !== "DELETE"}
                >
                  {pendingAction === "delete" ? "Deleting..." : "Delete organisation"}
                </button>
              </div>
            </form>
          ) : null}

          {action === "create" ? (
            <form
              className="organisation-dropdown__form"
              aria-label="Add organisation"
              onSubmit={onCreateSubmit}
            >
              <label className="form-label" htmlFor="organisation-create-name">
                Organisation name
              </label>
              <input
                ref={createInputRef}
                id="organisation-create-name"
                className="input"
                value={createName}
                onChange={(event) => setCreateName(event.target.value)}
                placeholder="Organisation name"
                disabled={busy}
              />
              <ActionError message={actionError} onClose={() => setActionError("")} />
              <div className="form-actions">
                <button
                  className="btn btn--secondary btn--compact"
                  type="button"
                  onClick={cancelAction}
                  disabled={busy}
                >
                  Cancel
                </button>
                <button
                  className="btn btn--primary btn--compact"
                  type="submit"
                  disabled={busy || !createName.trim()}
                >
                  {pendingAction === "create" ? "Creating..." : "Create organisation"}
                </button>
              </div>
            </form>
          ) : (
            <div className="organisation-dropdown__footer">
              <button
                ref={addButtonRef}
                className="btn btn--secondary organisation-dropdown__add"
                type="button"
                onClick={openCreate}
                disabled={busy}
              >
                Add organisation
              </button>
            </div>
          )}
        </div>
      ) : null}
    </div>
  );
}

function ActionError(props: { message: string; onClose: () => void }) {
  if (!props.message) return null;
  return (
    <Alert
      variant="danger"
      role="alert"
      className="organisation-dropdown__alert"
      message={props.message}
      onDismiss={props.onClose}
    />
  );
}

function ChevronIcon() {
  return (
    <svg className="dropdown-chevron" viewBox="0 0 24 24" aria-hidden="true">
      <path d="m7 10 5 5 5-5" />
    </svg>
  );
}

function PenIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="m4 20 4.4-1 10.8-10.8a2.1 2.1 0 0 0-3-3L5.4 16 4 20Z" />
      <path d="m14.8 6.6 2.6 2.6" />
    </svg>
  );
}

function TrashIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M4 7h16" />
      <path d="M9 7V4h6v3" />
      <path d="m6 7 1 13h10l1-13" />
      <path d="M10 11v5M14 11v5" />
    </svg>
  );
}
