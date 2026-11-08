import { useEffect, useState } from "react";

import type { Locale } from "../../i18n";
import { Alert, Badge, Button, Dialog, Field, TextArea, TextInput, useConfirm } from "../../ui";
import { createChange, deleteChange, loadChangeDetail, updateChange, type ChangeEdit, type LineChange } from "../client";
import { todayIso } from "../timeline";
import { describeEdit, timelineMessages } from "../timeline-messages";
import { refusalMessage } from "./refusals";

export type EditorTarget = { mode: "new" } | { mode: "edit"; change: LineChange };

/**
 * The change dialog: title, date and note, and for an existing change its ordered edits with the element names resolved for reading
 * (the edits themselves are drawn on the canvas). The form keeps the person's input when a write is refused, and says why.
 */
export function ChangeEditor({ organizationId, modelId, lineId, target, canWrite, locale, onClose, onChanged }: {
  organizationId: string; modelId: string; lineId: string; target: EditorTarget; canWrite: boolean; locale: Locale;
  onClose: () => void; /** `selectId` is the change to show afterwards (a new one), `removedId` the one that was deleted. */ onChanged: (result: { selectId?: string; removedId?: string }) => void;
}) {
  const text = timelineMessages(locale);
  const confirm = useConfirm();
  const editing = target.mode === "edit" ? target.change : null;
  const [change, setChange] = useState<LineChange | null>(editing);
  const [title, setTitle] = useState(editing?.title ?? "");
  const [date, setDate] = useState(editing?.occurred_on ?? todayIso());
  const [note, setNote] = useState(editing?.note ?? "");
  const [edits, setEdits] = useState<ChangeEdit[] | null>(null);
  const [names, setNames] = useState<ReadonlyMap<string, string>>(new Map());
  const [error, setError] = useState<string | null>(null);
  const [problems, setProblems] = useState<{ title?: string; date?: string }>({});
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(editing !== null);

  const editingId = editing?.id ?? null;
  /** Reads the change and its edits; `fields` also refills the form (the first time only, so a refused edit keeps what was typed). */
  async function refresh(fields: boolean) {
    if (!editingId) return;
    try {
      const detail = await loadChangeDetail(organizationId, modelId, lineId, editingId);
      setChange(detail.change); setEdits(detail.edits); setNames(detail.names);
      if (fields) { setTitle(detail.change.title); setDate(detail.change.occurred_on); setNote(detail.change.note ?? ""); }
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
      if (change) { await updateChange(organizationId, modelId, change, input); onChanged({}); } else { const created = await createChange(organizationId, modelId, lineId, input); onChanged({ selectId: created.id }); }
      onClose();
    } catch (cause) {
      setError(refusalMessage(cause, locale));
      // A stale version is read again so the next try can succeed; the typed values stay.
      if (change) await refresh(false);
    } finally { setBusy(false); }
  }
  async function remove() {
    if (!change) return;
    if (!(await confirm({ title: text.deleteChangeConfirm(change.title), confirmLabel: text.deleteChange, destructive: true }))) return;
    setBusy(true); setError(null);
    try { await deleteChange(organizationId, modelId, change); onChanged({ removedId: change.id }); onClose(); } catch (cause) { setError(refusalMessage(cause, locale)); await refresh(false); } finally { setBusy(false); }
  }

  const planned = date > todayIso();
  const disabled = !canWrite || busy;
  return (
    <Dialog open onOpenChange={(open) => { if (!open) onClose(); }} title={editing ? text.changeDialogTitle : text.newChangeDialogTitle}
      footer={<>
        {editing && canWrite ? <Button variant="ghost-danger" className="mr-auto" disabled={busy} onClick={() => void remove()}>{text.deleteChange}</Button> : null}
        <Button onClick={onClose}>{canWrite ? text.cancel : text.close}</Button>
        {canWrite ? <Button variant="primary" disabled={busy || loading} onClick={() => void save()}>{editing ? text.save : text.createChange}</Button> : null}
      </>}>
      {loading ? <p role="status" className="text-ink-muted">{text.loadingChange}</p> : (
        <form className="flex flex-col gap-3" onSubmit={(submit) => { submit.preventDefault(); void save(); }}>
          {error ? <Alert tone="danger" role="alert">{error}</Alert> : null}
          <Field label={text.changeTitle} error={problems.title}>{(control) => <TextInput {...control} value={title} maxLength={200} disabled={disabled} autoFocus onChange={(event) => setTitle(event.target.value)} />}</Field>
          <Field label={editing ? text.changeDate : text.dateLabel} hint={editing ? text.changeDateHint : `${text.changeDateHint} ${text.changeDateSuggestion}`} error={problems.date}>{(control) => <TextInput {...control} type="date" value={date} disabled={disabled} onChange={(event) => setDate(event.target.value)} />}</Field>
          {planned ? <p className="m-0"><Badge tone="warning">{text.planned}</Badge></p> : null}
          <Field label={text.changeNote}>{(control) => <TextArea {...control} rows={3} value={note} disabled={disabled} onChange={(event) => setNote(event.target.value)} />}</Field>
          {editing ? (
            <section aria-labelledby="change-edits" className="flex flex-col gap-1.5">
              <h3 id="change-edits" className="m-0 text-[13px] font-semibold">{text.edits}</h3>
              {edits && edits.length > 0
                ? <ol className="m-0 flex flex-col gap-1 pl-5 text-[13px]">{edits.map((edit) => <li key={edit.position}>{describeEdit(edit, names, locale)}</li>)}</ol>
                : <p className="m-0 text-[13px] text-ink-muted">{text.noEdits}</p>}
            </section>
          ) : null}
          <button type="submit" hidden />
        </form>
      )}
    </Dialog>
  );
}
