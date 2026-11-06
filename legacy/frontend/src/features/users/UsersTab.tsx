import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { SubmitEvent } from "react";
import { revokeUserAiConnections } from "../../api/ai";
import {
  createUser,
  deleteUser,
  fetchUsers,
  revokeUserSessions,
  updateUser
} from "../../api/users";
import type { UserDto, UserRole } from "../../api/users";
import Alert from "../../components/Alert";

function sortUsers(items: UserDto[]): UserDto[] {
  return [...items].sort((left, right) => {
    const nameComparison = left.name.localeCompare(right.name, undefined, {
      sensitivity: "base"
    });
    return nameComparison || left.id - right.id;
  });
}

function messageFromError(error: unknown): string {
  return error instanceof Error ? error.message : "Unknown error";
}

function userCountText(count: number): string {
  return `${count} active user(s)`;
}

function roleLabel(role: UserRole): string {
  return role === "admin" ? "Admin" : "Consultant";
}

export default function UsersTab(props: {
  currentUserId?: number;
  onCurrentUserSessionsRevoked?: () => void;
}) {
  const [users, setUsers] = useState<UserDto[]>([]);
  const [selectedUserId, setSelectedUserId] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [listError, setListError] = useState("");
  const [saving, setSaving] = useState(false);
  const [createName, setCreateName] = useState("");
  const [createEmail, setCreateEmail] = useState("");
  const [createRole, setCreateRole] = useState<UserRole>("consultant");
  const [createError, setCreateError] = useState("");
  const [editName, setEditName] = useState("");
  const [editEmail, setEditEmail] = useState("");
  const [editRole, setEditRole] = useState<UserRole>("consultant");
  const [actionError, setActionError] = useState("");
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [confirmingRevoke, setConfirmingRevoke] = useState(false);
  const [confirmingAiRevoke, setConfirmingAiRevoke] = useState(false);
  const [actionSuccess, setActionSuccess] = useState<{ title: string; text: string } | null>(null);
  const requestController = useRef<AbortController | null>(null);
  const selectedUserIdRef = useRef<number | null>(null);

  const selectedUser = useMemo(
    () => users.find((user) => user.id === selectedUserId) ?? null,
    [selectedUserId, users]
  );

  const applySelectedUser = useCallback((user: UserDto | null) => {
    selectedUserIdRef.current = user?.id ?? null;
    setSelectedUserId(user?.id ?? null);
    setEditName(user?.name ?? "");
    setEditEmail(user?.email ?? "");
    setEditRole(user?.role ?? "consultant");
    setActionError("");
    setActionSuccess(null);
    setConfirmingDelete(false);
    setConfirmingRevoke(false);
    setConfirmingAiRevoke(false);
  }, []);

  const applyUsers = useCallback(
    (items: UserDto[], preferredUserId?: number | null) => {
      const sortedItems = sortUsers(items);
      setUsers(sortedItems);
      const preferred = preferredUserId === undefined ? selectedUserIdRef.current : preferredUserId;
      const nextSelectedUser =
        sortedItems.find((user) => user.id === preferred) ?? sortedItems[0] ?? null;
      applySelectedUser(nextSelectedUser);
    },
    [applySelectedUser]
  );

  const loadUsers = useCallback(
    async (preferredUserId?: number | null) => {
      requestController.current?.abort();
      const controller = new AbortController();
      requestController.current = controller;

      try {
        setLoading(true);
        setListError("");
        const items = await fetchUsers(controller.signal);
        if (requestController.current !== controller) return;

        applyUsers(items, preferredUserId);
      } catch (error) {
        if (requestController.current !== controller) return;
        if ((error as { name?: string }).name === "AbortError") return;
        setListError(messageFromError(error));
      } finally {
        if (requestController.current === controller) {
          requestController.current = null;
          setLoading(false);
        }
      }
    },
    [applyUsers]
  );

  useEffect(() => {
    async function loadInitialUsers() {
      await loadUsers(null);
    }

    void loadInitialUsers();
    return () => {
      requestController.current?.abort();
      requestController.current = null;
    };
  }, [loadUsers]);

  function selectUser(userId: number) {
    applySelectedUser(users.find((user) => user.id === userId) ?? null);
  }

  async function onCreateSubmit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    const name = createName.trim();
    const email = createEmail.trim();
    if (!name) {
      setCreateError("User name is required.");
      return;
    }
    if (!email) {
      setCreateError("User email is required.");
      return;
    }

    try {
      setSaving(true);
      setCreateError("");
      const created = await createUser({ name, email, role: createRole });
      applyUsers([...users.filter((user) => user.id !== created.id), created], created.id);
      setCreateName("");
      setCreateEmail("");
      setCreateRole("consultant");
    } catch (error) {
      setCreateError(messageFromError(error));
    } finally {
      setSaving(false);
    }
  }

  async function onEditSubmit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedUser) return;

    const name = editName.trim();
    const email = editEmail.trim();
    if (!name) {
      setActionError("User name is required.");
      return;
    }
    if (!email) {
      setActionError("User email is required.");
      return;
    }

    try {
      setSaving(true);
      setActionError("");
      const updated = await updateUser(selectedUser.id, {
        name,
        email,
        role: editRole
      });
      applyUsers([...users.filter((user) => user.id !== updated.id), updated], updated.id);
    } catch (error) {
      setActionError(messageFromError(error));
    } finally {
      setSaving(false);
    }
  }

  async function onConfirmDelete() {
    if (!selectedUser) return;

    try {
      setSaving(true);
      setActionError("");
      await deleteUser(selectedUser.id);
      applyUsers(
        users.filter((user) => user.id !== selectedUser.id),
        null
      );
    } catch (error) {
      setActionError(messageFromError(error));
    } finally {
      setSaving(false);
    }
  }

  async function onConfirmRevoke() {
    if (!selectedUser) return;

    try {
      setSaving(true);
      setActionError("");
      setActionSuccess(null);
      await revokeUserSessions(selectedUser.id);
      if (selectedUser.id === props.currentUserId) {
        props.onCurrentUserSessionsRevoked?.();
        return;
      }
      setConfirmingRevoke(false);
      setActionSuccess({
        title: "Sessions revoked",
        text: `${selectedUser.name}'s Shadow application sessions were revoked.`
      });
    } catch (error) {
      setActionError(messageFromError(error));
    } finally {
      setSaving(false);
    }
  }

  async function onConfirmAiRevoke() {
    if (!selectedUser) return;

    try {
      setSaving(true);
      setActionError("");
      setActionSuccess(null);
      const result = await revokeUserAiConnections(selectedUser.id);
      setConfirmingAiRevoke(false);
      setActionSuccess({
        title: "AI connections revoked",
        text: `${result.revokedCount} AI connection(s) of ${selectedUser.name} were revoked.`
      });
    } catch (error) {
      setActionError(messageFromError(error));
    } finally {
      setSaving(false);
    }
  }

  const editHasChanges = selectedUser
    ? editName.trim() !== selectedUser.name ||
      editEmail.trim() !== selectedUser.email ||
      editRole !== selectedUser.role
    : false;
  const busy = loading || saving;

  return (
    <div className="management-tab users-tab">
      <section className="tab-toolbar" aria-label="Users overview">
        <div className="tab-toolbar__title">
          <h1 className="page-title">Users</h1>
          <span className="tab-toolbar__count">{userCountText(users.length)}</span>
        </div>
        <button
          className="btn btn--secondary"
          type="button"
          onClick={() => void loadUsers()}
          disabled={busy}
        >
          {loading ? "Refreshing..." : "Refresh"}
        </button>
      </section>

      <div className="main-detail-layout">
        <aside className="main-detail-sidebar" aria-label="User selection">
          <section className="sidebar-section">
            <h2 className="secondary-title">Active users</h2>
            {loading && users.length === 0 ? <p className="muted">Loading users...</p> : null}
            {listError ? (
              <Alert
                key={listError}
                variant="danger"
                role="alert"
                title="User API error"
                message={listError}
                onRetry={() => void loadUsers()}
                retryDisabled={loading}
              />
            ) : null}
            {!loading && !listError && users.length === 0 ? (
              <p className="muted">No active users available.</p>
            ) : null}
            <div className="entity-list" aria-label="Active user list">
              {users.map((user) => {
                const isSelected = user.id === selectedUserId;
                return (
                  <button
                    key={user.id}
                    className={`entity-row user-row${isSelected ? " entity-row--selected" : ""}`}
                    type="button"
                    onClick={() => selectUser(user.id)}
                    aria-pressed={isSelected}
                    disabled={busy}
                  >
                    <span className="entity-row__main">
                      <span className="entity-row__title">{user.name}</span>
                      <span className="clamped-description">
                        {user.email} · User ID {user.id}
                      </span>
                    </span>
                    <span className="badge badge--neutral">{roleLabel(user.role)}</span>
                  </button>
                );
              })}
            </div>
          </section>
        </aside>

        <section className="detail-workspace" aria-label="User management">
          <div className="detail-grid">
            <section className="detail-card" aria-labelledby="selected-user-title">
              <div className="detail-card__header">
                <p className="eyebrow">Selected user</p>
                <h2 id="selected-user-title" className="section-title">
                  {selectedUser?.name ?? "No user selected"}
                </h2>
              </div>

              {selectedUser ? (
                <>
                  <form aria-label="Edit user" onSubmit={onEditSubmit}>
                    <UserFields
                      idPrefix="user-edit"
                      name={editName}
                      email={editEmail}
                      role={editRole}
                      disabled={busy}
                      onNameChange={setEditName}
                      onEmailChange={setEditEmail}
                      onRoleChange={setEditRole}
                    />
                    <ActionError message={actionError} onClose={() => setActionError("")} />
                    {actionSuccess ? (
                      <Alert
                        variant="info"
                        role="status"
                        title={actionSuccess.title}
                        message={actionSuccess.text}
                        onDismiss={() => setActionSuccess(null)}
                      />
                    ) : null}
                    <div className="form-actions">
                      <button
                        className="btn btn--primary"
                        type="submit"
                        disabled={busy || !editHasChanges}
                      >
                        {saving ? "Saving..." : "Save user"}
                      </button>
                    </div>
                  </form>

                  <section
                    className="destructive-action-section"
                    aria-label="User session revocation"
                  >
                    {!confirmingRevoke ? (
                      <div className="form-actions">
                        <button
                          className="btn btn--secondary"
                          type="button"
                          onClick={() => {
                            setConfirmingDelete(false);
                            setConfirmingAiRevoke(false);
                            setConfirmingRevoke(true);
                          }}
                          disabled={busy}
                        >
                          Revoke sessions
                        </button>
                      </div>
                    ) : (
                      <div
                        className="delete-confirmation"
                        role="alertdialog"
                        aria-labelledby="revoke-session-confirmation"
                      >
                        <p id="revoke-session-confirmation">
                          Sign {selectedUser.name} out of every Shadow session? This does not sign
                          them out of the identity provider.
                        </p>
                        <div className="form-actions">
                          <button
                            className="btn btn--secondary"
                            type="button"
                            onClick={() => setConfirmingRevoke(false)}
                            disabled={busy}
                          >
                            Cancel revocation
                          </button>
                          <button
                            className="btn btn--danger"
                            type="button"
                            onClick={() => void onConfirmRevoke()}
                            disabled={busy}
                          >
                            {saving ? "Revoking..." : "Confirm revoke sessions"}
                          </button>
                        </div>
                      </div>
                    )}
                  </section>

                  {/* ADR-015 offboarding and incident procedure: stays available
                      while MCP is disabled. */}
                  <section
                    className="destructive-action-section"
                    aria-label="User AI connection revocation"
                  >
                    {!confirmingAiRevoke ? (
                      <div className="form-actions">
                        <button
                          className="btn btn--secondary"
                          type="button"
                          onClick={() => {
                            setConfirmingDelete(false);
                            setConfirmingRevoke(false);
                            setConfirmingAiRevoke(true);
                          }}
                          disabled={busy}
                        >
                          Revoke AI connections
                        </button>
                      </div>
                    ) : (
                      <div
                        className="delete-confirmation"
                        role="alertdialog"
                        aria-labelledby="revoke-ai-connections-confirmation"
                      >
                        <p id="revoke-ai-connections-confirmation">
                          Revoke every AI client connection of {selectedUser.name}? Their AI clients
                          lose access to Shadow immediately and must be connected again.
                        </p>
                        <div className="form-actions">
                          <button
                            className="btn btn--secondary"
                            type="button"
                            onClick={() => setConfirmingAiRevoke(false)}
                            disabled={busy}
                          >
                            Cancel AI revocation
                          </button>
                          <button
                            className="btn btn--danger"
                            type="button"
                            onClick={() => void onConfirmAiRevoke()}
                            disabled={busy}
                          >
                            {saving ? "Revoking..." : "Confirm revoke AI connections"}
                          </button>
                        </div>
                      </div>
                    )}
                  </section>

                  <section className="destructive-action-section" aria-label="User deletion">
                    {!confirmingDelete ? (
                      <div className="form-actions">
                        <button
                          className="btn btn--danger"
                          type="button"
                          onClick={() => {
                            setConfirmingRevoke(false);
                            setConfirmingAiRevoke(false);
                            setConfirmingDelete(true);
                          }}
                          disabled={busy}
                        >
                          Delete user
                        </button>
                      </div>
                    ) : (
                      <div
                        className="delete-confirmation"
                        role="alertdialog"
                        aria-labelledby="delete-user-confirmation"
                      >
                        <p id="delete-user-confirmation">Soft-delete {selectedUser.name}?</p>
                        <div className="form-actions">
                          <button
                            className="btn btn--secondary"
                            type="button"
                            onClick={() => setConfirmingDelete(false)}
                            disabled={busy}
                          >
                            Cancel deletion
                          </button>
                          <button
                            className="btn btn--danger"
                            type="button"
                            onClick={() => void onConfirmDelete()}
                            disabled={busy}
                          >
                            {saving ? "Deleting..." : "Confirm delete user"}
                          </button>
                        </div>
                      </div>
                    )}
                  </section>
                </>
              ) : (
                <p className="muted">Select an active user to edit or delete it.</p>
              )}
            </section>

            <form
              className="detail-card"
              aria-labelledby="create-user-title"
              onSubmit={onCreateSubmit}
            >
              <div className="detail-card__header">
                <h2 id="create-user-title" className="section-title">
                  Create user
                </h2>
              </div>
              <p className="muted">Create an application-wide Shadow user.</p>
              <UserFields
                idPrefix="user-create"
                name={createName}
                email={createEmail}
                role={createRole}
                disabled={busy}
                onNameChange={setCreateName}
                onEmailChange={setCreateEmail}
                onRoleChange={setCreateRole}
              />
              <ActionError message={createError} onClose={() => setCreateError("")} />
              <div className="form-actions">
                <button
                  className="btn btn--primary"
                  type="submit"
                  disabled={busy || !createName.trim() || !createEmail.trim()}
                >
                  {saving ? "Saving..." : "Create user"}
                </button>
              </div>
            </form>
          </div>
        </section>
      </div>
    </div>
  );
}

