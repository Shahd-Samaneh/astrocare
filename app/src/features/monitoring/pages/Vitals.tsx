// Vitals (placeholder) with a ChartFrame example: heart rate over the personal baseline band.
import { CartesianGrid, Line, LineChart, Tooltip, XAxis, YAxis } from 'recharts';
import { useApi } from '../../../shared/api/client';
import { Card, ChartFrame, PlaceholderPage, baselineBand, useChartTheme } from '../../../shared/components';
import type { Profile, Reading } from '../../../shared/types/contracts';
import { formatTime } from '../../../shared/utils/format';
import { OWNERS } from '../owners';

export default function Vitals() {
  const t = useChartTheme();
  const hr = useApi<Reading[]>('/readings?metric=heart_rate&hours=24');
  const profile = useApi<Profile>('/profile');
  const rows = (hr.data ?? []).map((r) => ({ time: formatTime(r.ts), value: r.value }));

  return (
    <PlaceholderPage
      title="Vitals"
      owners={OWNERS}
      endpoint="/readings?metric=heart_rate&hours=3"
      plan={[
        'Metric tabs',
        'Time ranges',
        'A trend over the personal baseline band',
        'Quality and gaps',
        'A recent readings table',
      ]}
    >
      <Card title="Heart rate · last 24 h" subtitle="Example: ChartFrame + baselineBand (mean ± 2 SD)">
        <ChartFrame label="Heart rate over the last 24 hours with the personal baseline band" height={220}>
          <LineChart data={rows} margin={{ top: 8, right: 8, bottom: 0, left: -16 }}>
            <CartesianGrid {...t.grid} />
            <XAxis dataKey="time" {...t.axis} minTickGap={40} />
            <YAxis {...t.axis} domain={['auto', 'auto']} />
            <Tooltip {...t.tooltip} />
            {baselineBand(profile.data?.baseline.heart_rate, 2, t)}
            <Line type="monotone" dataKey="value" name="bpm" stroke={t.colors.accent} dot={false} strokeWidth={2} />
          </LineChart>
        </ChartFrame>
      </Card>
    </PlaceholderPage>
  );
}
