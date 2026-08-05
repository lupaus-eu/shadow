import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { StrictMode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import * as api from "../../api/customers";
import type { AddressDto, ContactDto, CustomerDto } from "../../api/customers";
import CustomersTab from "./CustomersTab";

vi.mock("../../api/customers", () => ({
  createAddress: vi.fn(), createContact: vi.fn(), createCustomer: vi.fn(),
  deleteAddress: vi.fn(), deleteContact: vi.fn(), deleteCustomer: vi.fn(),
  fetchAddresses: vi.fn(), fetchContacts: vi.fn(), fetchCustomers: vi.fn(),
  updateAddress: vi.fn(), updateContact: vi.fn(), updateCustomer: vi.fn()
}));

const customer = (id: number, name: string, status: "active" | "archived" = "active"): CustomerDto => ({
  id, name, email: `${name.toLowerCase()}@example.com`, status, createdAt: "2026-01-01", updatedAt: "2026-01-01"
});
const contact = (id: number, name: string): ContactDto => ({ id, name, email: null, phone: null, jobTitle: null, createdAt: "x", updatedAt: "x" });
const address = (id: number, label: string): AddressDto => ({ id, label, addressLine1: "Main 1", addressLine2: null, postalCode: null, city: "Helsinki", region: null, countryCode: "FI", createdAt: "x", updatedAt: "x" });

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(api.fetchCustomers).mockResolvedValue([]);
  vi.mocked(api.fetchContacts).mockResolvedValue([]);
  vi.mocked(api.fetchAddresses).mockResolvedValue([]);
});

