import { useState } from "react";

import type { PlannerMessages } from "../i18n";
import { Alert, Button, Choice, Dialog } from "../ui";

export type ExportChoice = { format: "xlsx" | "csv" | "ics"; scope: "window" | "all" };

/** Choose what to export (the current window or the whole Yearclock) and the file format. */
export function ExportDialog({ open, onOpenChange, initialFormat, windowRange, filtering, copy, cancelLabel, onExport }: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  initialFormat: "xlsx" | "csv" | "ics";
  windowRange: string;
  filtering: boolean;
  copy: PlannerMessages["exchange"];
  cancelLabel: string;
  onExport: (choice: ExportChoice) => Promise<string | null>;
}) {
  const [scope, setScope] = useState<ExportChoice["scope"]>("window");
  const [format, setFormat] = useState<ExportChoice["format"]>(initialFormat);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Opening again from the other menu entry starts with that entry's format.
  const [seen, setSeen] = useState(initialFormat);
  if (seen !== initialFormat) { setSeen(initialFormat); setFormat(initialFormat); }

  async function submit() {
    setBusy(true);
    setError(null);
    const failure = await onExport({ format, scope });
    setBusy(false);
    if (failure) setError(failure);
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange} title={copy.exportTitle} description={copy.exportDescription}
      footer={<><Button onClick={() => onOpenChange(false)}>{cancelLabel}</Button><Button variant="primary" disabled={busy} onClick={() => void submit()}>{busy ? copy.exporting : copy.exportAction}</Button></>}>
      <div className="flex flex-col gap-4">
        <fieldset className="m-0 flex flex-col gap-1.5 border-0 p-0">
          <legend className="mb-1 p-0 text-[13px] font-semibold">{copy.scope}</legend>
          <Choice type="radio" name="export-scope" checked={scope === "window"} onChange={() => setScope("window")} label={copy.scopeWindow(windowRange)} />
          {scope === "window" && filtering ? <p className="m-0 ml-6 text-xs text-ink-muted">{copy.scopeFilters}</p> : null}
          <Choice type="radio" name="export-scope" checked={scope === "all"} onChange={() => setScope("all")} label={copy.scopeAll} />
        </fieldset>
        <fieldset className="m-0 flex flex-col gap-1.5 border-0 p-0">
          <legend className="mb-1 p-0 text-[13px] font-semibold">{copy.format}</legend>
          <Choice type="radio" name="export-format" checked={format === "xlsx"} onChange={() => setFormat("xlsx")} label={copy.formatXlsx} />
          <Choice type="radio" name="export-format" checked={format === "csv"} onChange={() => setFormat("csv")} label={copy.formatCsv} />
          <Choice type="radio" name="export-format" checked={format === "ics"} onChange={() => setFormat("ics")} label={copy.formatIcs} />
        </fieldset>
        {error ? <Alert tone="danger" role="alert">{error}</Alert> : null}
      </div>
    </Dialog>
  );
}
