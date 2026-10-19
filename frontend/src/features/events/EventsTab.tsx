import { useCallback, useEffect, useMemo, useState } from "react";
import type { SubmitEvent } from "react";
import { createEvent, deleteEvent, fetchEvents, updateEvent } from "../../api/events";
import type { EventDto } from "../../api/events";
import { useWorkspaceSelection } from "../../workspace/WorkspaceSelectionContext";

function sortEvents(items: EventDto[]): EventDto[] {
  return [...items].sort((a, b) => {
    const dateComparison = a.targetDate.localeCompare(b.targetDate);
    if (dateComparison !== 0) return dateComparison;
    return a.name.localeCompare(b.name);
  });
}

function eventRowKey(event: EventDto, index: number): string {
  return `${event.id || "event"}:${event.targetDate}:${index}`;
}

function messageFromError(error: unknown): string {
  return error instanceof Error ? error.message : "Unknown error";
}

function eventCountText(count: number): string {
  return `${count} event(s)`;
}

function todayDateValue(): string {
  const today = new Date();
  const year = today.getFullYear();
  const month = String(today.getMonth() + 1).padStart(2, "0");
  const day = String(today.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function eventStatus(targetDate: string, today: string): "past" | "upcoming" {
  return targetDate < today ? "past" : "upcoming";
}

export default function EventsTab(props: { orgId: string }) {
  const { selectedScenario } = useWorkspaceSelection();
  const [events, setEvents] = useState<EventDto[]>([]);
  const [selectedEventId, setSelectedEventId] = useState<string | null>(null);
  const [loadingEvents, setLoadingEvents] = useState(false);
  const [eventsError, setEventsError] = useState("");
  const [saving, setSaving] = useState(false);

  const [createName, setCreateName] = useState("");
  const [createTargetDate, setCreateTargetDate] = useState(todayDateValue);
  const [createDetails, setCreateDetails] = useState("");
  const [createError, setCreateError] = useState("");

  const [editName, setEditName] = useState("");
  const [editTargetDate, setEditTargetDate] = useState("");
  const [editDetails, setEditDetails] = useState("");
  const [actionError, setActionError] = useState("");

  const selectedEvent = useMemo(
    () => events.find((event) => event.id === selectedEventId) ?? null,
    [events, selectedEventId]
  );

  const applySelectedEvent = useCallback((event: EventDto | null) => {
    setSelectedEventId(event?.id ?? null);
    setEditName(event?.name ?? "");
    setEditTargetDate(event?.targetDate ?? "");
    setEditDetails(event?.eventDetails ?? "");
    setActionError("");
  }, []);

  const loadEvents = useCallback(
    async (preferredEventId?: string | null, signal?: AbortSignal) => {
      if (!selectedScenario) {
        setEvents([]);
        applySelectedEvent(null);
        return;
      }

      try {
        setLoadingEvents(true);
        setEventsError("");
        const items = sortEvents(await fetchEvents(props.orgId, selectedScenario.id, signal));
        setEvents(items);
        const preferredEvent = preferredEventId
          ? items.find((event) => event.id === preferredEventId)
          : null;
        applySelectedEvent(preferredEvent ?? items[0] ?? null);
      } catch (error) {
        const err = error as { name?: string };
        if (err.name === "AbortError") return;
        setEventsError(messageFromError(error));
        setEvents([]);
        applySelectedEvent(null);
      } finally {
        setLoadingEvents(false);
      }
    },
    [applySelectedEvent, props.orgId, selectedScenario]
  );

  useEffect(() => {
    const ac = new AbortController();
    let ignore = false;
    const scenarioId = selectedScenario?.id;

    if (!scenarioId) return () => ac.abort();
    const activeScenarioId = scenarioId;

    async function loadScenarioEvents() {
      try {
        setLoadingEvents(true);
        setEventsError("");
        const items = sortEvents(await fetchEvents(props.orgId, activeScenarioId, ac.signal));
        if (ignore) return;
        setEvents(items);
        applySelectedEvent(items[0] ?? null);
      } catch (error) {
        const err = error as { name?: string };
        if (ignore || err.name === "AbortError") return;
        setEventsError(messageFromError(error));
        setEvents([]);
        applySelectedEvent(null);
      } finally {
        if (!ignore) setLoadingEvents(false);
      }
    }

    void loadScenarioEvents();

    return () => {
      ignore = true;
      ac.abort();
    };
  }, [applySelectedEvent, props.orgId, selectedScenario]);

  function selectEvent(event: EventDto) {
    applySelectedEvent(event);
  }

  async function onRefreshEvents() {
    await loadEvents(selectedEventId);
  }

  async function onCreateSubmit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedScenario) return;

    const name = createName.trim();
    if (!name) {
      setCreateError("Event name is required.");
      return;
    }
    if (!createTargetDate) {
      setCreateError("Target date is required.");
      return;
    }

    try {
      setSaving(true);
      setCreateError("");
      const created = await createEvent(props.orgId, selectedScenario.id, {
        name,
        targetDate: createTargetDate,
        eventDetails: createDetails.trim()
      });
      setCreateName("");
      setCreateTargetDate(todayDateValue());
      setCreateDetails("");
      await loadEvents(created.id);
    } catch (error) {
      setCreateError(messageFromError(error));
    } finally {
      setSaving(false);
    }
  }

  async function onEditSubmit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedScenario || !selectedEvent) return;

    const name = editName.trim();
    if (!name) {
      setActionError("Event name is required.");
      return;
    }
    if (!editTargetDate) {
      setActionError("Target date is required.");
      return;
    }

    try {
      setSaving(true);
      setActionError("");
      const updated = await updateEvent(props.orgId, selectedScenario.id, selectedEvent.id, {
        name,
        targetDate: editTargetDate,
        eventDetails: editDetails.trim()
      });
      await loadEvents(updated.id);
    } catch (error) {
      setActionError(messageFromError(error));
    } finally {
      setSaving(false);
    }
  }

  async function onDeleteEvent() {
    if (!selectedScenario || !selectedEvent) return;

    try {
      setSaving(true);
      setActionError("");
      await deleteEvent(props.orgId, selectedScenario.id, selectedEvent.id);
      await loadEvents(null);
    } catch (error) {
      setActionError(messageFromError(error));
    } finally {
      setSaving(false);
    }
  }

  const refreshDisabled = loadingEvents || !selectedScenario;
  const today = todayDateValue();

  return (
    <div className="management-tab">
      <section className="tab-toolbar" aria-label="Events overview">
        <div className="tab-toolbar__title">
          <h1 className="page-title">Events</h1>
          <span className="tab-toolbar__count">{eventCountText(events.length)}</span>
        </div>
        <button
          className="btn btn--secondary"
          type="button"
          onClick={() => void onRefreshEvents()}
          disabled={refreshDisabled}
        >
          {loadingEvents ? "Refreshing..." : "Refresh"}
        </button>
      </section>

      <div className="main-detail-layout">
        <aside className="main-detail-sidebar" aria-label="Event selection">
          <section className="sidebar-section">
            <h3 className="secondary-title">Events</h3>
            {selectedScenario ? (
              <p className="muted">{selectedScenario.name}</p>
            ) : (
              <p className="muted">Select a scenario in Scenarios first.</p>
            )}
            {loadingEvents ? <p className="muted">Loading events...</p> : null}
            {eventsError ? (
              <div className="alert alert--danger" role="alert">
                <p className="alert__title">Event API error</p>
                <p className="alert__text">{eventsError}</p>
              </div>
            ) : null}
            {!loadingEvents && !eventsError && events.length === 0 ? (
              <p className="muted">No events available.</p>
            ) : null}
            <div className="entity-list" aria-label="Event list">
              {events.map((event, index) => {
                const isSelected = event.id === selectedEventId;
                const status = eventStatus(event.targetDate, today);
                return (
                  <button
                    key={eventRowKey(event, index)}
                    className={`entity-row event-row${isSelected ? " entity-row--selected" : ""}`}
                    type="button"
                    onClick={() => selectEvent(event)}
                    aria-pressed={isSelected}
                  >
                    <span className="event-row__meta">
                      <span className={`event-status event-status--${status}`}>
                        {status === "past" ? "Past" : "Upcoming"}
                      </span>
                      <span className="entity-row__date">{event.targetDate}</span>
                    </span>
                    <span className="entity-row__title event-row__title">{event.name}</span>
                    <span className="clamped-description event-row__description">
                      {event.eventDetails || "No details"}
                    </span>
                  </button>
                );
              })}
            </div>
          </section>
        </aside>

        <section className="detail-workspace" aria-label="Selected event">
          <div className="detail-grid">
            <EventDetail
              scenarioName={selectedScenario?.name ?? ""}
              event={selectedEvent}
              editName={editName}
              editTargetDate={editTargetDate}
              editDetails={editDetails}
              error={actionError}
              saving={saving}
              onEditNameChange={setEditName}
              onEditTargetDateChange={setEditTargetDate}
              onEditDetailsChange={setEditDetails}
              onEditSubmit={onEditSubmit}
              onDelete={onDeleteEvent}
            />
            <CreateEventForm
              scenarioName={selectedScenario?.name ?? ""}
              name={createName}
              targetDate={createTargetDate}
              details={createDetails}
              error={createError}
              saving={saving}
              disabled={!selectedScenario}
              onNameChange={setCreateName}
              onTargetDateChange={setCreateTargetDate}
              onDetailsChange={setCreateDetails}
              onSubmit={onCreateSubmit}
            />
          </div>
        </section>
      </div>
    </div>
  );
}

