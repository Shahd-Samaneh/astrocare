// Recharts wrapper with the dark theme, plus a baseline band helper.
//
//   const t = useChartTheme();
//   <ChartFrame height={240} label="Heart rate, last 24 h">
//     <LineChart data={rows}>
//       <CartesianGrid {...t.grid} />
//       <XAxis dataKey="time" {...t.axis} />
//       <YAxis {...t.axis} domain={['auto', 'auto']} />
//       <Tooltip {...t.tooltip} />
//       {baselineBand(profile.baseline.heart_rate, 2, t)}
//       <Line dataKey="value" stroke={t.colors.accent} dot={false} />
//     </LineChart>
//   </ChartFrame>
//
// NOTE: Recharts reads its children's types, so baselineBand is a plain function that
// returns a <ReferenceArea>, not a component.
import type { ReactElement } from 'react';
import { useMemo } from 'react';
import { ReferenceArea, ResponsiveContainer } from 'recharts';
import type { Baseline } from '../types/contracts';
import styles from './ChartFrame.module.css';

export interface ChartFrameProps {
  /** Accessible description of the chart. */
  label: string;
  height?: number;
  children: ReactElement;
}

export function ChartFrame({ label, height = 220, children }: ChartFrameProps) {
  return (
    <figure className={styles.frame} style={{ height }} aria-label={label} role="img">
      <ResponsiveContainer width="100%" height="100%">
        {children}
      </ResponsiveContainer>
    </figure>
  );
}

function token(name: string): string {
  if (typeof window === 'undefined') return '';
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

export interface ChartTheme {
  colors: { accent: string; pink: string; ok: string; warn: string; danger: string; band: string };
  grid: { stroke: string; strokeDasharray: string; vertical: boolean };
  axis: { stroke: string; tick: { fill: string; fontSize: number }; tickLine: boolean };
  tooltip: {
    contentStyle: Record<string, string | number>;
    labelStyle: Record<string, string>;
    itemStyle: Record<string, string>;
  };
}

/** Theme props resolved from the CSS tokens (so charts follow tokens.css). */
// eslint-disable-next-line react-refresh/only-export-components
export function useChartTheme(): ChartTheme {
  return useMemo(() => {
    const border = token('--border');
    return {
      colors: {
        accent: token('--accent'),
        pink: token('--pink'),
        ok: token('--ok'),
        warn: token('--warn'),
        danger: token('--danger'),
        band: token('--accent-2'),
      },
      grid: { stroke: border, strokeDasharray: '3 3', vertical: false },
      axis: { stroke: border, tick: { fill: token('--text-faint'), fontSize: 11 }, tickLine: false },
      tooltip: {
        contentStyle: {
          background: token('--bg-card'),
          border: `1px solid ${token('--border-strong')}`,
          borderRadius: 10,
          color: token('--text'),
          fontSize: 12,
        },
        labelStyle: { color: token('--text-muted') },
        itemStyle: { color: token('--text') },
      },
    };
  }, []);
}

/** Personal baseline band: mean ± k·SD as a shaded ReferenceArea. */
// eslint-disable-next-line react-refresh/only-export-components
export function baselineBand(baseline: Baseline | undefined, k: number, theme: ChartTheme) {
  if (!baseline) return null;
  return (
    <ReferenceArea
      key="baseline-band"
      y1={baseline.mean - k * baseline.sd}
      y2={baseline.mean + k * baseline.sd}
      fill={theme.colors.band}
      fillOpacity={0.08}
      stroke={theme.colors.band}
      strokeOpacity={0.25}
      strokeDasharray="4 4"
      ifOverflow="extendDomain"
    />
  );
}
