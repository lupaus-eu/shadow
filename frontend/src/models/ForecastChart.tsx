import type { MetricResult } from "./client";

const WIDTH = 640;
const HEIGHT = 170;
const LEFT = 48;
const RIGHT = WIDTH - 12;

/** History (solid) and forecast (dashed) of one metric with the prediction band behind it. */
export function ForecastChart({ metric, bandLabel }: { metric: MetricResult; bandLabel: string }) {
  const all = [...metric.history.map((p) => ({ period: p.period, value: p.value, lower: p.value, upper: p.value })), ...metric.forecast.map((p) => ({ period: p.period, value: p.value, lower: p.lower ?? p.value, upper: p.upper ?? p.value }))];
  if (all.length < 2) return null;
  const low = Math.min(...all.map((p) => p.lower));
  const high = Math.max(...all.map((p) => p.upper));
  const span = high - low || 1;
  const x = (index: number) => LEFT + (index / (all.length - 1)) * (RIGHT - LEFT);
  const y = (value: number) => HEIGHT - 24 - ((value - low) / span) * (HEIGHT - 44);
  const joined = metric.history.length;
  const history = all.slice(0, joined).map((p, i) => `${x(i)},${y(p.value)}`).join(" ");
  const future = all.slice(Math.max(joined - 1, 0)).map((p, i) => `${x(i + Math.max(joined - 1, 0))},${y(p.value)}`).join(" ");
  const band = metric.forecast.length
    ? [...metric.forecast.map((p, i) => `${x(joined + i)},${y(p.upper ?? p.value)}`), ...[...metric.forecast].reverse().map((p, i) => `${x(all.length - 1 - i)},${y(p.lower ?? p.value)}`)].join(" ")
    : "";
  return (
    <svg role="img" aria-label={`${metric.name}: ${bandLabel}`} viewBox={`0 0 ${WIDTH} ${HEIGHT}`} width="100%" className="text-accent">
      <line x1={LEFT} y1={HEIGHT - 24} x2={RIGHT} y2={HEIGHT - 24} stroke="#bbb" />
      <text x="4" y="22" fontSize="10" fill="#666">{Math.round(high * 100) / 100}</text>
      <text x="4" y={HEIGHT - 24} fontSize="10" fill="#666">{Math.round(low * 100) / 100}</text>
      <text x={LEFT} y={HEIGHT - 8} fontSize="10" fill="#666">{all[0].period.slice(0, 7)}</text>
      <text x={RIGHT} y={HEIGHT - 8} fontSize="10" textAnchor="end" fill="#666">{all[all.length - 1].period.slice(0, 7)}</text>
      {band ? <polygon points={band} fill="currentColor" opacity="0.15" /> : null}
      {joined > 1 ? <polyline points={history} fill="none" stroke="currentColor" strokeWidth="2" /> : null}
      <polyline points={future} fill="none" stroke="currentColor" strokeWidth="2" strokeDasharray="6 4" />
    </svg>
  );
}