function EventDetail(props: {
  scenarioName: string;
  event: EventDto | null;
  editName: string;
  editTargetDate: string;
  editDetails: string;
  error: string;
  saving: boolean;
  onEditNameChange: (value: string) => void;
  onEditTargetDateChange: (value: string) => void;
  onEditDetailsChange: (value: string) => void;
  onEditSubmit: (event: SubmitEvent<HTMLFormElement>) => void;
  onDelete: () => Promise<void>;
}) {
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const editedEventName = props.editName.trim();
  const editedEventDetails = props.editDetails.trim();
  const eventHasChanges = props.event
    ? editedEventName !== props.event.name ||
      editedEventDetails !== props.event.eventDetails ||
      props.editTargetDate !== props.event.targetDate
    : false;
  const saveDisabled =
    !props.event || !editedEventName || !props.editTargetDate || !eventHasChanges;

  async function confirmDelete() {
    await props.onDelete();
    setConfirmingDelete(false);
  }

  return (
    <section className="detail-card" aria-labelledby="selected-event-title">
      <div className="detail-card__header">
        <p className="eyebrow">Selected event</p>
        <h2 id="selected-event-title" className="section-title">
          {props.event ? props.event.name : "No event selected"}
        </h2>
      </div>

      {!props.scenarioName ? (
        <p className="muted">Select a scenario before working with events.</p>
      ) : !props.event ? (
        <p className="muted">Select an event in the side panel.</p>
      ) : (
        <>
          <form onSubmit={props.onEditSubmit}>
            <EventFields
              idPrefix="event-edit"
              name={props.editName}
              targetDate={props.editTargetDate}
              details={props.editDetails}
              onNameChange={props.onEditNameChange}
              onTargetDateChange={props.onEditTargetDateChange}
              onDetailsChange={props.onEditDetailsChange}
            />
            <ActionError message={props.error} />
            <div className="form-actions">
              <button
                className="btn btn--primary"
                type="submit"
                disabled={props.saving || saveDisabled}
              >
                {props.saving ? "Saving..." : "Save event"}
              </button>
            </div>
          </form>
          <section className="destructive-action-section" aria-label="Event deletion">
            <div className="form-actions">
              {!confirmingDelete ? (
                <button
                  className="btn btn--danger"
                  type="button"
                  disabled={props.saving}
                  onClick={() => setConfirmingDelete(true)}
                >
                  Delete event
                </button>
              ) : null}
            </div>
            {confirmingDelete ? (
              <div className="delete-confirmation" role="alertdialog">
                <p>Are you sure you want to delete the selected event?</p>
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
        </>
      )}
    </section>
  );
}

function CreateEventForm(props: {
  scenarioName: string;
  name: string;
  targetDate: string;
  details: string;
  error: string;
  saving: boolean;
  disabled: boolean;
  onNameChange: (value: string) => void;
  onTargetDateChange: (value: string) => void;
  onDetailsChange: (value: string) => void;
  onSubmit: (event: SubmitEvent<HTMLFormElement>) => void;
}) {
  return (
    <form className="detail-card" aria-labelledby="create-event-title" onSubmit={props.onSubmit}>
      <div className="detail-card__header">
        <h2 id="create-event-title" className="section-title">
          Create event
        </h2>
      </div>
      <p className="muted">
        {props.scenarioName
          ? `Create an event in ${props.scenarioName}.`
          : "Select a scenario before creating an event."}
      </p>
      <EventFields
        idPrefix="event-create"
        name={props.name}
        targetDate={props.targetDate}
        details={props.details}
        disabled={props.disabled}
        onNameChange={props.onNameChange}
        onTargetDateChange={props.onTargetDateChange}
        onDetailsChange={props.onDetailsChange}
      />
      <ActionError message={props.error} />
      <div className="form-actions">
        <button
          className="btn btn--primary"
          type="submit"
          disabled={props.disabled || props.saving || !props.name.trim() || !props.targetDate}
        >
          {props.saving ? "Saving..." : "Create event"}
        </button>
      </div>
    </form>
  );
}

function EventFields(props: {
  idPrefix: string;
  name: string;
  targetDate: string;
  details: string;
  disabled?: boolean;
  onNameChange: (value: string) => void;
  onTargetDateChange: (value: string) => void;
  onDetailsChange: (value: string) => void;
}) {
  const nameId = `${props.idPrefix}-name`;
  const targetDateId = `${props.idPrefix}-target-date`;
  const detailsId = `${props.idPrefix}-details`;

  return (
    <>
      <label className="form-label form-label--required" htmlFor={nameId}>
        Name
      </label>
      <input
        id={nameId}
        className="input"
        value={props.name}
        onChange={(event) => props.onNameChange(event.target.value)}
        disabled={props.disabled}
      />
      <label className="form-label form-label--required" htmlFor={targetDateId}>
        Target date
      </label>
      <input
        id={targetDateId}
        className="input date-input"
        type="date"
        value={props.targetDate}
        onChange={(event) => props.onTargetDateChange(event.target.value)}
        disabled={props.disabled}
      />
      <label className="form-label" htmlFor={detailsId}>
        Event details
      </label>
      <textarea
        id={detailsId}
        className="textarea"
        value={props.details}
        onChange={(event) => props.onDetailsChange(event.target.value)}
        disabled={props.disabled}
      />
    </>
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
