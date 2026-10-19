import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { SubmitEvent } from "react";
import {
  createAddress,
  createContact,
  createCustomer,
  deleteAddress,
  deleteContact,
  deleteCustomer,
  fetchAddresses,
  fetchContacts,
  fetchCustomers,
  updateAddress,
  updateContact,
  updateCustomer
} from "../../api/customers";
import type {
  AddressDto,
  AddressWriteRequest,
  ContactDto,
  ContactWriteRequest,
  CustomerDto,
  CustomerStatus
} from "../../api/customers";

const optional = (value: string) => value.trim() || null;
const errorMessage = (error: unknown) => (error instanceof Error ? error.message : "Unknown error");
const isAbort = (error: unknown) => (error as { name?: string } | null)?.name === "AbortError";

function sortedBy<T extends { id: number }>(items: T[], label: (item: T) => string) {
  return [...items].sort((left, right) => {
    const compared = label(left).localeCompare(label(right), undefined, {
      sensitivity: "base"
    });
    return compared || left.id - right.id;
  });
}

function ErrorAlert(props: {
  title?: string;
  message: string;
  retry?: () => void;
  busy?: boolean;
}) {
  if (!props.message) return null;
  return (
    <div className="alert alert--danger" role="alert">
      <p className="alert__title">{props.title ?? "Action error"}</p>
      <p className="alert__text">{props.message}</p>
      {props.retry ? (
        <div className="form-actions">
          <button
            className="btn btn--secondary btn--compact"
            type="button"
            onClick={props.retry}
            disabled={props.busy}
          >
            Retry
          </button>
        </div>
      ) : null}
    </div>
  );
}

