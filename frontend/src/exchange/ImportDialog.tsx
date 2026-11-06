import { useState } from "react";

import type { PlannerMessages } from "../i18n";
import { Alert, Badge, Button, Dialog, Table } from "../ui";
import { ImportRefusedError, RateLimitedError, downloadImportTemplate, importEvents, type ImportResult } from "./client";
import { importFormat, megabytes } from "./import-file";
import { saveBlob } from "./image";

const SHOWN_ROWS = 50;

type Choice = { file: File; format: "xlsx" | "csv" };

/** Choose a spreadsheet, read the preview the server builds, and save the import only when it has no problems. */
export function ImportDialog({ open, onOpenChange, organizationId, yearclockId, locale, copy, rateLimited, cancelLabel, onImported }: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  organizationId: string;
  yearclockId: string;
  locale: "en" | "fi";
  copy: PlannerMessages["import"];
  rateLimited: (minutes: number) => string;
  cancelLabel: string;
  onImported: (count: number) => void;
}) {
  const [choice, setChoice] = useState<Choice | null>(null);
  const [preview, setPreview] = useState<ImportResult | null>(null);
  const [busy, setBusy] = useState<"reading" | "saving" | null>(null);
  const [error, setError] = useState<string | null>(null);

  function reset() { setChoice(null); setPreview(null); setBusy(null); setError(null); }
  const failure = (cause: unknown): string => {
    if (cause instanceof RateLimitedError) return rateLimited(Math.max(1, Math.ceil(cause.retryAfterSeconds / 60)));
    if (cause instanceof ImportRefusedError) {
      const detail = cause.detail;
      switch (cause.reason) {
        case "unreadable_file": return copy.fatal.unreadable_file;
        case "macros_not_allowed": return copy.fatal.macros_not_allowed;
        case "too_many_rows": return copy.fatal.too_many_rows(Number(detail.maximum));
        case "file_too_large": return copy.fatal.file_too_large(megabytes(detail.maximum_bytes));
        case "limit_reached": return copy.fatal.limit_reached(Number(detail.maximum));
      }
    }
    return copy.fatal.failed;
  };

  async function choose(file: File | undefined) {
    setPreview(null);
    setError(null);
    if (!file) { setChoice(null); return; }
    const format = importFormat(file.name);
    if (!format) { setChoice(null); setError(copy.fatal.unsupported); return; }
    setChoice({ file, format });
    setBusy("reading");
    try { setPreview(await importEvents(organizationId, yearclockId, file, format, true)); } catch (cause) { setError(failure(cause)); }
    setBusy(null);
  }

  async function save() {
    if (!choice || !preview) return;
    setBusy("saving");
    setError(null);
    try {
      const saved = await importEvents(organizationId, yearclockId, choice.file, choice.format, false);
      reset();
      onOpenChange(false);
      onImported(saved.created);
      return;
    } catch (cause) { setError(failure(cause)); }
    setBusy(null);
  }

  async function template() {
    setError(null);
    try { const file = await downloadImportTemplate(organizationId, yearclockId, locale); saveBlob(file.blob, file.fileName); } catch { setError(copy.templateFailed); }
  }

  const canSave = preview !== null && preview.errors.length === 0 && preview.create.length > 0 && busy === null;
  return (
    <Dialog open={open} onOpenChange={(next) => { if (!next) reset(); onOpenChange(next); }} title={copy.title} description={copy.description} wide
      footer={<><Button onClick={() => { reset(); onOpenChange(false); }}>{cancelLabel}</Button><Button variant="primary" disabled={!canSave} onClick={() => void save()}>{busy === "saving" ? copy.saving : copy.save(preview?.create.length ?? 0)}</Button></>}>
      <div className="flex flex-col gap-4">
        <div className="flex flex-wrap items-end gap-3">
          <div className="flex min-w-60 flex-1 flex-col gap-1.5">
            <label htmlFor="import-file" className="text-[13px] font-medium">{copy.file}</label>
            <input id="import-file" type="file" accept=".xlsx,.csv,.txt" onChange={(event) => void choose(event.target.files?.[0])} className="text-[13px]" />
          </div>
          <Button onClick={() => void template()}>{copy.template}</Button>
        </div>
        {busy === "reading" ? <p role="status" className="m-0 text-[13px] text-ink-muted">{copy.reading}</p> : null}
        {error ? <Alert tone="danger" role="alert">{error}</Alert> : null}
        {preview ? (
          <div className="flex flex-col gap-3" aria-live="polite">
            {preview.errors.length ? (
              <>
                <Alert tone="danger" role="alert">{copy.problems(preview.errors.length)}</Alert>
                <Table caption={copy.problems(preview.errors.length)}>
                  <thead><tr><th scope="col">{copy.row}</th><th scope="col">{copy.column}</th><th scope="col">{copy.problem}</th></tr></thead>
                  <tbody>{preview.errors.slice(0, SHOWN_ROWS).map((issue, index) => <tr key={index}><td>{issue.row}</td><td>{issue.column ? (copy.dates[issue.column as keyof typeof copy.dates] ?? issue.column) : ""}</td><td>{(copy.reasons[issue.reason] ?? (() => issue.reason))(issue.value)}</td></tr>)}</tbody>
                </Table>
                {preview.errors.length > SHOWN_ROWS ? <p className="m-0 text-xs text-ink-muted">{copy.more(preview.errors.length - SHOWN_ROWS)}</p> : null}
              </>
            ) : (
              <Alert tone={preview.create.length ? "success" : "info"} role="status">{preview.create.length ? copy.summary(preview.create.length, preview.skipped.length) : copy.nothing}</Alert>
            )}
            {preview.errors.length === 0 && preview.create.length ? (
              <section aria-label={copy.creating} className="flex flex-col gap-1.5">
                <h3 className="m-0 text-[13px] font-semibold">{copy.creating}</h3>
                <Table caption={copy.creating}>
                  <thead><tr><th scope="col">{copy.row}</th><th scope="col">{copy.titleColumn}</th><th scope="col">{copy.dates.starts}</th><th scope="col">{copy.dates.ends}</th><th scope="col">{copy.dates.lane}</th><th scope="col">{copy.dates.category}</th><th scope="col">{copy.dates.labels}</th></tr></thead>
                  <tbody>{preview.create.slice(0, SHOWN_ROWS).map((row) => <tr key={row.row}><td>{row.row}</td><th scope="row" className="text-left font-semibold">{row.title}</th><td>{row.starts_on}</td><td>{row.ends_on ?? ""}</td><td>{row.lane}</td><td>{row.category ?? ""}</td><td>{row.labels.join(", ")}</td></tr>)}</tbody>
                </Table>
                {preview.create.length > SHOWN_ROWS ? <p className="m-0 text-xs text-ink-muted">{copy.more(preview.create.length - SHOWN_ROWS)}</p> : null}
              </section>
            ) : null}
            {preview.skipped.length ? (
              <section aria-label={copy.skippedTitle} className="flex flex-col gap-1.5">
                <h3 className="m-0 text-[13px] font-semibold">{copy.skippedTitle} <Badge>{preview.skipped.length}</Badge></h3>
                <ul className="m-0 flex list-none flex-col gap-0.5 p-0 text-[13px] text-ink-muted">{preview.skipped.slice(0, SHOWN_ROWS).map((item) => <li key={`${item.row}-${item.reason}`}>{copy.row} {item.row}: {item.title || "—"} — {copy.skippedReasons[item.reason]}</li>)}</ul>
              </section>
            ) : null}
          </div>
        ) : null}
      </div>
    </Dialog>
  );
}
