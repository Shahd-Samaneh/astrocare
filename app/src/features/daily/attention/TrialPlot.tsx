// Owner: Shahd. Per-trial view of one result:
//   * every response as a dot on a ms axis; lapses (≥ pvt_lapse_ms) are marked, with a
//     dashed line at the lapse threshold; false starts are listed (they have no RT)
//   * extended mode: reaction time over the 3 minutes (time-on-task effect)
import {
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  ReferenceLine,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { ChartFrame, useChartTheme } from '../../../shared/components';
import type { DailyCognitiveTest } from '../api.attention';
import styles from './Attention.module.css';

export interface TrialPlotProps {
  test: DailyCognitiveTest;
  /** daily.pvt_lapse_ms from GET /api/daily/thresholds; null = don't mark lapses. */
  lapseMs: number | null;
}

export function TrialPlot({ test, lapseMs }: TrialPlotProps) {
  const t = useChartTheme();
  const dots = test.trialsMs.map((ms, i) => ({
    trial: i + 1,
    ms: Math.round(ms),
    y: 1,
    lapse: lapseMs != null && ms >= lapseMs,
  }));
  const lapses = dots.filter((d) => d.lapse).length;
  const maxMs = Math.max(...dots.map((d) => d.ms), lapseMs ?? 0);
  const label =
    `${dots.length} responses from ${Math.min(...dots.map((d) => d.ms))} to ${Math.max(...dots.map((d) => d.ms))} ms` +
    (lapseMs != null ? `, ${lapses} at or above the ${lapseMs} ms lapse line` : '') +
    `. ${test.falseStarts} false start${test.falseStarts === 1 ? '' : 's'}.`;

  const offsets = test.trialOffsetsMs;
  const overTime =
    test.mode === 'extended' && offsets && offsets.length === test.trialsMs.length
      ? test.trialsMs.map((ms, i) => ({ sec: Math.round(offsets[i] / 1000), ms: Math.round(ms) }))
      : null;

  return (
    <div className={styles.chartBlock}>
      <h3 className={styles.subhead}>Each response</h3>
      <ChartFrame label={label} height={110}>
        <ScatterChart margin={{ top: 8, right: 16, bottom: 0, left: 8 }}>
          <CartesianGrid {...t.grid} />
          <XAxis
            type="number"
            dataKey="ms"
            {...t.axis}
            unit=" ms"
            domain={[0, Math.ceil((maxMs + 50) / 100) * 100]}
          />
          <YAxis type="number" dataKey="y" hide domain={[0, 2]} />
          <Tooltip
            {...t.tooltip}
            cursor={false}
            formatter={(v, name) => (name === 'ms' ? [`${v} ms`, 'Reaction time'] : [v, name])}
          />
          {lapseMs != null && (
            <ReferenceLine
              x={lapseMs}
              stroke={t.colors.warn}
              strokeDasharray="5 4"
              ifOverflow="extendDomain"
            />
          )}
          <Scatter data={dots} isAnimationActive={false}>
            {dots.map((d) => (
              <Cell key={d.trial} fill={d.lapse ? t.colors.warn : t.colors.accent} />
            ))}
          </Scatter>
        </ScatterChart>
      </ChartFrame>
      <ul className={styles.legend} aria-label="Legend">
        <li>
          <span className={`${styles.swatch} ${styles.swDot}`} aria-hidden /> Response
        </li>
        <li>
          <span className={`${styles.swatch} ${styles.swBoth}`} aria-hidden /> Lapse (≥{' '}
          {lapseMs ?? '—'} ms): {lapses}
        </li>
        <li>
          False starts (before the signal, no reaction time): <strong>{test.falseStarts}</strong>
        </li>
      </ul>

      {overTime && overTime.length > 1 && (
        <>
          <h3 className={styles.subhead}>Reaction time over the 3 minutes</h3>
          <ChartFrame
            label={`Reaction time across the extended test, first ${overTime[0].ms} ms, last ${overTime[overTime.length - 1].ms} ms. A rise towards the end can be a time-on-task effect.`}
            height={140}
          >
            <LineChart data={overTime} margin={{ top: 8, right: 16, bottom: 0, left: -8 }}>
              <CartesianGrid {...t.grid} />
              <XAxis dataKey="sec" type="number" {...t.axis} unit=" s" domain={[0, 180]} />
              <YAxis {...t.axis} unit=" ms" width={64} domain={['auto', 'auto']} />
              <Tooltip {...t.tooltip} formatter={(v) => [`${v} ms`, 'Reaction time']} />
              {lapseMs != null && (
                <ReferenceLine
                  y={lapseMs}
                  stroke={t.colors.warn}
                  strokeDasharray="5 4"
                  ifOverflow="extendDomain"
                />
              )}
              <Line
                dataKey="ms"
                stroke={t.colors.accent}
                strokeWidth={2}
                dot={{ r: 2 }}
                isAnimationActive={false}
              />
            </LineChart>
          </ChartFrame>
          <p className={styles.caption}>
            A slowdown towards the end of the 3 minutes is a known time-on-task effect. One test is
            not enough to judge it.
          </p>
        </>
      )}
    </div>
  );
}
