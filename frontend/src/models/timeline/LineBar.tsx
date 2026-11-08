import { useState } from "react";

import type { Locale } from "../../i18n";
import { Alert, Badge, Button, Dialog, Field, Select, TextInput } from "../../ui";
import type { ModelLine } from "../client";
import { lineTree } from "../timeline";
import { timelineMessages } from "../timeline-messages";

/** The kind of the shown line, always as a word and a colour: the Base line records what happened, a Scenario is a what-if copy. */
export function LineKind({ line, locale }: { line: ModelLine; locale: Locale }) {
  const text = timelineMessages(locale);
  return line.kind === "base"
    ? <Badge tone="accent" className="shrink-0">{text.baseLine}</Badge>
    : <Badge tone="info" className="shrink-0">{text.scenario}</Badge>;
}

/** The line picker: the Base line first, each Scenario right under the line it starts from. */
export function LinePicker({ lines, line, locale, onSelect }: { lines: ModelLine[]; line: ModelLine; locale: Locale; onSelect: (line: ModelLine) => void }) {
  const text = timelineMessages(locale);
  return (
    <Field label={text.line} className="w-72 max-w-full">
      {(control) => (
        <Select {...control} title={line.kind === "base" ? text.baseLineHelp : text.scenarioHelp} value={line.id} onChange={(event) => { const next = lines.find((item) => item.id === event.target.value); if (next) onSelect(next); }}>
          {lineTree(lines).map(({ line: item, depth }) => <option key={item.id} value={item.id}>{`${"  ".repeat(depth)}${depth > 0 ? "↳ " : ""}${text.lineOption(item.name, item.kind)}`}</option>)}
        </Select>
      )}
    </Field>
  );
}

/** A dialog that asks one name (a new Scenario, a rename). It keeps what was typed when the server refuses, and says why. */
export function NameDialog({ title, description, label, initial, submitLabel, locale, onSubmit, onClose }: {
  title: string; description?: string; label: string; initial: string; submitLabel: string; locale: Locale;
  /** Resolves when done; rejects with the message to show. */ onSubmit: (name: string) => Promise<void>; onClose: () => void;
}) {
  const text = timelineMessages(locale);
  const [name, setName] = useState(initial);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  async function submit() {
    if (!name.trim()) { setError(text.nameRequired); return; }
    setBusy(true); setError(null);
    try { await onSubmit(name.trim()); onClose(); } catch (cause) { setError(cause instanceof Error ? cause.message : text.failed); } finally { setBusy(false); }
  }
  return (
    <Dialog open onOpenChange={(open) => { if (!open) onClose(); }} title={title} description={description}
      footer={<><Button onClick={onClose}>{text.cancel}</Button><Button variant="primary" disabled={busy} onClick={() => void submit()}>{submitLabel}</Button></>}>
      <form className="flex flex-col gap-3" onSubmit={(event) => { event.preventDefault(); void submit(); }}>
        {error ? <Alert tone="danger" role="alert">{error}</Alert> : null}
        <Field label={label}>{(control) => <TextInput {...control} value={name} maxLength={120} autoFocus disabled={busy} onChange={(event) => setName(event.target.value)} />}</Field>
        <button type="submit" hidden />
      </form>
    </Dialog>
  );
}
