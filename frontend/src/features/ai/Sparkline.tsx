const WIDTH = 160;
const HEIGHT = 36;
const PADDING = 2;

// An inline SVG sparkline of the numeric values in date order; no chart
// dependency. Renders nothing with fewer than two numeric values. Staged
// values may come in any order, so the ISO dates are sorted first.
export default function Sparkline(props: { values: Array<{ date: string; value: unknown }> }) {
  const points = props.values
    .filter(
      (item): item is { date: string; value: number } =>
        typeof item.value === "number" && Number.isFinite(item.value)
    )
    .sort((left, right) => (left.date < right.date ? -1 : left.date > right.date ? 1 : 0));
  if (points.length < 2) return null;

  const numbers = points.map((item) => item.value);
  const min = Math.min(...numbers);
  const max = Math.max(...numbers);
  const range = max - min || 1;
  const step = (WIDTH - 2 * PADDING) / (points.length - 1);
  const coordinates = points
    .map((item, index) => {
      const x = PADDING + index * step;
      const y = HEIGHT - PADDING - ((item.value - min) / range) * (HEIGHT - 2 * PADDING);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");

  return (
    <svg
      className="ai-panel-sparkline"
      viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
      width={WIDTH}
      height={HEIGHT}
      role="img"
      aria-label={`Sparkline of ${points.length} values from ${points[0].date} to ${
        points[points.length - 1].date
      }, between ${min} and ${max}`}
    >
      <polyline points={coordinates} fill="none" stroke="currentColor" strokeWidth="1.5" />
    </svg>
  );
}