describe("CustomersTab", () => {
  it("sorts and selects customers, then loads both child collections in parallel", async () => {
    const pendingContacts = deferred<ContactDto[]>();
    const pendingAddresses = deferred<AddressDto[]>();
    vi.mocked(api.fetchCustomers).mockResolvedValue([customer(3, "Zulu", "archived"), customer(2, "alpha"), customer(1, "Alpha")]);
    vi.mocked(api.fetchContacts).mockReturnValue(pendingContacts.promise);
    vi.mocked(api.fetchAddresses).mockReturnValue(pendingAddresses.promise);

    render(<CustomersTab />);
    const list = await screen.findByRole("generic", { name: "Customer list" });
    expect(within(list).getAllByRole("button").map((row) => row.textContent)).toEqual([
      "Alphaalpha@example.comactive", "alphaalpha@example.comactive", "Zuluzulu@example.comarchived"
    ]);
    expect(within(list).getAllByRole("button")[0]).toHaveAttribute("aria-pressed", "true");
    await waitFor(() => expect(api.fetchContacts).toHaveBeenCalledWith(1, expect.any(AbortSignal)));
    expect(api.fetchAddresses).toHaveBeenCalledWith(1, expect.any(AbortSignal));
    expect(screen.getByText("3 non-deleted customer(s)")).toBeInTheDocument();
    const detailHeadings = screen
      .getAllByRole("heading", { level: 2 })
      .map((heading) => heading.textContent);
    expect(detailHeadings.indexOf("Addresses")).toBeLessThan(
      detailHeadings.indexOf("Contacts")
    );

    await act(async () => { pendingContacts.resolve([]); pendingAddresses.resolve([]); });
  });

  it("renders list errors with retry and sends search/status without workspace ids", async () => {
    vi.mocked(api.fetchCustomers).mockRejectedValueOnce(new Error("Customers unavailable."));
    render(<CustomersTab />);
    expect(await screen.findByText("Customers unavailable.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    await screen.findByText("No customers match the current search.");

    fireEvent.change(screen.getByLabelText("Search name or email"), { target: { value: " Acme " } });
    fireEvent.change(screen.getByLabelText("Status"), { target: { value: "archived" } });
    await waitFor(() => expect(api.fetchCustomers).toHaveBeenLastCalledWith(expect.objectContaining({ q: " Acme ", status: "archived" })));
    expect(vi.mocked(api.fetchCustomers).mock.calls.flat().join(" ")).not.toContain("org-123");
  });

  it("trims customer writes, converts blank email to null and reconciles PUT results", async () => {
    const original = customer(1, "Alpha");
    vi.mocked(api.fetchCustomers).mockResolvedValue([original]);
    vi.mocked(api.createCustomer).mockResolvedValue(customer(2, "Beta"));
    vi.mocked(api.updateCustomer).mockResolvedValue({ ...original, name: "Alpha Prime", email: null, status: "archived" });
    render(<CustomersTab />);
    await screen.findByRole("button", { name: /Alpha/ });

    const createForm = screen.getByRole("form", { name: "Create customer" });
    fireEvent.change(within(createForm).getByLabelText("Name"), { target: { value: "  Beta  " } });
    fireEvent.change(within(createForm).getByLabelText("Email"), { target: { value: "   " } });
    fireEvent.submit(createForm);
    await waitFor(() => expect(api.createCustomer).toHaveBeenCalledWith({ name: "Beta", email: null }));
    expect(await screen.findByRole("button", { name: /Beta/ })).toHaveAttribute("aria-pressed", "true");

    const editForm = screen.getByRole("form", { name: "Edit customer" });
    fireEvent.change(within(editForm).getByLabelText("Name"), { target: { value: " Alpha Prime " } });
    fireEvent.change(within(editForm).getByLabelText("Email"), { target: { value: " " } });
    fireEvent.change(within(editForm).getByLabelText("Status"), { target: { value: "archived" } });
    fireEvent.submit(editForm);
    await waitFor(() => expect(api.updateCustomer).toHaveBeenCalledWith(2, { name: "Alpha Prime", email: null, status: "archived" }));
    expect(api.fetchCustomers).toHaveBeenCalledTimes(1);
  });

  it("normalizes contact and address writes and keeps successful children visible", async () => {
    vi.mocked(api.fetchCustomers).mockResolvedValue([customer(1, "Alpha")]);
    vi.mocked(api.fetchContacts).mockResolvedValue([contact(1, "Ada")]);
    vi.mocked(api.fetchAddresses).mockResolvedValue([address(1, "Office")]);
    vi.mocked(api.createContact).mockResolvedValue({ ...contact(2, "Grace"), email: null, phone: null, jobTitle: null });
    vi.mocked(api.createAddress).mockResolvedValue({ ...address(2, "Billing"), countryCode: "FI" });
    render(<CustomersTab />);
    const contactForm = await screen.findByRole("form", { name: "Create contact" });
    fireEvent.change(within(contactForm).getByLabelText("Name"), { target: { value: " Grace " } });
    fireEvent.change(within(contactForm).getByLabelText("Phone"), { target: { value: " " } });
    fireEvent.submit(contactForm);
    await waitFor(() => expect(api.createContact).toHaveBeenCalledWith(1, { name: "Grace", email: null, phone: null, jobTitle: null }));
    expect(await screen.findByRole("button", { name: /Grace/ })).toHaveAttribute("aria-pressed", "true");

    const addressForm = screen.getByRole("form", { name: "Create address" });
    expect(within(addressForm).getByLabelText("Country code")).toHaveValue("FI");
    fireEvent.change(within(addressForm).getByLabelText("Label"), { target: { value: " Billing " } });
    fireEvent.change(within(addressForm).getByLabelText("Address line 1"), { target: { value: " Main 2 " } });
    fireEvent.change(within(addressForm).getByLabelText("Country code"), { target: { value: "fi" } });
    fireEvent.submit(addressForm);
    await waitFor(() => expect(api.createAddress).toHaveBeenCalledWith(1, expect.objectContaining({ label: "Billing", addressLine1: "Main 2", countryCode: "FI", city: null })));
    expect(await screen.findByRole("button", { name: /Billing/ })).toHaveAttribute("aria-pressed", "true");
    expect(within(addressForm).getByLabelText("Country code")).toHaveValue("FI");
  });

  it("aborts child requests and clears their UI immediately when selection changes", async () => {
    vi.mocked(api.fetchCustomers).mockResolvedValue([customer(1, "Alpha"), customer(2, "Beta")]);
    const signals: AbortSignal[] = [];
    vi.mocked(api.fetchContacts).mockImplementation((_id, signal) => { if (signal) signals.push(signal); return new Promise(() => undefined); });
    vi.mocked(api.fetchAddresses).mockImplementation((_id, signal) => { if (signal) signals.push(signal); return new Promise(() => undefined); });
    render(<CustomersTab />);
    const beta = await screen.findByRole("button", { name: /Beta/ });
    await waitFor(() => expect(signals).toHaveLength(2));
    fireEvent.click(beta);
    expect(signals[0].aborted).toBe(true);
    expect(signals[1].aborted).toBe(true);
    await waitFor(() => expect(api.fetchContacts).toHaveBeenLastCalledWith(2, expect.any(AbortSignal)));
  });

  it("requires customer deletion confirmation and selects a deterministic fallback", async () => {
    vi.mocked(api.fetchCustomers).mockResolvedValue([customer(1, "Alpha"), customer(2, "Beta")]);
    vi.mocked(api.deleteCustomer).mockResolvedValue();
    render(<CustomersTab />);
    await screen.findByRole("button", { name: /Alpha/ });

    fireEvent.click(screen.getByRole("button", { name: "Delete customer" }));
    const dialog = screen.getByRole("alertdialog", { name: /Soft-delete Alpha/ });
    expect(dialog).toHaveTextContent("contacts and addresses");
    fireEvent.click(within(dialog).getByRole("button", { name: "Cancel deletion" }));
    expect(api.deleteCustomer).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Delete customer" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm delete customer" }));
    await waitFor(() => expect(api.deleteCustomer).toHaveBeenCalledWith(1));
    expect(await screen.findByRole("button", { name: /Beta/ })).toHaveAttribute("aria-pressed", "true");
    expect(screen.queryByRole("button", { name: /Alpha/ })).not.toBeInTheDocument();
  });

  it("keeps child load failures independent and retries the failed collection", async () => {
    vi.mocked(api.fetchCustomers).mockResolvedValue([customer(1, "Alpha")]);
    vi.mocked(api.fetchContacts).mockRejectedValueOnce(new Error("Contacts unavailable.")).mockResolvedValueOnce([]);
    vi.mocked(api.fetchAddresses).mockResolvedValue([]);
    render(<CustomersTab />);

    expect(await screen.findByText("Contacts unavailable.")).toBeInTheDocument();
    expect(screen.getByText("No addresses available.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("No contacts available.")).toBeInTheDocument();
    expect(api.fetchContacts).toHaveBeenCalledTimes(2);
    expect(api.fetchAddresses).toHaveBeenCalledTimes(1);
  });

  it("edits and confirms soft deletion for contacts and addresses with PUT reconciliation", async () => {
    vi.mocked(api.fetchCustomers).mockResolvedValue([customer(1, "Alpha")]);
    vi.mocked(api.fetchContacts).mockResolvedValue([contact(1, "Ada")]);
    vi.mocked(api.fetchAddresses).mockResolvedValue([address(1, "Office")]);
    vi.mocked(api.updateContact).mockResolvedValue({ ...contact(1, "Ada Lovelace"), email: "ada@example.com" });
    vi.mocked(api.updateAddress).mockResolvedValue({ ...address(1, "Head office"), countryCode: "SE" });
    vi.mocked(api.deleteContact).mockResolvedValue();
    vi.mocked(api.deleteAddress).mockResolvedValue();
    render(<CustomersTab />);

    await screen.findByRole("button", { name: /Ada/ });
    const editContact = screen.getByRole("form", { name: "Edit contact" });
    fireEvent.change(within(editContact).getByLabelText("Name"), { target: { value: " Ada Lovelace " } });
    fireEvent.change(within(editContact).getByLabelText("Email"), { target: { value: " ada@example.com " } });
    fireEvent.submit(editContact);
    await waitFor(() => expect(api.updateContact).toHaveBeenCalledWith(1, 1, {
      name: "Ada Lovelace", email: "ada@example.com", phone: null, jobTitle: null
    }));
    expect(await screen.findByRole("button", { name: /Ada Lovelace/ })).toBeVisible();

    const editAddress = screen.getByRole("form", { name: "Edit address" });
    fireEvent.change(within(editAddress).getByLabelText("Label"), { target: { value: " Head office " } });
    fireEvent.change(within(editAddress).getByLabelText("Country code"), { target: { value: "se" } });
    fireEvent.submit(editAddress);
    await waitFor(() => expect(api.updateAddress).toHaveBeenCalledWith(1, 1, expect.objectContaining({ label: "Head office", countryCode: "SE" })));

    fireEvent.click(within(editContact).getByRole("button", { name: "Delete contact" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm delete contact" }));
    await waitFor(() => expect(api.deleteContact).toHaveBeenCalledWith(1, 1));
    fireEvent.click(within(editAddress).getByRole("button", { name: "Delete address" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm delete address" }));
    await waitFor(() => expect(api.deleteAddress).toHaveBeenCalledWith(1, 1));
    expect(api.fetchContacts).toHaveBeenCalledTimes(1);
    expect(api.fetchAddresses).toHaveBeenCalledTimes(1);
  });

  it("does not allow customer list refreshes and mutations to overlap", async () => {
    const refresh = deferred<CustomerDto[]>();
    vi.mocked(api.fetchCustomers)
      .mockResolvedValueOnce([customer(1, "Alpha")])
      .mockReturnValueOnce(refresh.promise);
    render(<CustomersTab />);
    await screen.findByRole("button", { name: /Alpha/ });

    const createForm = screen.getByRole("form", { name: "Create customer" });
    fireEvent.change(within(createForm).getByLabelText("Name"), { target: { value: "Beta" } });
    fireEvent.click(screen.getByRole("button", { name: "Refresh" }));

    expect(within(createForm).getByRole("button", { name: "Create customer" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Save customer" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Search" })).toBeDisabled();
    expect(within(screen.getByRole("form", { name: "Search customers" })).getByLabelText("Status")).toBeDisabled();
    await act(async () => refresh.resolve([customer(1, "Alpha")]));
  });

  it("does not allow child refreshes and mutations to overlap", async () => {
    const contactRefresh = deferred<ContactDto[]>();
    const addressRefresh = deferred<AddressDto[]>();
    vi.mocked(api.fetchCustomers).mockResolvedValue([customer(1, "Alpha")]);
    vi.mocked(api.fetchContacts)
      .mockResolvedValueOnce([contact(1, "Ada")])
      .mockReturnValueOnce(contactRefresh.promise);
    vi.mocked(api.fetchAddresses)
      .mockResolvedValueOnce([address(1, "Office")])
      .mockReturnValueOnce(addressRefresh.promise);
    render(<CustomersTab />);
    const createContactForm = await screen.findByRole("form", { name: "Create contact" });
    const createAddressForm = screen.getByRole("form", { name: "Create address" });

    fireEvent.click(screen.getByRole("button", { name: "Refresh contacts" }));
    expect(within(createContactForm).getByLabelText("Name")).toBeDisabled();
    expect(screen.getByRole("button", { name: "Save contact" })).toBeDisabled();

    fireEvent.click(screen.getByRole("button", { name: "Refresh addresses" }));
    expect(within(createAddressForm).getByLabelText("Label")).toBeDisabled();
    expect(screen.getByRole("button", { name: "Save address" })).toBeDisabled();
    await act(async () => {
      contactRefresh.resolve([contact(1, "Ada")]);
      addressRefresh.resolve([address(1, "Office")]);
    });
  });

  it("shows mutation failures and prevents duplicate customer submissions", async () => {
    let rejectCreate!: (error: Error) => void;
    const pendingCreate = new Promise<CustomerDto>((_resolve, reject) => {
      rejectCreate = reject;
    });
    vi.mocked(api.fetchCustomers).mockResolvedValue([customer(1, "Alpha")]);
    vi.mocked(api.createCustomer).mockReturnValue(pendingCreate);
    vi.mocked(api.createContact).mockRejectedValue(new Error("Contact create failed."));
    vi.mocked(api.createAddress).mockRejectedValue(new Error("Address create failed."));
    render(<CustomersTab />);
    const createCustomerForm = await screen.findByRole("form", { name: "Create customer" });
    fireEvent.change(within(createCustomerForm).getByLabelText("Name"), { target: { value: "Beta" } });
    const createCustomerButton = within(createCustomerForm).getByRole("button", { name: "Create customer" });
    fireEvent.click(createCustomerButton);
    expect(within(createCustomerForm).getByRole("button", { name: "Saving..." })).toBeDisabled();
    fireEvent.click(within(createCustomerForm).getByRole("button", { name: "Saving..." }));
    expect(api.createCustomer).toHaveBeenCalledTimes(1);
    await act(async () => rejectCreate(new Error("Customer create failed.")));
    expect(await screen.findByText("Customer create failed.")).toBeInTheDocument();

    const createContactForm = screen.getByRole("form", { name: "Create contact" });
    fireEvent.change(within(createContactForm).getByLabelText("Name"), { target: { value: "Grace" } });
    fireEvent.submit(createContactForm);
    expect(await screen.findByText("Contact create failed.")).toBeInTheDocument();

    const createAddressForm = screen.getByRole("form", { name: "Create address" });
    fireEvent.change(within(createAddressForm).getByLabelText("Label"), { target: { value: "Billing" } });
    fireEvent.change(within(createAddressForm).getByLabelText("Address line 1"), { target: { value: "Main 2" } });
    fireEvent.submit(createAddressForm);
    expect(await screen.findByText("Address create failed.")).toBeInTheDocument();
  });

  it("ignores stale customer and child responses even when mocks resolve after abort", async () => {
    const oldCustomers = deferred<CustomerDto[]>();
    const currentCustomers = deferred<CustomerDto[]>();
    vi.mocked(api.fetchCustomers)
      .mockReturnValueOnce(oldCustomers.promise)
      .mockReturnValueOnce(currentCustomers.promise);
    const strictView = render(<StrictMode><CustomersTab /></StrictMode>);
    await act(async () => currentCustomers.resolve([customer(2, "Beta")]));
    expect(await screen.findByRole("button", { name: /Beta/ })).toBeVisible();
    await act(async () => oldCustomers.resolve([customer(1, "Alpha")]));
    expect(screen.queryByRole("button", { name: /Alpha/ })).not.toBeInTheDocument();
    strictView.unmount();

    const oldContacts = deferred<ContactDto[]>();
    const currentContacts = deferred<ContactDto[]>();
    const oldAddresses = deferred<AddressDto[]>();
    const currentAddresses = deferred<AddressDto[]>();
    vi.mocked(api.fetchCustomers).mockResolvedValue([customer(1, "Alpha"), customer(2, "Beta")]);
    vi.mocked(api.fetchContacts)
      .mockReturnValueOnce(oldContacts.promise)
      .mockReturnValueOnce(currentContacts.promise);
    vi.mocked(api.fetchAddresses)
      .mockReturnValueOnce(oldAddresses.promise)
      .mockReturnValueOnce(currentAddresses.promise);
    const view = render(<CustomersTab />);
    fireEvent.click(await screen.findByRole("button", { name: /Beta/ }));
    await act(async () => {
      currentContacts.resolve([contact(2, "Grace")]);
      currentAddresses.resolve([address(2, "Billing")]);
    });
    expect(await screen.findByRole("button", { name: /Grace/ })).toBeVisible();
    expect(await screen.findByRole("button", { name: /Billing/ })).toBeVisible();
    await act(async () => {
      oldContacts.resolve([contact(1, "Ada")]);
      oldAddresses.resolve([address(1, "Office")]);
    });
    expect(screen.queryByRole("button", { name: /Ada/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Office/ })).not.toBeInTheDocument();
    view.unmount();
  });

  it("aborts active customer and child list requests on unmount", async () => {
    let customerSignal: AbortSignal | undefined;
    vi.mocked(api.fetchCustomers).mockImplementation((options = {}) => {
      customerSignal = options.signal;
      return new Promise(() => undefined);
    });
    const customerView = render(<CustomersTab />);
    expect(customerSignal?.aborted).toBe(false);
    customerView.unmount();
    expect(customerSignal?.aborted).toBe(true);

    const signals: AbortSignal[] = [];
    vi.mocked(api.fetchCustomers).mockResolvedValue([customer(1, "Alpha")]);
    vi.mocked(api.fetchContacts).mockImplementation((_id, signal) => {
      if (signal) signals.push(signal);
      return new Promise(() => undefined);
    });
    vi.mocked(api.fetchAddresses).mockImplementation((_id, signal) => {
      if (signal) signals.push(signal);
      return new Promise(() => undefined);
    });
    const view = render(<CustomersTab />);
    await waitFor(() => expect(signals).toHaveLength(2));
    view.unmount();
    expect(signals.every((signal) => signal.aborted)).toBe(true);
  });
});

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => { resolve = done; });
  return { promise, resolve };
}
