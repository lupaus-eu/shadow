import { useEffect, useState } from "react";

import type { Locale } from "../../i18n";
import { Alert, Badge, Button, Dialog, Field, TextArea, TextInput, useConfirm } from "../../ui";
import { createEvent, deleteEvent, loadEventDetail, updateEvent, type EventChange, type LineEvent } from "../client";
import { todayIso } from "../timeline";
import { describeChange, timelineMessages } from "../timeline-messages";
import { refusalMessage } from "./refusals";

export type EditorTarget = { mode: "new" } | { mode: "edit"; event: LineEvent };

/**
 * The event dialog: title, date and note, and for an existing event its ordered changes with the element names resolved for reading
 * (the changes themselves are drawn on the canvas). The form keeps the person's input when a write is refused, and says why.
 */
export function EventEditor({ organizationId, modelId, lineId, target, canWrite, locale, onClose, onChanged }: {
  organizationId: string; modelId: string; lineId: string; target: EditorTarget; canWrite: boolean; locale: Locale;
  onClose: () => void; /** `selectId` is the event to show afterwards (a new one), `removedId` the one that was deleted. */ onChanged: (result: { selectId?: string; removedId?: string }) => void;
}) {
  const text = timelineMessages(locale);
  const confirm = useConfirm();
  const editing = target.mode === "edit" ? target.event : null;
  const [event, setEvent] = useState<LineEvent | null>(editing);
  const [title, setTitle] = useState(editing?.title ?? "");
  const [date, setDate] = useState(editing?.occurred_on ?? todayIso());
  const [note, setNote] = useState(editing?.note ?? "");
  const [changes, setChanges] = useState<EventChange[] | null>(null);
  const [names, setNames] = useState<ReadonlyMap<string, string>>(new Map());
  const [error, setError] = useState<string | null>(null);
  const [problems, setProblems] = useState<{ title?: string; date?: string }>({});
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(editing !== null);

  const editingId = editing?.id ?? null;
  /** Reads the event and its changes; `fields` also refills the form (the first time only, so a refused edit keeps what was typed). */
  async function refresh(fields: boolean) {
    if (!editingId) return;
    try {
      const detail = await loadEventDetail(organizationId, modelId, lineId, editingId);
      setEvent(detail.event); setChanges(detail.changes); setNames(detail.names);
      if (fields) { setTitle(detail.event.title); setDate(detail.event.occurred_on); setNote(detail.event.note ?? ""); }
    } catch (cause) { setError(refusalMessage(cause, locale)); } finally { setLoading(false); }
  }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { void refresh(true); }, [editingId]);

  async function save() {
    const next = { title: title.trim() ? undefined : text.titleRequired, date: date ? undefined : text.dateRequired };
    setProblems(next);
    if (next.title || next.date) return;
    setBusy(true); setError(null);
    try {
      const input = { occurred_on: date, title: title.trim(), note: note.trim() || null };
      if (event) { await updateEvent(organizationId, modelId, event, input); onChanged({}); } else { const created = await createEvent(organizationId, modelId, lineId, input); onChanged({ selectId: created.id }); }
      onClose();
    } catch (cause) {
      setError(refusalMessage(cause, locale));
      // A stale version is read again so the next try can succeed; the typed values stay.
      if (event) await refresh(false);
    } finally { setBusy(false); }
  }
  async function remove() {
    if (!event) return;
    if (!(await confirm({ title: text.deleteEventConfirm(event.title), confirmLabel: text.deleteEvent, destructive: true }))) return;
    setBusy(true); setError(null);
    try { await deleteEvent(organizationId, modelId, event); onChanged({ removedId: event.id }); onClose(); } catch (cause) { setError(refusalMessage(cause, locale)); await refresh(false); } finally { setBusy(false); }
  }

  const planned = date > todayIso();
  const disabled = !canWrite || busy;
  return (
    <Dialog open onOpenChange={(open) => { if (!open) onClose(); }} title={editing ? text.eventDialogTitle : text.newEventDialogTitle}
      footer={<>
        {editing && canWrite ? <Button variant="ghost-danger" className="mr-auto" disabled={busy} onClick={() => void remove()}>{text.deleteEvent}</Button> : null}
        <Button onClick={onClose}>{canWrite ? text.cancel : text.close}</Button>
        {canWrite ? <Button variant="primary" disabled={busy || loading} onClick={() => void save()}>{editing ? text.save : text.createEvent}</Button> : null}
      </>}>
      {loading ? <p role="status" className="text-ink-muted">{text.loadingEvent}</p> : (
        <form className="flex flex-col gap-3" onSubmit={(submit) => { submit.preventDefault(); void save(); }}>
          {error ? <Alert tone="danger" role="alert">{error}</Alert> : null}
          <Field label={text.eventTitle} error={problems.title}>{(control) => <TextInput {...control} value={title} maxLength={200} disabled={disabled} autoFocus onChange={(change) => setTitle(change.target.value)} />}</Field>
          <Field label={editing ? text.changeDate : text.eventDate} hint={editing ? text.eventDateHint : `${text.eventDateHint} ${text.eventDateSuggestion}`} error={problems.date}>{(control) => <TextInput {...control} type="date" value={date} disabled={disabled} onChange={(change) => setDate(change.target.value)} />}</Field>
          {planned ? <p className="m-0"><Badge tone="warning">{text.planned}</Badge></p> : null}
          <Field label={text.eventNote}>{(control) => <TextArea {...control} rows={3} value={note} disabled={disabled} onChange={(change) => setNote(change.target.value)} />}</Field>
          {editing ? (
            <section aria-labelledby="event-changes" className="flex flex-col gap-1.5">
              <h3 id="event-changes" className="m-0 text-[13px] font-semibold">{text.changes}</h3>
              {changes && changes.length > 0
                ? <ol className="m-0 flex flex-col gap-1 pl-5 text-[13px]">{changes.map((change) => <li key={change.position}>{describeChange(change, names, locale)}</li>)}</ol>
                : <p className="m-0 text-[13px] text-ink-muted">{text.noChanges}</p>}
            </section>
          ) : null}
          <button type="submit" hidden />
        </form>
      )}
    </Dialog>
  );
}
