// One vital sign tile. States: normal, stale (dimmed + note), missing ("—" + Enter manually).
//   <VitalCard label="Heart rate" value={64} unit="bpm" ts={r.ts} quality="good"
//              sensorName="Chest strap" sensorStatus="connected" source="simulated" sparkline={<Spark/>} />
//   <VitalCard label="Blood pressure" quality="missing" manualTo="/vitals" />
import type { ReactNode } from 'react';
import { PenLine } from 'lucide-react';
import type { Quality, SensorStatus, Source } from '../types/contracts';
import { formatTime, relativeTime } from '../utils/format';
import { Badge } from './Badge';
import { Button } from './Button';
import { SimulatedBadge } from './SimulatedBadge';
import styles from './VitalCard.module.css';

export interface VitalCardProps {
  label: string;
  value?: number | string | null;
  unit?: string;
  ts?: string | null;
  quality: Quality;
  source?: Source;
  sensorName?: string | null;
  sensorStatus?: SensorStatus | null;
  /** Optional mini chart (e.g. a Recharts <LineChart> inside ChartFrame). */
  sparkline?: ReactNode;
  /** For the missing state: route of the manual entry form … */
  manualTo?: string;
  /** … or a click handler. */
  onEnterManually?: () => void;
}

const SENSOR_LABEL: Record<SensorStatus, string> = {
  connected: 'Sensor connected',
  disconnected: 'Sensor disconnected',
  low_battery: 'Sensor low battery',
};

export function VitalCard(props: VitalCardProps) {
  const { label, value, unit, ts, quality, source, sensorName, sensorStatus, sparkline } = props;
  const state = quality === 'missing' || value === null || value === undefined ? 'missing' : quality === 'stale' ? 'stale' : 'normal';

  return (
    <article className={`${styles.card} ${styles[state]}`} aria-label={`${label}: ${state === 'missing' ? 'no reading' : `${value} ${unit ?? ''}`}`}>
      <div className={styles.head}>
        <span className={styles.label}>{label}</span>
        <span className={styles.badges}>
          {source && state !== 'missing' && <SimulatedBadge source={source} />}
          <Badge variant={state === 'missing' ? 'missing' : quality} />
        </span>
      </div>

      <div className={styles.valueRow}>
        <span className={styles.value}>{state === 'missing' ? '—' : value}</span>
        {state !== 'missing' && unit && <span className={styles.unit}>{unit}</span>}
      </div>

      {state === 'stale' && ts && <p className={styles.note}>Last reading {relativeTime(ts)}</p>}
      {state === 'missing' && <p className={styles.note}>No reading today</p>}
      {state === 'normal' && ts && <p className={styles.meta}>at {formatTime(ts)}</p>}

      {sparkline && state !== 'missing' && <div className={styles.spark}>{sparkline}</div>}

      <div className={styles.foot}>
        {sensorStatus && (
          <span className={`${styles.sensor} ${styles[sensorStatus]}`}>
            <span className={styles.dot} aria-hidden />
            {sensorName ? `${sensorName} · ` : ''}
            {SENSOR_LABEL[sensorStatus]}
          </span>
        )}
        {state === 'missing' && (props.manualTo || props.onEnterManually) && (
          props.manualTo ? (
            <Button variant="secondary" to={props.manualTo} icon={<PenLine size={16} />}>
              Enter manually
            </Button>
          ) : (
            <Button variant="secondary" onClick={props.onEnterManually} icon={<PenLine size={16} />}>
              Enter manually
            </Button>
          )
        )}
      </div>
    </article>
  );
}

/** Alias: same tile for non-vital stats. */
export const StatTile = VitalCard;
