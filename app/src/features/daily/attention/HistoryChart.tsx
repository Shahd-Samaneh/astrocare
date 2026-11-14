// Owner: Shahd. Last 10 attention tests over the personal baseline band.
// The band is the baseline range (min–max of the baseline tests, or median ± 10 %),
// drawn with the shared baselineBand helper (mean ± 1·SD where SD = half the range).
import { CartesianGrid, Line, LineChart, Tooltip, XAxis, YAxis } from 'recharts';
import { ChartFrame, EmptyState, baselineBand, useChartTheme } from '../../../shared/components';
import type { AttentionBaseline, DailyCognitiveTest } from '../api.attention';

export interface HistoryChartProps {
  tests: DailyCognitiveTest[]; // newest first, as the API returns them
  baseline?: AttentionBaseline;
}

function label(ts: string) {
  const d = new Date(ts);
  return `${d.toLocaleDateString([], { month: 'short', day: 'numeric' })} ${d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`;
}

export function HistoryChart({ tests, baseline }: HistoryChartProps) {
  const t = useChartTheme();
  if (!tests.length)
    return (
      <EmptyState title="No attention tests yet" description="Your results will appear here." />
    );

  const rows = [...tests].reverse().map((x) => ({
    when: label(x.ts),
    medianMs: Math.round(x.medianMs),
    kind: x.context === 'retest' ? 'Retest' : 'Routine',
  }));
  const band =
    baseline && baseline.rangeLowMs != null && baseline.rangeHighMs != null
      ? {
          mean: (baseline.rangeLowMs + baseline.rangeHighMs) / 2,
          sd: (baseline.rangeHighMs - baseline.rangeLowMs) / 2,
          n: baseline.n,
        }
      : undefined;
  const summary = `Median reaction time of the last ${rows.length} tests, from ${rows[0].medianMs} ms to ${rows[rows.length - 1].medianMs} ms${
    band
      ? `. Usual range ${Math.round(band.mean - band.sd)} to ${Math.round(band.mean + band.sd)} ms`
      : ''
  }.`;

  return (
    <ChartFrame label={summary} height={220}>
      <LineChart data={rows} margin={{ top: 8, right: 12, bottom: 0, left: -8 }}>
        <CartesianGrid {...t.grid} />
        <XAxis dataKey="when" {...t.axis} interval="preserveStartEnd" minTickGap={24} />
        <YAxis {...t.axis} domain={['auto', 'auto']} unit=" ms" width={64} />
        <Tooltip
          {...t.tooltip}
          formatter={(v, _n, item) => [`${v} ms`, item?.payload?.kind ?? 'Median']}
        />
        {baselineBand(band, 1, t)}
        <Line
          dataKey="medianMs"
          name="Median"
          stroke={t.colors.accent}
          strokeWidth={2}
          dot={{ r: 3 }}
          isAnimationActive={false}
        />
      </LineChart>
    </ChartFrame>
  );
}
