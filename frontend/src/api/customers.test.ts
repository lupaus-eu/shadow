import { afterEach, describe, expect, it, vi } from "vitest";
import {
  createAddress,
  createContact,
  createCustomer,
  deleteAddress,
  deleteContact,
  deleteCustomer,
  fetchAddresses,
  fetchContacts,
  fetchCustomer,
  fetchCustomers,
  updateAddress,
  updateContact,
  updateCustomer
} from "./customers";

function jsonResponse(payload: unknown, init?: ResponseInit) {
  return new Response(JSON.stringify(payload), {
    status: 200,
    headers: { "Content-Type": "application/json" },
    ...init
  });
}

afterEach(() => vi.unstubAllGlobals());

describe("customers API", () => {
  it("encodes search and status without workspace context and forwards AbortSignal", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse([]));
    vi.stubGlobal("fetch", fetchMock);
    const controller = new AbortController();

    await fetchCustomers({ q: " Acme & Sons ", status: "archived", signal: controller.signal });

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/customers?q=Acme+%26+Sons&status=archived",
      expect.objectContaining({ method: "GET", signal: controller.signal })
    );
    expect(String(fetchMock.mock.calls[0][0])).not.toContain("organisation");
  });

  it("uses the complete customer POST, GET, PUT and DELETE contracts", async () => {
    const customer = { id: 7, name: "Acme", email: null, status: "active", createdAt: "x", updatedAt: "x" };
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse(customer))
      .mockResolvedValueOnce(jsonResponse(customer, { status: 201 }))
      .mockResolvedValueOnce(jsonResponse({ ...customer, status: "archived" }))
      .mockResolvedValueOnce(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);

    await fetchCustomer(7);
    await createCustomer({ name: "Acme", email: null });
    await updateCustomer(7, { name: "Acme", email: null, status: "archived" });
    await deleteCustomer(7);

    expect(fetchMock.mock.calls.map(([url, init]) => [url, (init as RequestInit).method])).toEqual([
      ["/api/v1/customers/7", "GET"],
      ["/api/v1/customers", "POST"],
      ["/api/v1/customers/7", "PUT"],
      ["/api/v1/customers/7", "DELETE"]
    ]);
  });

  it("uses nested contact and address paths and PUT replacements", async () => {
    const contact = { name: "Ada", email: null, phone: null, jobTitle: null };
    const address = { label: "Office", addressLine1: "Main 1", addressLine2: null, postalCode: null, city: null, region: null, countryCode: "FI" };
    const fetchMock = vi.fn()
      .mockImplementation(() => Promise.resolve(jsonResponse([])));
    vi.stubGlobal("fetch", fetchMock);

    await fetchContacts(7); await createContact(7, contact); await updateContact(7, 8, contact); await deleteContact(7, 8);
    await fetchAddresses(7); await createAddress(7, address); await updateAddress(7, 9, address); await deleteAddress(7, 9);

    expect(fetchMock.mock.calls.map(([url, init]) => [url, (init as RequestInit).method])).toEqual([
      ["/api/v1/customers/7/contacts", "GET"], ["/api/v1/customers/7/contacts", "POST"],
      ["/api/v1/customers/7/contacts/8", "PUT"], ["/api/v1/customers/7/contacts/8", "DELETE"],
      ["/api/v1/customers/7/addresses", "GET"], ["/api/v1/customers/7/addresses", "POST"],
      ["/api/v1/customers/7/addresses/9", "PUT"], ["/api/v1/customers/7/addresses/9", "DELETE"]
    ]);
  });

  it("turns FastAPI validation details into an actionable error", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(
      { detail: [{ msg: "Value must not be blank." }, { msg: "Invalid email." }] },
      { status: 422 }
    )));
    await expect(createCustomer({ name: "", email: null })).rejects.toThrow(
      "Failed to create customer (422): Value must not be blank. Invalid email."
    );
  });
});
