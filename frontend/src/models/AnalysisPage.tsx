import { useCallback, useEffect, useState } from "react";

import { useOrganization } from "../shell/organization-outlet";
import { Alert, Badge, Button, EmptyState, Field, Select } from "../ui";
import { decideRecommendation, generateAiAnalysis, generateAnalysis, loadAnalysis, loadSimulations, type Analysis, type Finding, type Recommendation, type RecommendationStatus, type Simulation } from "./client";
import { modelMessages } from "./messages";
import { useModel } from "./ModelShell";

const number = (value: number | null, unit: string | null) => (value === null ? "–" : `${Math.round(value * 100) / 100}${unit ? ` ${unit}` : ""}`);
const percent = (value: number | null) => (value === null ? "–" : `${value > 0 ? "+" : ""}${(value * 100).toFixed(0)} %`);

/** `…/models/:modelId/analysis`: findings of a simulation and the actions proposed from them. */
export function AnalysisPage() {
  const { locale } = useOrganization();
  const { organizationId, modelId, version, writable } = useModel();
  const text = modelMessages(locale);
  const [runs, setRuns] = useState<Simulation[] | null>(null);
  const [runId, setRunId] = useState("");
  const [compareId, setCompareId] = useState("");
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    void loadSimulations(organizationId, modelId, version.id).then((list) => { setRuns(list); setRunId(list[0]?.id ?? ""); setCompareId(""); }).catch(() => setError(text.failed));
  }, [organizationId, modelId, version.id, text.failed]);

  const load = useCallback(async () => {
    if (!runId) { setAnalysis(null); return; }
    try { setAnalysis(await loadAnalysis(organizationId, modelId, runId, compareId || null)); setError(null); } catch { setError(text.failed); }
  }, [organizationId, modelId, runId, compareId, text.failed]);
  useEffect(() => { void load(); }, [load]);

  async function generate() {
    try { setAnalysis(await generateAnalysis(organizationId, modelId, runId, compareId || null)); setError(null); } catch { setError(text.failed); }
  }
  async function askAi() {
    setBusy(true);
    try { setAnalysis(await generateAiAnalysis(organizationId, modelId, runId, compareId || null, locale)); setError(null); } catch { setError(text.aiFailed); }
    setBusy(false);
  }
  async function decide(recommendation: Recommendation, status: RecommendationStatus) {
    try {
      const updated = await decideRecommendation(organizationId, modelId, runId, recommendation, status);
      setAnalysis((current) => (current ? { ...current, recommendations: current.recommendations.map((item) => (item.id === updated.id ? updated : item)) } : current));
    } catch { setError(text.stale); await load(); }
  }

  if (runs !== null && runs.length === 0) return <EmptyState title={text.noRuns} />;
  return (
    <div className="flex flex-col gap-4">
      <div>
        <h2 className="m-0 text-[15px] font-semibold">{text.analysisTitle}</h2>
        <p className="m-0 text-[13px] text-ink-muted">{text.analysisDescription}</p>
      </div>
      <div className="flex flex-wrap items-end gap-3">
        <Field label={text.chooseRun} className="w-64">{(control) => <Select {...control} value={runId} onChange={(event) => setRunId(event.target.value)}>{(runs ?? []).map((run) => <option key={run.id} value={run.id}>{run.name}</option>)}</Select>}</Field>
        <Field label={text.compareTo} className="w-64">{(control) => <Select {...control} value={compareId} onChange={(event) => setCompareId(event.target.value)}><option value="">{text.noComparison}</option>{(runs ?? []).filter((run) => run.id !== runId).map((run) => <option key={run.id} value={run.id}>{run.name}</option>)}</Select>}</Field>
        {writable && runId ? <Button variant="primary" onClick={() => void generate()}>{text.generate}</Button> : null}
        {writable && runId && analysis?.ai_available ? <Button disabled={busy} onClick={() => void askAi()}>{text.askAi}</Button> : null}
      </div>
      {error ? <Alert tone="danger" role="alert">{error}</Alert> : null}
      {analysis ? (
        <>
          <section className="flex flex-col gap-2 rounded-[var(--radius-card)] border border-line bg-surface p-4">
            <h3 className="m-0 text-[14px] font-semibold">{text.findings}</h3>
            <div className="overflow-x-auto"><table className="w-full text-[13px]">
              <thead><tr className="text-left text-ink-muted"><th scope="col">{text.metric}</th><th scope="col">{text.start}</th><th scope="col">{text.end}</th><th scope="col">{text.change}</th>{analysis.compared_to ? <th scope="col">{text.versus}</th> : null}<th scope="col" /></tr></thead>
              <tbody>{analysis.findings.map((finding) => <FindingRow key={finding.key} finding={finding} compared={analysis.compared_to !== null} text={text} />)}</tbody>
            </table></div>
          </section>
          {analysis.ai_summary ? (
            <section className="flex flex-col gap-1 rounded-[var(--radius-card)] border border-line bg-surface p-4" aria-label={text.aiSummary}>
              <h3 className="m-0 text-[14px] font-semibold">{text.aiSummary} <Badge>{text.aiBadge}</Badge></h3>
              <p className="m-0 text-[13px]">{analysis.ai_summary}</p>
              <p className="m-0 text-xs text-ink-muted">{text.aiNote}</p>
            </section>
          ) : null}
          <section className="flex flex-col gap-2">
            <h3 className="m-0 text-[14px] font-semibold">{text.proposals}</h3>
            {analysis.recommendations.length === 0 ? <p className="m-0 text-[13px] text-ink-muted">{text.noProposals}</p> : null}
            {analysis.recommendations.map((item) => (
              <article key={item.id} className="flex flex-col gap-2 rounded-[var(--radius-card)] border border-line bg-surface p-4" aria-label={item.title}>
                <div className="flex flex-wrap items-center gap-2"><strong className="text-[14px]">{item.title}</strong>{item.kind === "ai" ? <Badge>{text.aiBadge}</Badge> : null}<Badge>{text.severities[item.severity]}</Badge><Badge>{text.statuses[item.status]}</Badge></div>
                <p className="m-0 text-[13px] text-ink-muted">{item.rationale}</p>
                {writable ? (
                  <div className="flex gap-2">
                    {item.status === "proposed" ? <><Button size="sm" variant="primary" onClick={() => void decide(item, "accepted")}>{text.accept}</Button><Button size="sm" onClick={() => void decide(item, "dismissed")}>{text.dismiss}</Button></> : <Button size="sm" onClick={() => void decide(item, "proposed")}>{text.reopen}</Button>}
                  </div>
                ) : null}
              </article>
            ))}
          </section>
        </>
      ) : null}
    </div>
  );
}

function FindingRow({ finding, compared, text }: { finding: Finding; compared: boolean; text: ReturnType<typeof modelMessages> }) {
  return (
    <tr className="border-t border-line">
      <th scope="row" className="py-1 pr-3 text-left font-medium">{finding.name}</th>
      <td>{number(finding.start, finding.unit)}</td>
      <td>{number(finding.end, finding.unit)}</td>
      <td>{percent(finding.change_pct)} <span className="text-xs text-ink-muted">{text.trends[finding.trend] ?? finding.trend}</span></td>
      {compared ? <td>{percent(finding.versus)}</td> : null}
      <td className="text-xs text-danger">{finding.turns_negative ? text.turnsNegative(finding.turns_negative.slice(0, 7)) : ""}</td>
    </tr>
  );
}
