// Marks any value whose `source` is 'simulated'. Renders nothing for other sources.
//   <SimulatedBadge source={reading.source} />
import type { Source } from '../types/contracts';
import styles from './SimulatedBadge.module.css';

export function SimulatedBadge({ source = 'simulated' }: { source?: Source }) {
  if (source !== 'simulated') return null;
  return (
    <span className={styles.chip} title="Simulated value (not from a real sensor)">
      SIM
      <span className="sr-only"> simulated data</span>
    </span>
  );
}
