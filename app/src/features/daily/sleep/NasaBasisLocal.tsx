// TEMPORARY local stand-in for Shahd's NasaBasis (features/daily/common/NasaBasis).
// When hers exists, replace the imports of this file with hers. It takes the same idea:
// a short "Why we track this" text in our own words plus the source titles (no URLs here:
// links live on the backend, GET /api/daily/sources).
import { NASA_SOURCE_TITLES } from './nasaSourceTitles';
import styles from './NasaBasisLocal.module.css';

export interface NasaBasisLocalProps {
  sourceIds: string[];
  why: string;
}

export function NasaBasisLocal({ sourceIds, why }: NasaBasisLocalProps) {
  return (
    <details className={styles.panel}>
      <summary className={styles.summary}>Why we track this</summary>
      <p className={styles.why}>{why}</p>
      <p className={styles.label}>Sources (listed for reference; not an endorsement by NASA)</p>
      <ul className={styles.list}>
        {sourceIds.map((id) => (
          <li key={id}>{NASA_SOURCE_TITLES[id] ?? id}</li>
        ))}
      </ul>
    </details>
  );
}
