// Owner: Shahd. "Sleep and reaction time, last 14 days".
// Bars: sleep hours per night (left axis) with a dashed line at sleep_short_hours.
// Line: daily median of routine quick tests (right axis) over the personal baseline band.
// Days where both are off (short sleep AND slower by ≥ attention_slower_pct) are highlighted.
// Missing days are gaps. Two signals shown together are not a proven cause (caption).
import {
  Bar,
  CartesianGrid,
  Cell,
  ComposedChart,
  Line,
  ReferenceLine,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { ChartFrame, EmptyState, baselineBand, useChartTheme } from '../../../shared/components';
import type {
  AttentionBaseline,
  DailyCognitiveTest,
  DailyThresholds,
  SleepNight,
} from '../api.attention';
import styles from './Attention.module.css';

export const TOGETHER_CAPTION = 'Shown together, not a proven cause.';
const DAYS = 14;

export interface SleepRtRow {
  day: string;
  missionDay: number;
  sleepHours: number | null;
  medianMs: number | null;
  shortSleep: boolean;
  slower: boolean;
  bothOff: boolean;
}

function median(xs: number[]): number {
  const s = [...xs].sort((a, b) => a - b);
  const m = Math.floor(s.length / 2);
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
}

/** Pure: build one row per mission day (exported for reuse in tests or other charts). */
// eslint-disable-next-line react-refresh/only-export-components
export function buildRows(
  nights: SleepNight[],
  tests: DailyCognitiveTest[],
  baselineMs: number | null,
  shortHours: number | null,
  slowerPct: number | null,
  lastDay?: number,
): SleepRtRow[] {
  const routine = tests.filter(
    (t) => t.context === 'routine' && t.missionDay != null && isQuick(t),
  );
  const days = [...nights.map((n) => n.missionDay), ...routine.map((t) => t.missionDay as number)];
  const end = lastDay ?? (days.length ? Math.max(...days) : undefined);
  if (end === undefined) return [];
  const rows: SleepRtRow[] = [];
  for (let d = end - DAYS + 1; d <= end; d++) {
    const sleep = nights.filter((n) => n.missionDay === d);
    const sleepHours = sleep.length ? Math.max(...sleep.map((n) => n.hours)) : null;
    const meds = routine.filter((t) => t.missionDay === d).map((t) => t.medianMs);
    const medianMs = meds.length ? Math.round(median(meds)) : null;
    const shortSleep = sleepHours != null && shortHours != null && sleepHours < shortHours;
    const slower =
      medianMs != null &&
      baselineMs != null &&
      slowerPct != null &&
      medianMs >= baselineMs * (1 + slowerPct / 100);
    rows.push({
      day: `D${d}`,
      missionDay: d,
      sleepHours,
      medianMs,
      shortSleep,
      slower,
      bothOff: shortSleep && slower,
    });
  }
  return rows;
}

/** Tests without a stored mode are quick (all simulated tests are 5-trial quick tests). */
function isQuick(t: DailyCognitiveTest): boolean {
  return !t.mode || t.mode === 'quick';
}

export interface SleepRtChartProps {
  nights: SleepNight[];
  tests: DailyCognitiveTest[];
  baseline?: AttentionBaseline;
  thresholds?: DailyThresholds;
  lastDay?: number;
}

export function SleepRtChart({ nights, tests, baseline, thresholds, lastDay }: SleepRtChartProps) {
  const t = useChartTheme();
  const shortHours = thresholds?.sleep_short_hours?.value ?? null;
  const slowerPct = thresholds?.attention_slower_pct?.value ?? null;
  const rows = buildRows(nights, tests, baseline?.medianMs ?? null, shortHours, slowerPct, lastDay);
  if (!rows.some((r) => r.sleepHours != null || r.medianMs != null)) {
    return (
      <EmptyState
        title="No sleep or test data yet"
        description="Nights and routine tests will appear here."
      />
    );
  }

  const band =
    baseline && baseline.rangeLowMs != null && baseline.rangeHighMs != null
      ? {
          mean: (baseline.rangeLowMs + baseline.rangeHighMs) / 2,
          sd: (baseline.rangeHighMs - baseline.rangeLowMs) / 2,
          n: baseline.n,
        }
      : undefined;
  const both = rows.filter((r) => r.bothOff).map((r) => r.day);
  const label =
    `Sleep hours per night and daily median reaction time, mission days ${rows[0].missionDay} to ${rows[rows.length - 1].missionDay}.` +
    (both.length
      ? ` Short sleep and slower reaction time on ${both.join(', ')}.`
      : ' No day with both short sleep and slower reaction time.') +
    ` ${TOGETHER_CAPTION}`;

  return (
    <div className={styles.chartBlock}>
      <ChartFrame label={label} height={260}>
        <ComposedChart data={rows} margin={{ top: 8, right: 4, bottom: 0, left: -8 }}>
          <CartesianGrid {...t.grid} />
          <XAxis dataKey="day" {...t.axis} interval="preserveStartEnd" minTickGap={12} />
          <YAxis
            yAxisId="sleep"
            orientation="left"
            {...t.axis}
            unit=" h"
            width={48}
            domain={[0, 10]}
          />
          <YAxis orientation="right" {...t.axis} unit=" ms" width={64} domain={['auto', 'auto']} />
          <Tooltip
            {...t.tooltip}
            formatter={(v, name) =>
              name === 'Sleep' ? [`${v} h`, 'Sleep'] : [`${v} ms`, 'Median reaction time']
            }
          />
          {baselineBand(band, 1, t)}
          {shortHours != null && (
            <ReferenceLine
              yAxisId="sleep"
              y={shortHours}
              stroke={t.colors.pink}
              strokeDasharray="5 4"
              ifOverflow="extendDomain"
            />
          )}
          <Bar
            yAxisId="sleep"
            dataKey="sleepHours"
            name="Sleep"
            barSize={14}
            isAnimationActive={false}
          >
            {rows.map((r) => (
              <Cell
                key={r.day}
                fill={r.bothOff ? t.colors.warn : t.colors.band}
                fillOpacity={r.bothOff ? 0.9 : 0.45}
              />
            ))}
          </Bar>
          <Line
            dataKey="medianMs"
            name="Median"
            stroke={t.colors.accent}
            strokeWidth={2}
            dot={{ r: 3 }}
            connectNulls={false}
            isAnimationActive={false}
          />
        </ComposedChart>
      </ChartFrame>
      <ul className={styles.legend} aria-label="Legend">
        <li>
          <span className={`${styles.swatch} ${styles.swBar}`} aria-hidden /> Sleep (h)
        </li>
        <li>
          <span className={`${styles.swatch} ${styles.swShort}`} aria-hidden /> Short sleep line (
          {shortHours ?? '—'} h)
        </li>
        <li>
          <span className={`${styles.swatch} ${styles.swLine}`} aria-hidden /> Median reaction time
          (routine tests)
        </li>
        <li>
          <span className={`${styles.swatch} ${styles.swBand}`} aria-hidden /> Your usual range
        </li>
        <li>
          <span className={`${styles.swatch} ${styles.swBoth}`} aria-hidden /> Both off: short sleep
          and ≥{slowerPct ?? '—'} % slower
        </li>
      </ul>
      <p className={styles.caption}>{TOGETHER_CAPTION} Days without data are gaps.</p>
    </div>
  );
}