export default function CustomersTab() {
  const [customers, setCustomers] = useState<CustomerDto[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const selectedIdRef = useRef<number | null>(null);
  const listController = useRef<AbortController | null>(null);
  const [loading, setLoading] = useState(false);
  const [listError, setListError] = useState("");
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState<CustomerStatus | "all">("all");
  const [mutating, setMutating] = useState(false);
  const [createName, setCreateName] = useState("");
  const [createEmail, setCreateEmail] = useState("");
  const [createError, setCreateError] = useState("");
  const [editName, setEditName] = useState("");
  const [editEmail, setEditEmail] = useState("");
  const [editStatus, setEditStatus] = useState<CustomerStatus>("active");
  const [actionError, setActionError] = useState("");
  const [confirmDelete, setConfirmDelete] = useState(false);

  const selected = useMemo(
    () => customers.find((customer) => customer.id === selectedId) ?? null,
    [customers, selectedId]
  );

  const selectCustomer = useCallback((customer: CustomerDto | null) => {
    selectedIdRef.current = customer?.id ?? null;
    setSelectedId(customer?.id ?? null);
    setEditName(customer?.name ?? "");
    setEditEmail(customer?.email ?? "");
    setEditStatus(customer?.status ?? "active");
    setActionError("");
    setConfirmDelete(false);
  }, []);

  const applyCustomers = useCallback(
    (items: CustomerDto[], preferred?: number | null) => {
      const sorted = sortedBy(items, (item) => item.name);
      setCustomers(sorted);
      const wanted = preferred === undefined ? selectedIdRef.current : preferred;
      selectCustomer(sorted.find((item) => item.id === wanted) ?? sorted[0] ?? null);
    },
    [selectCustomer]
  );

  const loadCustomers = useCallback(
    async (
      preferred: number | null | undefined,
      nextQuery: string,
      nextStatus: CustomerStatus | "all"
    ) => {
      listController.current?.abort();
      const controller = new AbortController();
      listController.current = controller;
      setLoading(true);
      setListError("");
      try {
        const items = await fetchCustomers({
          q: nextQuery,
          status: nextStatus === "all" ? undefined : nextStatus,
          signal: controller.signal
        });
        if (listController.current === controller) applyCustomers(items, preferred);
      } catch (error) {
        if (listController.current === controller && !isAbort(error))
          setListError(errorMessage(error));
      } finally {
        if (listController.current === controller) {
          listController.current = null;
          setLoading(false);
        }
      }
    },
    [applyCustomers]
  );

  useEffect(() => {
    async function loadInitialCustomers() {
      await loadCustomers(null, "", "all");
    }
    void loadInitialCustomers();
    return () => {
      listController.current?.abort();
      listController.current = null;
    };
  }, [loadCustomers]);

  async function submitCreate(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    const name = createName.trim();
    if (!name) return setCreateError("Customer name is required.");
    setMutating(true);
    setCreateError("");
    try {
      const created = await createCustomer({ name, email: optional(createEmail) });
      applyCustomers([...customers.filter((item) => item.id !== created.id), created], created.id);
      setCreateName("");
      setCreateEmail("");
    } catch (error) {
      setCreateError(errorMessage(error));
    } finally {
      setMutating(false);
    }
  }

  async function submitEdit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selected) return;
    const name = editName.trim();
    if (!name) return setActionError("Customer name is required.");
    setMutating(true);
    setActionError("");
    try {
      const updated = await updateCustomer(selected.id, {
        name,
        email: optional(editEmail),
        status: editStatus
      });
      applyCustomers([...customers.filter((item) => item.id !== updated.id), updated], updated.id);
    } catch (error) {
      setActionError(errorMessage(error));
    } finally {
      setMutating(false);
    }
  }

  async function confirmCustomerDelete() {
    if (!selected) return;
    setMutating(true);
    setActionError("");
    try {
      await deleteCustomer(selected.id);
      selectCustomer(null);
      applyCustomers(
        customers.filter((item) => item.id !== selected.id),
        null
      );
    } catch (error) {
      setActionError(errorMessage(error));
    } finally {
      setMutating(false);
    }
  }

  const editChanged = selected
    ? editName.trim() !== selected.name ||
      optional(editEmail) !== selected.email ||
      editStatus !== selected.status
    : false;
  const customerBusy = loading || mutating;

  return (
    <div className="management-tab customers-tab">
      <section className="tab-toolbar" aria-label="Customers overview">
        <div className="tab-toolbar__title">
          <h1 className="page-title">Customers</h1>
          <span className="tab-toolbar__count">{customers.length} non-deleted customer(s)</span>
        </div>
        <button
          className="btn btn--secondary"
          type="button"
          onClick={() => void loadCustomers(undefined, query, status)}
          disabled={loading || mutating}
        >
          {loading ? "Refreshing..." : "Refresh"}
        </button>
      </section>

      <div className="customer-layout">
        <aside className="main-detail-sidebar customer-sidebar" aria-label="Customer selection">
          <form
            className="field-stack"
            aria-label="Search customers"
            onSubmit={(event) => {
              event.preventDefault();
              void loadCustomers(undefined, query, status);
            }}
          >
            <label className="form-label" htmlFor="customer-search">
              Search name or email
            </label>
            <input
              id="customer-search"
              className="input"
              type="search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              disabled={customerBusy}
            />
            <label className="form-label" htmlFor="customer-status-filter">
              Status
            </label>
            <select
              id="customer-status-filter"
              className="select"
              value={status}
              disabled={customerBusy}
              onChange={(event) => {
                const value = event.target.value as CustomerStatus | "all";
                setStatus(value);
                void loadCustomers(undefined, query, value);
              }}
            >
              <option value="all">Active and archived</option>
              <option value="active">Active</option>
              <option value="archived">Archived</option>
            </select>
            <button
              className="btn btn--secondary btn--compact"
              type="submit"
              disabled={customerBusy}
            >
              Search
            </button>
          </form>
          {loading && customers.length === 0 ? <p className="muted">Loading customers...</p> : null}
          <ErrorAlert
            title="Customer list error"
            message={listError}
            retry={() => void loadCustomers(undefined, query, status)}
            busy={loading}
          />
          {!loading && !listError && customers.length === 0 ? (
            <p className="muted">No customers match the current search.</p>
          ) : null}
          <div className="entity-list" aria-label="Customer list">
            {customers.map((customer) => {
              const chosen = customer.id === selectedId;
              return (
                <button
                  key={customer.id}
                  className={`entity-row${chosen ? " entity-row--selected" : ""}`}
                  type="button"
                  aria-pressed={chosen}
                  onClick={() => selectCustomer(customer)}
                  disabled={customerBusy}
                >
                  <span className="entity-row__main">
                    <span className="entity-row__title">{customer.name}</span>
                    <span className="clamped-description">
                      {customer.email ?? `Customer ID ${customer.id}`}
                    </span>
                  </span>
                  <span
                    className={`badge ${customer.status === "active" ? "badge--accent" : "badge--neutral"}`}
                  >
                    {customer.status}
                  </span>
                </button>
              );
            })}
          </div>
        </aside>

        <section className="detail-workspace customer-workspace" aria-label="Customer management">
          <div className="detail-grid">
            <section className="detail-card" aria-labelledby="selected-customer-title">
              <div className="detail-card__header">
                <p className="eyebrow">Selected customer</p>
                <h2 id="selected-customer-title" className="section-title">
                  {selected?.name ?? "No customer selected"}
                </h2>
              </div>
              {selected ? (
                <>
                  <form aria-label="Edit customer" onSubmit={submitEdit}>
                    <CustomerFields
                      idPrefix="customer-edit"
                      name={editName}
                      email={editEmail}
                      disabled={customerBusy}
                      onName={setEditName}
                      onEmail={setEditEmail}
                    />
                    <label
                      className="form-label form-label--required"
                      htmlFor="customer-edit-status"
                    >
                      Status
                    </label>
                    <select
                      id="customer-edit-status"
                      className="select"
                      value={editStatus}
                      disabled={customerBusy}
                      onChange={(event) => setEditStatus(event.target.value as CustomerStatus)}
                    >
                      <option value="active">Active</option>
                      <option value="archived">Archived</option>
                    </select>
                    <ErrorAlert message={actionError} />
                    <div className="form-actions">
                      <button
                        className="btn btn--primary"
                        type="submit"
                        disabled={customerBusy || !editChanged}
                      >
                        {mutating ? "Saving..." : "Save customer"}
                      </button>
                    </div>
                  </form>
                  {!confirmDelete ? (
                    <div className="form-actions">
                      <button
                        className="btn btn--danger"
                        type="button"
                        disabled={customerBusy}
                        onClick={() => setConfirmDelete(true)}
                      >
                        Delete customer
                      </button>
                    </div>
                  ) : (
                    <div
                      className="delete-confirmation"
                      role="alertdialog"
                      aria-labelledby="delete-customer-confirmation"
                    >
                      <p id="delete-customer-confirmation">
                        Soft-delete {selected.name}? Its contacts and addresses will also be removed
                        from normal views.
                      </p>
                      <div className="form-actions">
                        <button
                          className="btn btn--secondary"
                          type="button"
                          disabled={customerBusy}
                          onClick={() => setConfirmDelete(false)}
                        >
                          Cancel deletion
                        </button>
                        <button
                          className="btn btn--danger"
                          type="button"
                          disabled={customerBusy}
                          onClick={() => void confirmCustomerDelete()}
                        >
                          {mutating ? "Deleting..." : "Confirm delete customer"}
                        </button>
                      </div>
                    </div>
                  )}
                </>
              ) : (
                <p className="muted">
                  Select a customer to manage its profile, contacts and addresses.
                </p>
              )}
            </section>

            <form className="detail-card" aria-label="Create customer" onSubmit={submitCreate}>
              <div className="detail-card__header">
                <h2 className="section-title">Create customer</h2>
              </div>
              <p className="muted">New customers are active.</p>
              <CustomerFields
                idPrefix="customer-create"
                name={createName}
                email={createEmail}
                disabled={customerBusy}
                onName={setCreateName}
                onEmail={setCreateEmail}
              />
              <ErrorAlert message={createError} />
              <div className="form-actions">
                <button
                  className="btn btn--primary"
                  type="submit"
                  disabled={customerBusy || !createName.trim()}
                >
                  {mutating ? "Saving..." : "Create customer"}
                </button>
              </div>
            </form>
          </div>
          {selected ? (
            <div className="customer-children" key={selected.id}>
              <AddressesPanel customerId={selected.id} />
              <ContactsPanel customerId={selected.id} />
            </div>
          ) : null}
        </section>
      </div>
    </div>
  );
}

