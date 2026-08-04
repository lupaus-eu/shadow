import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { SubmitEvent } from "react";
import {
  createUser,
  deleteUser,
  fetchUsers,
  updateUser
} from "../../api/users";
import type { UserDto, UserRole } from "../../api/users";

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

export default function UsersTab() {
  const [users, setUsers] = useState<UserDto[]>([]);
  const [selectedUserId, setSelectedUserId] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [listError, setListError] = useState("");
  const [saving, setSaving] = useState(false);
  const [createName, setCreateName] = useState("");
  const [createRole, setCreateRole] = useState<UserRole>("consultant");
  const [createError, setCreateError] = useState("");
  const [editName, setEditName] = useState("");
  const [editRole, setEditRole] = useState<UserRole>("consultant");
  const [actionError, setActionError] = useState("");
  const [confirmingDelete, setConfirmingDelete] = useState(false);
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
    setEditRole(user?.role ?? "consultant");
    setActionError("");
    setConfirmingDelete(false);
  }, []);

  const applyUsers = useCallback((items: UserDto[], preferredUserId?: number | null) => {
    const sortedItems = sortUsers(items);
    setUsers(sortedItems);
    const preferred =
      preferredUserId === undefined
        ? selectedUserIdRef.current
        : preferredUserId;
    const nextSelectedUser =
      sortedItems.find((user) => user.id === preferred) ??
      sortedItems[0] ??
      null;
    applySelectedUser(nextSelectedUser);
  }, [applySelectedUser]);

  const loadUsers = useCallback(async (preferredUserId?: number | null) => {
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
  }, [applyUsers]);

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
    if (!name) {
      setCreateError("User name is required.");
      return;
    }

    try {
      setSaving(true);
      setCreateError("");
      const created = await createUser({ name, role: createRole });
      applyUsers(
        [...users.filter((user) => user.id !== created.id), created],
        created.id
      );
      setCreateName("");
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
    if (!name) {
      setActionError("User name is required.");
      return;
    }

    try {
      setSaving(true);
      setActionError("");
      const updated = await updateUser(selectedUser.id, {
        name,
        role: editRole
      });
      applyUsers(
        [...users.filter((user) => user.id !== updated.id), updated],
        updated.id
      );
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

  const editHasChanges = selectedUser
    ? editName.trim() !== selectedUser.name || editRole !== selectedUser.role
    : false;
  const busy = loading || saving;

  return (
    <div className="scenarios-tab users-tab">
      <section className="scenarios-toolbar" aria-label="Users overview">
        <div className="scenarios-toolbar__title">
          <h1 className="page-title">Users</h1>
          <span className="scenarios-toolbar__count">
            {userCountText(users.length)}
          </span>
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

      <div className="scenario-control-grid">
        <aside className="scenario-side-panel" aria-label="User selection">
          <section className="scenario-side-section">
            <h2 className="secondary__title">Active users</h2>
            {loading && users.length === 0 ? (
              <p className="muted">Loading users...</p>
            ) : null}
            {listError ? (
              <div className="alert alert--danger" role="alert">
                <p className="alert__title">User API error</p>
                <p className="alert__text">{listError}</p>
                <div className="form-actions">
                  <button
                    className="btn btn--secondary btn--compact"
                    type="button"
                    onClick={() => void loadUsers()}
                    disabled={loading}
                  >
                    Retry
                  </button>
                </div>
              </div>
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
                    className={`entity-row user-row${
                      isSelected ? " entity-row--selected" : ""
                    }`}
                    type="button"
                    onClick={() => selectUser(user.id)}
                    aria-pressed={isSelected}
                    disabled={busy}
                  >
                    <span className="entity-row__main">
                      <span className="entity-row__title">{user.name}</span>
                      <span className="entity-row__description">
                        User ID {user.id}
                      </span>
                    </span>
                    <span className="badge badge--neutral">
                      {roleLabel(user.role)}
                    </span>
                  </button>
                );
              })}
            </div>
          </section>
        </aside>

        <section className="scenario-workspace" aria-label="User management">
          <div className="scenario-detail-grid">
            <section
              className="detail-card"
              aria-labelledby="selected-user-title"
            >
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
                      role={editRole}
                      disabled={busy}
                      onNameChange={setEditName}
                      onRoleChange={setEditRole}
                    />
                    <ActionError message={actionError} />
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

                  <section className="state-delete-form" aria-label="User deletion">
                    {!confirmingDelete ? (
                      <div className="form-actions">
                        <button
                          className="btn btn--danger"
                          type="button"
                          onClick={() => setConfirmingDelete(true)}
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
                        <p id="delete-user-confirmation">
                          Soft-delete {selectedUser.name}?
                        </p>
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
                <p className="muted">
                  Select an active user to edit or delete it.
                </p>
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
              <p className="muted">Create an application-wide Schatten user.</p>
              <UserFields
                idPrefix="user-create"
                name={createName}
                role={createRole}
                disabled={busy}
                onNameChange={setCreateName}
                onRoleChange={setCreateRole}
              />
              <ActionError message={createError} />
              <div className="form-actions">
                <button
                  className="btn btn--primary"
                  type="submit"
                  disabled={busy || !createName.trim()}
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
  role: UserRole;
  disabled: boolean;
  onNameChange: (value: string) => void;
  onRoleChange: (value: UserRole) => void;
}) {
  const nameId = `${props.idPrefix}-name`;
  const roleId = `${props.idPrefix}-role`;

  return (
    <div className="user-fields">
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

function ActionError(props: { message: string }) {
  if (!props.message) return null;
  return (
    <div className="alert alert--danger" role="alert">
      <p className="alert__title">Action error</p>
      <p className="alert__text">{props.message}</p>
    </div>
  );
}
