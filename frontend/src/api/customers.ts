import { authenticatedFetch } from "./client";

export type CustomerStatus = "active" | "archived";

export type CustomerDto = {
  id: number;
  name: string;
  email: string | null;
  status: CustomerStatus;
  createdAt: string;
  updatedAt: string;
};

export type ContactDto = {
  id: number;
  name: string;
  email: string | null;
  phone: string | null;
  jobTitle: string | null;
  createdAt: string;
  updatedAt: string;
};

export type AddressDto = {
  id: number;
  label: string;
  addressLine1: string;
  addressLine2: string | null;
  postalCode: string | null;
  city: string | null;
  region: string | null;
  countryCode: string;
  createdAt: string;
  updatedAt: string;
};

export type CustomerCreateRequest = Pick<CustomerDto, "name" | "email">;
export type CustomerUpdateRequest = Pick<
  CustomerDto,
  "name" | "email" | "status"
>;
export type ContactWriteRequest = Pick<
  ContactDto,
  "name" | "email" | "phone" | "jobTitle"
>;
export type AddressWriteRequest = Pick<
  AddressDto,
  | "label"
  | "addressLine1"
  | "addressLine2"
  | "postalCode"
  | "city"
  | "region"
  | "countryCode"
>;

export type CustomerListOptions = {
  q?: string;
  status?: CustomerStatus;
  signal?: AbortSignal;
};

const customersPath = "/api/v1/customers";

function messageFromPayload(payload: unknown): string {
  if (!payload || typeof payload !== "object") return "";
  const detail = (payload as { detail?: unknown }).detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item) =>
        item && typeof item === "object" &&
        typeof (item as { msg?: unknown }).msg === "string"
          ? String((item as { msg: string }).msg)
          : ""
      )
      .filter(Boolean)
      .join(" ");
  }
  const error = (payload as { error?: unknown }).error;
  return error && typeof error === "object" &&
    typeof (error as { message?: unknown }).message === "string"
    ? String((error as { message: string }).message)
    : "";
}

async function responseErrorMessage(response: Response, action: string) {
  const text = await response.text().catch(() => "");
  let detail = text;
  if (text) {
    try {
      detail = messageFromPayload(JSON.parse(text)) || text;
    } catch {
      // Keep a non-JSON response as useful diagnostic context.
    }
  }
  return detail
    ? `Failed to ${action} (${response.status}): ${detail}`
    : `Failed to ${action} (${response.status}).`;
}

async function requestJson<T>(
  path: string,
  action: string,
  init: RequestInit,
  signal?: AbortSignal
): Promise<T> {
  const response = await authenticatedFetch(path, {
    ...init,
    headers: {
      Accept: "application/json",
      ...(init.body ? { "Content-Type": "application/json" } : {}),
      ...init.headers
    },
  }, signal);
  if (!response.ok) throw new Error(await responseErrorMessage(response, action));
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

function customerPath(customerId: number) {
  return `${customersPath}/${encodeURIComponent(String(customerId))}`;
}

function contactsPath(customerId: number) {
  return `${customerPath(customerId)}/contacts`;
}

function contactPath(customerId: number, contactId: number) {
  return `${contactsPath(customerId)}/${encodeURIComponent(String(contactId))}`;
}

function addressesPath(customerId: number) {
  return `${customerPath(customerId)}/addresses`;
}

function addressPath(customerId: number, addressId: number) {
  return `${addressesPath(customerId)}/${encodeURIComponent(String(addressId))}`;
}

export function fetchCustomers(options: CustomerListOptions = {}) {
  const parameters = new URLSearchParams();
  const query = options.q?.trim();
  if (query) parameters.set("q", query);
  if (options.status) parameters.set("status", options.status);
  const queryString = parameters.toString();
  return requestJson<CustomerDto[]>(
    `${customersPath}${queryString ? `?${queryString}` : ""}`,
    "fetch customers",
    { method: "GET" },
    options.signal
  );
}

export function fetchCustomer(customerId: number, signal?: AbortSignal) {
  return requestJson<CustomerDto>(customerPath(customerId), "fetch customer", { method: "GET" }, signal);
}

export function createCustomer(payload: CustomerCreateRequest, signal?: AbortSignal) {
  return requestJson<CustomerDto>(customersPath, "create customer", { method: "POST", body: JSON.stringify(payload) }, signal);
}

export function updateCustomer(customerId: number, payload: CustomerUpdateRequest, signal?: AbortSignal) {
  return requestJson<CustomerDto>(customerPath(customerId), "update customer", { method: "PUT", body: JSON.stringify(payload) }, signal);
}

export function deleteCustomer(customerId: number, signal?: AbortSignal) {
  return requestJson<void>(customerPath(customerId), "delete customer", { method: "DELETE" }, signal);
}

export function fetchContacts(customerId: number, signal?: AbortSignal) {
  return requestJson<ContactDto[]>(contactsPath(customerId), "fetch contacts", { method: "GET" }, signal);
}

export function createContact(customerId: number, payload: ContactWriteRequest, signal?: AbortSignal) {
  return requestJson<ContactDto>(contactsPath(customerId), "create contact", { method: "POST", body: JSON.stringify(payload) }, signal);
}

export function updateContact(customerId: number, contactId: number, payload: ContactWriteRequest, signal?: AbortSignal) {
  return requestJson<ContactDto>(contactPath(customerId, contactId), "update contact", { method: "PUT", body: JSON.stringify(payload) }, signal);
}

export function deleteContact(customerId: number, contactId: number, signal?: AbortSignal) {
  return requestJson<void>(contactPath(customerId, contactId), "delete contact", { method: "DELETE" }, signal);
}

export function fetchAddresses(customerId: number, signal?: AbortSignal) {
  return requestJson<AddressDto[]>(addressesPath(customerId), "fetch addresses", { method: "GET" }, signal);
}

export function createAddress(customerId: number, payload: AddressWriteRequest, signal?: AbortSignal) {
  return requestJson<AddressDto>(addressesPath(customerId), "create address", { method: "POST", body: JSON.stringify(payload) }, signal);
}

export function updateAddress(customerId: number, addressId: number, payload: AddressWriteRequest, signal?: AbortSignal) {
  return requestJson<AddressDto>(addressPath(customerId, addressId), "update address", { method: "PUT", body: JSON.stringify(payload) }, signal);
}

export function deleteAddress(customerId: number, addressId: number, signal?: AbortSignal) {
  return requestJson<void>(addressPath(customerId, addressId), "delete address", { method: "DELETE" }, signal);
}
