// Bar chart of the last nights (hours) with a dashed personal-average line.
// Nights shorter than the server's sleep_short_hours threshold are highlighted.
import { Bar, BarChart, CartesianGrid, Cell, ReferenceLine, Tooltip, XAxis, YAxis } from 'recharts';
import { ChartFrame, useChartTheme } from '../../../shared/components';
import type { SleepSummary } from '../types.log';

export function SleepChart({ summary }: { summary: SleepSummary }) {
  const t = useChartTheme();
  const rows = summary.nights.map((n) => ({ label: `Day ${n.missionDay}`, hours: n.hours, short: n.short }));
  const avg = summary.personalAvgHours;
  const shortDays = summary.nights.filter((n) => n.short).map((n) => n.missionDay);
  const description =
    `Sleep over the last ${rows.length} nights, in hours.` +
    (avg !== null ? ` Your personal average is ${avg} hours.` : '') +
    (shortDays.length ? ` Short nights: mission day ${shortDays.join(', ')}.` : '');

  return (
    <ChartFrame label={description} height={240}>
      <BarChart data={rows} margin={{ top: 12, right: 12, bottom: 0, left: -12 }}>
        <CartesianGrid {...t.grid} />
        <XAxis dataKey="label" {...t.axis} />
        <YAxis {...t.axis} domain={[0, 10]} unit=" h" />
        <Tooltip {...t.tooltip} formatter={(v) => [`${String(v)} h`, 'Sleep']} cursor={{ fill: t.colors.band, fillOpacity: 0.08 }} />
        <Bar dataKey="hours" radius={[6, 6, 0, 0]} isAnimationActive={false}>
          {rows.map((r) => (
            <Cell key={r.label} fill={r.short ? t.colors.warn : t.colors.accent} />
          ))}
        </Bar>
        {avg !== null && (
          <ReferenceLine
            y={avg}
            stroke={t.colors.pink}
            strokeDasharray="6 4"
            label={{ value: `Your average ${avg} h`, position: 'insideTopRight', fill: t.colors.pink, fontSize: 11 }}
          />
        )}
      </BarChart>
    </ChartFrame>
  );
}
