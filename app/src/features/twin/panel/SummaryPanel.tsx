// Default panel (nothing selected): one summary line plus every region with its status chip.
// Each row is a button, so keyboard and screen-reader users can select regions without the 3D view.
import type { RegionId, TwinRegion } from '../types';
import { REGION_SHORT, bySeverity, overallSummary } from '../twinView';
import { StatusBadge } from './RegionCard';
import styles from './Panel.module.css';

export function SummaryPanel({ regions, onSelect }: { regions: TwinRegion[]; onSelect: (id: RegionId) => void }) {
  return (
    <section className={styles.card} aria-labelledby="twin-summary-title">
      <h2 id="twin-summary-title" className={styles.title}>
        Overview
      </h2>
      <p className={styles.headline} aria-live="polite">
        {overallSummary(regions)}
      </p>
      <ul className={styles.regionList} aria-label="Body regions">
        {bySeverity(regions).map((r) => (
          <li key={r.id}>
            <button type="button" className={styles.regionButton} onClick={() => onSelect(r.id)}>
              <span className={styles.regionName}>{REGION_SHORT[r.id]}</span>
              <StatusBadge region={r} />
              <span className={styles.regionHeadline}>{r.headline}</span>
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
