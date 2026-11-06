import { useEffect, useState } from "react";

import { Section } from "../admin/Section";
import type { Locale } from "../i18n";
import { saveBlob } from "../exchange/image";
import { AppShell, useAccount, usePageTitle } from "../shell/AppShell";
import { Alert, Badge, Button, Table } from "../ui";
import {
  TransferRateLimitedError, TransferRefusedError, exportAll, importFile, loadTransferOrganizations,
  type TransferOrganization, type TransferResult,
} from "./client";
import { KIND_ORDER, dataTransferMessages } from "./messages";

const SHOWN_ERRORS = 100;

/** Export all administered Organizations as one CSV and import it back, with a preview first. */
export function DataTransferPage() {
  const { locale } = useAccount();
  return (
    <AppShell>
      <Content locale={locale} />
    </AppShell>
  );
}

function Content({ locale }: { locale: Locale }) {
  const text = dataTransferMessages(locale);
  usePageTitle(text.title);
  const [organizations, setOrganizations] = useState<TransferOrganization[] | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<TransferResult | null>(null);
  const [busy, setBusy] = useState<"exporting" | "reading" | "saving" | null>(null);
  const [message, setMessage] = useState<{ tone: "success" | "danger"; text: string } | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    loadTransferOrganizations(controller.signal).then(setOrganizations).catch(() => { if (!controller.signal.aborted) setMessage({ tone: "danger", text: text.failed }); });
    return () => controller.abort();
  }, [text.failed]);

  const failure = (cause: unknown): string => {
    if (cause instanceof TransferRateLimitedError) return text.rateLimited(Math.max(1, Math.ceil(cause.retryAfterSeconds / 60)));
    if (cause instanceof TransferRefusedError) return text.fileProblems[cause.reason] ?? text.failed;
    return text.failed;
  };

  async function download() {
    setBusy("exporting");
    setMessage(null);
    try {
      const { blob, fileName } = await exportAll();
      saveBlob(blob, fileName);
      setMessage({ tone: "success", text: text.exported });
    } catch (cause) { setMessage({ tone: "danger", text: failure(cause) }); }
    setBusy(null);
  }

  async function choose(chosen: File | undefined) {
    setPreview(null);
    setMessage(null);
    setFile(chosen ?? null);
    if (!chosen) return;
    setBusy("reading");
    try { setPreview(await importFile(chosen, true)); } catch (cause) { setMessage({ tone: "danger", text: failure(cause) }); }
    setBusy(null);
  }

  async function save() {
    if (!file) return;
    setBusy("saving");
    try {
      await importFile(file, false);
      setMessage({ tone: "success", text: text.saved });
      setFile(null);
      setPreview(null);
    } catch (cause) { setMessage({ tone: "danger", text: failure(cause) }); }
    setBusy(null);
  }

  const problem = (reason: string) => {
    const [code, detail] = reason.split(":");
    const known = text.problems[code] ?? code;
    return detail ? `${known} (${text.limit(detail)})` : known;
  };

  return (
    <div className="flex flex-col gap-5">
      <p className="m-0 max-w-3xl text-[13px] text-ink-muted">{text.intro}</p>
      {message ? <Alert tone={message.tone} role={message.tone === "danger" ? "alert" : "status"}>{message.text}</Alert> : null}
      <Section title={text.scope}>
        {organizations === null ? null : organizations.length === 0 ? <p className="m-0 text-[13px] text-ink-muted">{text.scopeEmpty}</p> : (
          <ul className="m-0 flex list-none flex-col gap-1 p-0">
            {organizations.map((item) => <li key={item.id} className="flex items-center gap-2 text-[13px]"><span className="font-medium">{item.name}</span><Badge>{text.roles[item.role]}</Badge></li>)}
          </ul>
        )}
      </Section>
      {organizations && organizations.length > 0 ? (
        <>
          <Section title={text.exportTitle} description={text.exportBody}>
            <p className="m-0 text-[13px]">{text.exportIncludes}</p>
            <p className="m-0 text-[13px] text-ink-muted">{text.exportExcludes}</p>
            <div><Button variant="primary" disabled={busy !== null} onClick={() => void download()}>{busy === "exporting" ? text.exporting : text.exportAction}</Button></div>
          </Section>
          <Section title={text.importTitle} description={text.importBody}>
            <p className="m-0 text-[13px] text-ink-muted">{text.importRules}</p>
            <label className="flex flex-col gap-1 text-[13px] font-medium">
              {text.choose}
              <input type="file" accept=".csv,text/csv" disabled={busy !== null} onChange={(event) => void choose(event.target.files?.[0])} className="text-[13px] font-normal" />
            </label>
            {busy === "reading" ? <p role="status" className="m-0 text-[13px] text-ink-muted">{text.reading}</p> : null}
            {preview ? (
              <div className="flex flex-col gap-3">
                <h3 className="m-0 text-[14px] font-semibold">{text.previewTitle}</h3>
                {preview.errors.length === 0 ? <p className="m-0 text-[13px] text-ink-muted">{text.nothingSaved}</p> : null}
                {preview.organizations.map((summary) => (
                  <div key={summary.id} className="flex flex-col gap-2">
                    <p className="m-0 text-[13px] font-semibold">{summary.name ?? summary.id}</p>
                    <Table>
                      <thead><tr><th scope="col">{text.columns.kind}</th><th scope="col">{text.columns.created}</th><th scope="col">{text.columns.updated}</th><th scope="col">{text.columns.unchanged}</th></tr></thead>
                      <tbody>
                        {KIND_ORDER.filter((kind) => summary.kinds[kind]).map((kind) => <tr key={kind}><th scope="row">{text.kinds[kind]}</th><td>{summary.kinds[kind].created}</td><td>{summary.kinds[kind].updated}</td><td>{summary.kinds[kind].unchanged}</td></tr>)}
                      </tbody>
                    </Table>
                    {summary.overwrites_newer > 0 ? <Alert tone="warning">{text.overwrites(summary.overwrites_newer)}</Alert> : null}
                  </div>
                ))}
                {preview.errors.length > 0 ? (
                  <div className="flex flex-col gap-2">
                    <Alert tone="danger" role="alert">{text.errorsTitle(preview.errors.length, Math.min(SHOWN_ERRORS, preview.errors.length))}</Alert>
                    <Table>
                      <thead><tr><th scope="col">{text.errorColumns.row}</th><th scope="col">{text.errorColumns.kind}</th><th scope="col">{text.errorColumns.column}</th><th scope="col">{text.errorColumns.problem}</th></tr></thead>
                      <tbody>
                        {preview.errors.slice(0, SHOWN_ERRORS).map((issue, index) => <tr key={`${issue.row}-${index}`}><td>{issue.row}</td><td>{issue.type ? text.kinds[issue.type as keyof typeof text.kinds] ?? issue.type : ""}</td><td>{issue.column ?? ""}</td><td>{problem(issue.reason)}{issue.value ? `: ${issue.value}` : ""}</td></tr>)}
                      </tbody>
                    </Table>
                  </div>
                ) : null}
                <div className="flex gap-2">
                  <Button variant="primary" disabled={busy !== null || preview.errors.length > 0} onClick={() => void save()}>{busy === "saving" ? text.saving : text.save}</Button>
                  <Button disabled={busy !== null} onClick={() => { setPreview(null); setFile(null); }}>{text.cancel}</Button>
                </div>
              </div>
            ) : null}
          </Section>
        </>
      ) : null}
    </div>
  );
}