function CustomerFields(props: {
  idPrefix: string;
  name: string;
  email: string;
  disabled: boolean;
  onName: (value: string) => void;
  onEmail: (value: string) => void;
}) {
  return (
    <div className="field-stack">
      <label className="form-label form-label--required" htmlFor={`${props.idPrefix}-name`}>
        Name
      </label>
      <input
        id={`${props.idPrefix}-name`}
        className="input"
        value={props.name}
        disabled={props.disabled}
        onChange={(event) => props.onName(event.target.value)}
      />
      <label className="form-label" htmlFor={`${props.idPrefix}-email`}>
        Email
      </label>
      <input
        id={`${props.idPrefix}-email`}
        className="input"
        type="email"
        value={props.email}
        disabled={props.disabled}
        onChange={(event) => props.onEmail(event.target.value)}
      />
    </div>
  );
}

const emptyContact = (): ContactWriteRequest => ({
  name: "",
  email: null,
  phone: null,
  jobTitle: null
});
function contactForm(contact?: ContactDto): ContactWriteRequest {
  return contact
    ? { name: contact.name, email: contact.email, phone: contact.phone, jobTitle: contact.jobTitle }
    : emptyContact();
}

function ContactsPanel({ customerId }: { customerId: number }) {
  const [items, setItems] = useState<ContactDto[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const selectedRef = useRef<number | null>(null);
  const controllerRef = useRef<AbortController | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [actionError, setActionError] = useState("");
  const [busy, setBusy] = useState(false);
  const [creating, setCreating] = useState<ContactWriteRequest>(emptyContact);
  const [editing, setEditing] = useState<ContactWriteRequest>(emptyContact);
  const [confirming, setConfirming] = useState(false);
  const selected = items.find((item) => item.id === selectedId) ?? null;
  const panelBusy = loading || busy;

  const apply = useCallback((next: ContactDto[], preferred?: number | null) => {
    const sorted = sortedBy(next, (item) => item.name);
    setItems(sorted);
    const wanted = preferred === undefined ? selectedRef.current : preferred;
    const chosen = sorted.find((item) => item.id === wanted) ?? sorted[0] ?? null;
    selectedRef.current = chosen?.id ?? null;
    setSelectedId(chosen?.id ?? null);
    setEditing(contactForm(chosen ?? undefined));
    setConfirming(false);
    setActionError("");
  }, []);

  const load = useCallback(async () => {
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;
    setLoading(true);
    setError("");
    try {
      const result = await fetchContacts(customerId, controller.signal);
      if (controllerRef.current === controller) apply(result);
    } catch (caught) {
      if (controllerRef.current === controller && !isAbort(caught)) setError(errorMessage(caught));
    } finally {
      if (controllerRef.current === controller) {
        controllerRef.current = null;
        setLoading(false);
      }
    }
  }, [apply, customerId]);

  useEffect(() => {
    async function loadInitialContacts() {
      await load();
    }
    void loadInitialContacts();
    return () => {
      controllerRef.current?.abort();
      controllerRef.current = null;
    };
  }, [load]);
  function choose(item: ContactDto) {
    selectedRef.current = item.id;
    setSelectedId(item.id);
    setEditing(contactForm(item));
    setActionError("");
    setConfirming(false);
  }
  const normalize = (value: ContactWriteRequest): ContactWriteRequest => ({
    name: value.name.trim(),
    email: optional(value.email ?? ""),
    phone: optional(value.phone ?? ""),
    jobTitle: optional(value.jobTitle ?? "")
  });

  async function create(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    const payload = normalize(creating);
    if (!payload.name) return setActionError("Contact name is required.");
    setBusy(true);
    setActionError("");
    try {
      const made = await createContact(customerId, payload);
      apply([...items.filter((item) => item.id !== made.id), made], made.id);
      setCreating(emptyContact());
    } catch (caught) {
      setActionError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  }
  async function edit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selected) return;
    const payload = normalize(editing);
    if (!payload.name) return setActionError("Contact name is required.");
    setBusy(true);
    setActionError("");
    try {
      const changed = await updateContact(customerId, selected.id, payload);
      apply([...items.filter((item) => item.id !== changed.id), changed], changed.id);
    } catch (caught) {
      setActionError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  }
  async function remove() {
    if (!selected) return;
    setBusy(true);
    setActionError("");
    try {
      await deleteContact(customerId, selected.id);
      apply(
        items.filter((item) => item.id !== selected.id),
        null
      );
    } catch (caught) {
      setActionError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="detail-card child-panel" aria-labelledby={`contacts-title-${customerId}`}>
      <div className="detail-card__header child-panel__heading">
        <div>
          <p className="eyebrow">Customer details</p>
          <h2 id={`contacts-title-${customerId}`} className="section-title">
            Contacts
          </h2>
        </div>
        <button
          className="btn btn--secondary btn--compact"
          type="button"
          onClick={() => void load()}
          disabled={loading || busy}
        >
          {loading ? "Loading..." : "Refresh contacts"}
        </button>
      </div>
      {loading && items.length === 0 ? <p className="muted">Loading contacts...</p> : null}
      <ErrorAlert
        title="Contact load error"
        message={error}
        retry={() => void load()}
        busy={loading}
      />
      {!loading && !error && items.length === 0 ? (
        <p className="muted">No contacts available.</p>
      ) : null}
      <div className="entity-list child-list" aria-label="Contact list">
        {items.map((item) => (
          <button
            key={item.id}
            type="button"
            className={`entity-row${selectedId === item.id ? " entity-row--selected" : ""}`}
            aria-pressed={selectedId === item.id}
            disabled={panelBusy}
            onClick={() => choose(item)}
          >
            <span className="entity-row__main">
              <span className="entity-row__title">{item.name}</span>
              <span className="clamped-description">
                {item.email ?? item.phone ?? `Contact ID ${item.id}`}
              </span>
            </span>
          </button>
        ))}
      </div>
      <ErrorAlert message={actionError} />
      <div className="child-forms">
        <form aria-label="Create contact" onSubmit={create}>
          <h3>Create contact</h3>
          <ContactFields
            prefix={`contact-create-${customerId}`}
            value={creating}
            disabled={panelBusy}
            onChange={setCreating}
          />
          <div className="form-actions">
            <button
              className="btn btn--primary"
              type="submit"
              disabled={panelBusy || !creating.name.trim()}
            >
              {busy ? "Saving..." : "Create contact"}
            </button>
          </div>
        </form>
        <form aria-label="Edit contact" onSubmit={edit}>
          <h3>Edit contact</h3>
          {selected ? (
            <>
              <ContactFields
                prefix={`contact-edit-${customerId}`}
                value={editing}
                disabled={panelBusy}
                onChange={setEditing}
              />
              <div className="form-actions">
                <button className="btn btn--primary" type="submit" disabled={panelBusy}>
                  Save contact
                </button>
                {!confirming ? (
                  <button
                    className="btn btn--danger"
                    type="button"
                    disabled={panelBusy}
                    onClick={() => setConfirming(true)}
                  >
                    Delete contact
                  </button>
                ) : null}
              </div>
              {confirming ? (
                <DeleteConfirm
                  id={`delete-contact-${customerId}`}
                  text={`Soft-delete ${selected.name}?`}
                  busy={panelBusy}
                  cancel={() => setConfirming(false)}
                  confirm={() => void remove()}
                  label="contact"
                />
              ) : null}
            </>
          ) : (
            <p className="muted">Select a contact to edit it.</p>
          )}
        </form>
      </div>
    </section>
  );
}

function ContactFields(props: {
  prefix: string;
  value: ContactWriteRequest;
  disabled: boolean;
  onChange: (value: ContactWriteRequest) => void;
}) {
  const field = (key: keyof ContactWriteRequest, value: string) =>
    props.onChange({ ...props.value, [key]: value });
  return (
    <div className="field-stack">
      <label className="form-label form-label--required" htmlFor={`${props.prefix}-name`}>
        Name
      </label>
      <input
        className="input"
        id={`${props.prefix}-name`}
        value={props.value.name}
        disabled={props.disabled}
        onChange={(e) => field("name", e.target.value)}
      />
      <label className="form-label" htmlFor={`${props.prefix}-email`}>
        Email
      </label>
      <input
        className="input"
        type="email"
        id={`${props.prefix}-email`}
        value={props.value.email ?? ""}
        disabled={props.disabled}
        onChange={(e) => field("email", e.target.value)}
      />
      <label className="form-label" htmlFor={`${props.prefix}-phone`}>
        Phone
      </label>
      <input
        className="input"
        type="tel"
        id={`${props.prefix}-phone`}
        value={props.value.phone ?? ""}
        disabled={props.disabled}
        onChange={(e) => field("phone", e.target.value)}
      />
      <label className="form-label" htmlFor={`${props.prefix}-job-title`}>
        Job title
      </label>
      <input
        className="input"
        id={`${props.prefix}-job-title`}
        value={props.value.jobTitle ?? ""}
        disabled={props.disabled}
        onChange={(e) => field("jobTitle", e.target.value)}
      />
    </div>
  );
}

const emptyAddress = (): AddressWriteRequest => ({
  label: "",
  addressLine1: "",
  addressLine2: null,
  postalCode: null,
  city: null,
  region: null,
  countryCode: "FI"
});
function addressForm(address?: AddressDto): AddressWriteRequest {
  return address
    ? {
        label: address.label,
        addressLine1: address.addressLine1,
        addressLine2: address.addressLine2,
        postalCode: address.postalCode,
        city: address.city,
        region: address.region,
        countryCode: address.countryCode
      }
    : emptyAddress();
}

function AddressesPanel({ customerId }: { customerId: number }) {
  const [items, setItems] = useState<AddressDto[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const selectedRef = useRef<number | null>(null);
  const controllerRef = useRef<AbortController | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [actionError, setActionError] = useState("");
  const [busy, setBusy] = useState(false);
  const [creating, setCreating] = useState<AddressWriteRequest>(emptyAddress);
  const [editing, setEditing] = useState<AddressWriteRequest>(emptyAddress);
  const [confirming, setConfirming] = useState(false);
  const selected = items.find((item) => item.id === selectedId) ?? null;
  const panelBusy = loading || busy;
  const apply = useCallback((next: AddressDto[], preferred?: number | null) => {
    const sorted = sortedBy(next, (item) => item.label);
    setItems(sorted);
    const wanted = preferred === undefined ? selectedRef.current : preferred;
    const chosen = sorted.find((item) => item.id === wanted) ?? sorted[0] ?? null;
    selectedRef.current = chosen?.id ?? null;
    setSelectedId(chosen?.id ?? null);
    setEditing(addressForm(chosen ?? undefined));
    setConfirming(false);
    setActionError("");
  }, []);
  const load = useCallback(async () => {
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;
    setLoading(true);
    setError("");
    try {
      const result = await fetchAddresses(customerId, controller.signal);
      if (controllerRef.current === controller) apply(result);
    } catch (caught) {
      if (controllerRef.current === controller && !isAbort(caught)) setError(errorMessage(caught));
    } finally {
      if (controllerRef.current === controller) {
        controllerRef.current = null;
        setLoading(false);
      }
    }
  }, [apply, customerId]);
  useEffect(() => {
    async function loadInitialAddresses() {
      await load();
    }
    void loadInitialAddresses();
    return () => {
      controllerRef.current?.abort();
      controllerRef.current = null;
    };
  }, [load]);
  function choose(item: AddressDto) {
    selectedRef.current = item.id;
    setSelectedId(item.id);
    setEditing(addressForm(item));
    setActionError("");
    setConfirming(false);
  }
  const normalize = (value: AddressWriteRequest): AddressWriteRequest => ({
    label: value.label.trim(),
    addressLine1: value.addressLine1.trim(),
    addressLine2: optional(value.addressLine2 ?? ""),
    postalCode: optional(value.postalCode ?? ""),
    city: optional(value.city ?? ""),
    region: optional(value.region ?? ""),
    countryCode: value.countryCode.trim().toUpperCase()
  });
  function validate(payload: AddressWriteRequest) {
    if (!payload.label) return "Address label is required.";
    if (!payload.addressLine1) return "Address line 1 is required.";
    if (!payload.countryCode) return "Country code is required.";
    return "";
  }
  async function create(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    const payload = normalize(creating);
    const validation = validate(payload);
    if (validation) return setActionError(validation);
    setBusy(true);
    setActionError("");
    try {
      const made = await createAddress(customerId, payload);
      apply([...items.filter((item) => item.id !== made.id), made], made.id);
      setCreating(emptyAddress());
    } catch (caught) {
      setActionError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  }
  async function edit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selected) return;
    const payload = normalize(editing);
    const validation = validate(payload);
    if (validation) return setActionError(validation);
    setBusy(true);
    setActionError("");
    try {
      const changed = await updateAddress(customerId, selected.id, payload);
      apply([...items.filter((item) => item.id !== changed.id), changed], changed.id);
    } catch (caught) {
      setActionError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  }
  async function remove() {
    if (!selected) return;
    setBusy(true);
    setActionError("");
    try {
      await deleteAddress(customerId, selected.id);
      apply(
        items.filter((item) => item.id !== selected.id),
        null
      );
    } catch (caught) {
      setActionError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="detail-card child-panel" aria-labelledby={`addresses-title-${customerId}`}>
      <div className="detail-card__header child-panel__heading">
        <div>
          <p className="eyebrow">Customer details</p>
          <h2 id={`addresses-title-${customerId}`} className="section-title">
            Addresses
          </h2>
        </div>
        <button
          className="btn btn--secondary btn--compact"
          type="button"
          onClick={() => void load()}
          disabled={panelBusy}
        >
          {loading ? "Loading..." : "Refresh addresses"}
        </button>
      </div>
      {loading && items.length === 0 ? <p className="muted">Loading addresses...</p> : null}
      <ErrorAlert
        title="Address load error"
        message={error}
        retry={() => void load()}
        busy={loading}
      />
      {!loading && !error && items.length === 0 ? (
        <p className="muted">No addresses available.</p>
      ) : null}
      <div className="entity-list child-list" aria-label="Address list">
        {items.map((item) => (
          <button
            key={item.id}
            type="button"
            className={`entity-row${selectedId === item.id ? " entity-row--selected" : ""}`}
            aria-pressed={selectedId === item.id}
            disabled={panelBusy}
            onClick={() => choose(item)}
          >
            <span className="entity-row__main">
              <span className="entity-row__title">{item.label}</span>
              <span className="clamped-description">
                {[item.addressLine1, item.city, item.countryCode].filter(Boolean).join(", ")}
              </span>
            </span>
          </button>
        ))}
      </div>
      <ErrorAlert message={actionError} />
      <div className="child-forms">
        <form aria-label="Create address" onSubmit={create}>
          <h3>Create address</h3>
          <AddressFields
            prefix={`address-create-${customerId}`}
            value={creating}
            disabled={panelBusy}
            onChange={setCreating}
          />
          <div className="form-actions">
            <button
              className="btn btn--primary"
              type="submit"
              disabled={
                panelBusy ||
                !creating.label.trim() ||
                !creating.addressLine1.trim() ||
                !creating.countryCode.trim()
              }
            >
              {busy ? "Saving..." : "Create address"}
            </button>
          </div>
        </form>
        <form aria-label="Edit address" onSubmit={edit}>
          <h3>Edit address</h3>
          {selected ? (
            <>
              <AddressFields
                prefix={`address-edit-${customerId}`}
                value={editing}
                disabled={panelBusy}
                onChange={setEditing}
              />
              <div className="form-actions">
                <button className="btn btn--primary" type="submit" disabled={panelBusy}>
                  Save address
                </button>
                {!confirming ? (
                  <button
                    className="btn btn--danger"
                    type="button"
                    disabled={panelBusy}
                    onClick={() => setConfirming(true)}
                  >
                    Delete address
                  </button>
                ) : null}
              </div>
              {confirming ? (
                <DeleteConfirm
                  id={`delete-address-${customerId}`}
                  text={`Soft-delete ${selected.label}?`}
                  busy={panelBusy}
                  cancel={() => setConfirming(false)}
                  confirm={() => void remove()}
                  label="address"
                />
              ) : null}
            </>
          ) : (
            <p className="muted">Select an address to edit it.</p>
          )}
        </form>
      </div>
    </section>
  );
}

function AddressFields(props: {
  prefix: string;
  value: AddressWriteRequest;
  disabled: boolean;
  onChange: (value: AddressWriteRequest) => void;
}) {
  const field = (key: keyof AddressWriteRequest, value: string) =>
    props.onChange({ ...props.value, [key]: value });
  const fields: {
    key: keyof AddressWriteRequest;
    label: string;
    required?: boolean;
    maxLength?: number;
  }[] = [
    { key: "label", label: "Label", required: true },
    { key: "addressLine1", label: "Address line 1", required: true },
    { key: "addressLine2", label: "Address line 2" },
    { key: "postalCode", label: "Postal code" },
    { key: "city", label: "City" },
    { key: "region", label: "Region" },
    { key: "countryCode", label: "Country code", required: true, maxLength: 2 }
  ];
  return (
    <div className="field-stack">
      {fields.map((item) => (
        <span className="field-stack" key={item.key}>
          <label
            className={`form-label${item.required ? " form-label--required" : ""}`}
            htmlFor={`${props.prefix}-${item.key}`}
          >
            {item.label}
          </label>
          <input
            className="input"
            id={`${props.prefix}-${item.key}`}
            value={props.value[item.key] ?? ""}
            maxLength={item.maxLength}
            disabled={props.disabled}
            onChange={(event) =>
              field(
                item.key,
                item.key === "countryCode" ? event.target.value.toUpperCase() : event.target.value
              )
            }
          />
        </span>
      ))}
    </div>
  );
}

function DeleteConfirm(props: {
  id: string;
  text: string;
  busy: boolean;
  cancel: () => void;
  confirm: () => void;
  label: string;
}) {
  return (
    <div className="delete-confirmation" role="alertdialog" aria-labelledby={props.id}>
      <p id={props.id}>{props.text}</p>
      <div className="form-actions">
        <button
          className="btn btn--secondary"
          type="button"
          onClick={props.cancel}
          disabled={props.busy}
        >
          Cancel deletion
        </button>
        <button
          className="btn btn--danger"
          type="button"
          onClick={props.confirm}
          disabled={props.busy}
        >
          {props.busy ? "Deleting..." : `Confirm delete ${props.label}`}
        </button>
      </div>
    </div>
  );
}
