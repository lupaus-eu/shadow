import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within
} from "@testing-library/react";
import { StrictMode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  createUser,
  deleteUser,
  fetchUsers,
  revokeUserSessions,
  updateUser
} from "../../api/users";
import type { UserDto } from "../../api/users";
import UsersTab from "./UsersTab";

vi.mock("../../api/users", () => ({
  createUser: vi.fn(),
  deleteUser: vi.fn(),
  fetchUsers: vi.fn(),
  revokeUserSessions: vi.fn(),
  updateUser: vi.fn()
}));

const fetchUsersMock = vi.mocked(fetchUsers);
const createUserMock = vi.mocked(createUser);
const updateUserMock = vi.mocked(updateUser);
const deleteUserMock = vi.mocked(deleteUser);
const revokeUserSessionsMock = vi.mocked(revokeUserSessions);

const ada: UserDto = {
  id: 2,
  name: "ada",
  email: "ada@example.local",
  role: "admin"
};
const grace: UserDto = {
  id: 3,
  name: "Grace",
  email: "grace@example.local",
  role: "consultant"
};

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((resolver) => {
    resolve = resolver;
  });
  return { promise, resolve };
}

beforeEach(() => {
  vi.resetAllMocks();
});

describe("UsersTab", () => {
  it("loads, sorts, counts, and selects active users", async () => {
    fetchUsersMock.mockResolvedValue([
      grace,
      { id: 5, name: "Ada", email: "ada2@example.local", role: "consultant" },
      ada
    ]);

    render(<UsersTab />);

    expect(screen.getByText("Loading users...")).toBeInTheDocument();
    const list = await screen.findByRole("generic", { name: "Active user list" });
    const rows = within(list).getAllByRole("button");
    expect(rows.map((row) => row.textContent)).toEqual([
      "adaada@example.local · User ID 2Admin",
      "Adaada2@example.local · User ID 5Consultant",
      "Gracegrace@example.local · User ID 3Consultant"
    ]);
    expect(rows[0]).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByText("3 active user(s)")).toBeInTheDocument();
  });

  it("shows load failure, empty, and retry states", async () => {
    fetchUsersMock
      .mockRejectedValueOnce(new Error("Users unavailable."))
      .mockResolvedValueOnce([]);

    render(<UsersTab />);

    expect(await screen.findByText("Users unavailable.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));

    expect(
      await screen.findByText("No active users available.")
    ).toBeInTheDocument();
    expect(fetchUsersMock).toHaveBeenCalledTimes(2);
  });

  it("creates a trimmed user and preserves the created selection", async () => {
    const created: UserDto = {
      id: 4,
      name: "Linus",
      email: "linus@example.local",
      role: "admin"
    };
    fetchUsersMock.mockResolvedValue([ada]);
    createUserMock.mockResolvedValue(created);

    render(<UsersTab />);
    await screen.findByRole("button", { name: /ada/ });
    const form = screen.getByRole("form", { name: "Create user" });

    fireEvent.change(within(form).getByLabelText("Name"), {
      target: { value: "  Linus  " }
    });
    fireEvent.change(within(form).getByLabelText("Email"), {
      target: { value: "  linus@example.local  " }
    });
    fireEvent.change(within(form).getByLabelText("Role"), {
      target: { value: "admin" }
    });
    fireEvent.submit(form);

    await waitFor(() => {
      expect(createUserMock).toHaveBeenCalledWith({
        name: "Linus",
        email: "linus@example.local",
        role: "admin"
      });
    });
    const createdRow = await screen.findByRole("button", { name: /Linus/ });
    expect(createdRow).toHaveAttribute("aria-pressed", "true");
    expect(within(form).getByLabelText("Name")).toHaveValue("");
    expect(within(form).getByLabelText("Email")).toHaveValue("");
    expect(within(form).getByLabelText("Role")).toHaveValue("consultant");
  });

  it("requires non-blank name and email for creation", async () => {
    fetchUsersMock.mockResolvedValue([]);
    render(<UsersTab />);
    await screen.findByText("No active users available.");
    const form = screen.getByRole("form", { name: "Create user" });
    const createButton = within(form).getByRole("button", {
      name: "Create user"
    });

    expect(createButton).toBeDisabled();

    fireEvent.change(within(form).getByLabelText("Name"), {
      target: { value: "Ada" }
    });

    expect(createButton).toBeDisabled();
    fireEvent.change(within(form).getByLabelText("Email"), {
      target: { value: "   " }
    });
    expect(createButton).toBeDisabled();
    expect(createUserMock).not.toHaveBeenCalled();
  });

  it("updates a user and preserves its selection", async () => {
    const updated: UserDto = {
      id: ada.id,
      name: "Ada Lovelace",
      email: "lovelace@example.local",
      role: "consultant"
    };
    fetchUsersMock.mockResolvedValue([ada, grace]);
    updateUserMock.mockResolvedValue(updated);

    render(<UsersTab />);
    await screen.findByRole("button", { name: /ada/ });
    const form = screen.getByRole("form", { name: "Edit user" });
    fireEvent.change(within(form).getByLabelText("Name"), {
      target: { value: "  Ada Lovelace " }
    });
    fireEvent.change(within(form).getByLabelText("Email"), {
      target: { value: " lovelace@example.local " }
    });
    fireEvent.change(within(form).getByLabelText("Role"), {
      target: { value: "consultant" }
    });
    fireEvent.submit(form);

    await waitFor(() => {
      expect(updateUserMock).toHaveBeenCalledWith(ada.id, {
        name: "Ada Lovelace",
        email: "lovelace@example.local",
        role: "consultant"
      });
    });
    expect(
      await screen.findByRole("button", { name: /Ada Lovelace/ })
    ).toHaveAttribute("aria-pressed", "true");
  });

  it("cancels deletion and then soft-deletes with a predictable fallback", async () => {
    fetchUsersMock.mockResolvedValue([ada, grace]);
    deleteUserMock.mockResolvedValue();

    render(<UsersTab />);
    await screen.findByRole("button", { name: /ada/ });
    fireEvent.click(screen.getByRole("button", { name: "Delete user" }));
    expect(screen.getByRole("alertdialog")).toHaveTextContent("Soft-delete ada?");
    fireEvent.click(screen.getByRole("button", { name: "Cancel deletion" }));
    expect(deleteUserMock).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Delete user" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm delete user" }));

    await waitFor(() => expect(deleteUserMock).toHaveBeenCalledWith(ada.id));
    expect(screen.queryByRole("button", { name: /ada/ })).not.toBeInTheDocument();
    expect(await screen.findByRole("button", { name: /Grace/ })).toHaveAttribute(
      "aria-pressed",
      "true"
    );
  });

  it("confirms and reports application-session revocation", async () => {
    fetchUsersMock.mockResolvedValue([ada]);
    revokeUserSessionsMock.mockResolvedValue();

    render(<UsersTab />);
    await screen.findByRole("button", { name: /ada/ });
    fireEvent.click(screen.getByRole("button", { name: "Revoke sessions" }));

    expect(screen.getByRole("alertdialog")).toHaveTextContent(
      "This does not sign them out of the identity provider."
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Confirm revoke sessions" })
    );

    await waitFor(() => expect(revokeUserSessionsMock).toHaveBeenCalledWith(ada.id));
    expect(screen.getByRole("status")).toHaveTextContent(
      "ada's Schatten application sessions were revoked."
    );
  });

  it("reports a session-revocation API failure", async () => {
    fetchUsersMock.mockResolvedValue([ada]);
    revokeUserSessionsMock.mockRejectedValue(new Error("Revocation forbidden."));

    render(<UsersTab />);
    await screen.findByRole("button", { name: /ada/ });
    fireEvent.click(screen.getByRole("button", { name: "Revoke sessions" }));
    fireEvent.click(
      screen.getByRole("button", { name: "Confirm revoke sessions" })
    );

    expect(await screen.findByText("Revocation forbidden.")).toBeInTheDocument();
  });

  it("invalidates frontend auth when the admin revokes their own sessions", async () => {
    const onCurrentUserSessionsRevoked = vi.fn();
    fetchUsersMock.mockResolvedValue([ada]);
    revokeUserSessionsMock.mockResolvedValue();

    render(
      <UsersTab
        currentUserId={ada.id}
        onCurrentUserSessionsRevoked={onCurrentUserSessionsRevoked}
      />
    );
    await screen.findByRole("button", { name: /ada/ });
    fireEvent.click(screen.getByRole("button", { name: "Revoke sessions" }));
    fireEvent.click(
      screen.getByRole("button", { name: "Confirm revoke sessions" })
    );

    await waitFor(() => {
      expect(onCurrentUserSessionsRevoked).toHaveBeenCalledTimes(1);
    });
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("shows mutation failures and disables duplicate submissions while saving", async () => {
    const pending = deferred<UserDto>();
    fetchUsersMock.mockResolvedValue([ada]);
    createUserMock.mockReturnValueOnce(pending.promise);

    render(<UsersTab />);
    const userRow = await screen.findByRole("button", { name: /ada/ });
    const form = screen.getByRole("form", { name: "Create user" });
    fireEvent.change(within(form).getByLabelText("Name"), {
      target: { value: "Linus" }
    });
    fireEvent.change(within(form).getByLabelText("Email"), {
      target: { value: "linus@example.local" }
    });
    fireEvent.submit(form);

    expect(await within(form).findByRole("button", { name: "Saving..." })).toBeDisabled();
    expect(userRow).toBeDisabled();
    pending.resolve({
      id: 4,
      name: "Linus",
      email: "linus@example.local",
      role: "consultant"
    });
    expect(await screen.findByRole("button", { name: /Linus/ })).toHaveAttribute(
      "aria-pressed",
      "true"
    );
    expect(fetchUsersMock).toHaveBeenCalledTimes(1);

    updateUserMock.mockRejectedValueOnce(new Error("Update failed."));
    const editForm = screen.getByRole("form", { name: "Edit user" });
    fireEvent.change(within(editForm).getByLabelText("Name"), {
      target: { value: "Ada changed" }
    });
    fireEvent.submit(editForm);
    expect(await screen.findByText("Update failed.")).toBeInTheDocument();
  });

  it("keeps successful mutations visible without requiring a list reload", async () => {
    const updated: UserDto = {
      id: ada.id,
      name: "Ada updated",
      email: ada.email,
      role: "consultant"
    };
    fetchUsersMock.mockResolvedValue([ada, grace]);
    updateUserMock.mockResolvedValue(updated);

    render(<UsersTab />);
    await screen.findByRole("button", { name: /ada/ });
    const form = screen.getByRole("form", { name: "Edit user" });
    fireEvent.change(within(form).getByLabelText("Name"), {
      target: { value: updated.name }
    });
    fireEvent.change(within(form).getByLabelText("Role"), {
      target: { value: updated.role }
    });
    fireEvent.submit(form);

    expect(
      await screen.findByRole("button", { name: /Ada updated/ })
    ).toBeVisible();
    expect(fetchUsersMock).toHaveBeenCalledTimes(1);
  });

  it("disables mutation controls while a refresh is in progress", async () => {
    const refreshedUsers = deferred<UserDto[]>();
    fetchUsersMock
      .mockResolvedValueOnce([ada])
      .mockReturnValueOnce(refreshedUsers.promise);

    render(<UsersTab />);
    const userRow = await screen.findByRole("button", { name: /ada/ });
    fireEvent.click(screen.getByRole("button", { name: "Refresh" }));

    expect(userRow).toBeDisabled();
    expect(screen.getByRole("button", { name: "Save user" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Create user" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Delete user" })).toBeDisabled();

    await act(async () => refreshedUsers.resolve([ada]));
    expect(screen.getByRole("button", { name: "Refresh" })).toBeEnabled();
  });

  it("aborts the active list request when unmounted", () => {
    let capturedSignal: AbortSignal | undefined;
    fetchUsersMock.mockImplementation((signal) => {
      capturedSignal = signal;
      return new Promise<UserDto[]>(() => undefined);
    });

    const view = render(<UsersTab />);
    expect(capturedSignal?.aborted).toBe(false);
    view.unmount();
    expect(capturedSignal?.aborted).toBe(true);
  });

  it("does not let an older list response overwrite the current users", async () => {
    const older = deferred<UserDto[]>();
    const current = deferred<UserDto[]>();
    fetchUsersMock
      .mockReturnValueOnce(older.promise)
      .mockReturnValueOnce(current.promise);

    render(
      <StrictMode>
        <UsersTab />
      </StrictMode>
    );

    await act(async () => current.resolve([grace]));
    expect(await screen.findByRole("button", { name: /Grace/ })).toBeVisible();

    await act(async () => older.resolve([ada]));
    expect(screen.getByRole("button", { name: /Grace/ })).toBeVisible();
    expect(screen.queryByRole("button", { name: /ada/ })).not.toBeInTheDocument();
  });
});