function UserFields(props: {
  idPrefix: string;
  name: string;
  email: string;
  role: UserRole;
  disabled: boolean;
  onNameChange: (value: string) => void;
  onEmailChange: (value: string) => void;
  onRoleChange: (value: UserRole) => void;
}) {
  const nameId = `${props.idPrefix}-name`;
  const emailId = `${props.idPrefix}-email`;
  const roleId = `${props.idPrefix}-role`;

  return (
    <div className="field-stack">
      <label className="form-label form-label--required" htmlFor={nameId}>
        Name
      </label>
      <input
        id={nameId}
        className="input"
        value={props.name}
        onChange={(event) => props.onNameChange(event.target.value)}
        disabled={props.disabled}
        autoComplete="off"
      />
      <label className="form-label form-label--required" htmlFor={emailId}>
        Email
      </label>
      <input
        id={emailId}
        className="input"
        type="email"
        value={props.email}
        onChange={(event) => props.onEmailChange(event.target.value)}
        disabled={props.disabled}
        autoComplete="email"
      />
      <label className="form-label form-label--required" htmlFor={roleId}>
        Role
      </label>
      <select
        id={roleId}
        className="select"
        value={props.role}
        onChange={(event) => props.onRoleChange(event.target.value as UserRole)}
        disabled={props.disabled}
      >
        <option value="consultant">Consultant</option>
        <option value="admin">Admin</option>
      </select>
    </div>
  );
}

function ActionError(props: { message: string; onClose: () => void }) {
  if (!props.message) return null;
  return (
    <Alert
      variant="danger"
      role="alert"
      title="Action error"
      message={props.message}
      onDismiss={props.onClose}
    />
  );
}
