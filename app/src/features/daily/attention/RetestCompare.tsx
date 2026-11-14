// Owner: Shahd. Retest mode: Before (the routine median that triggered the alert) vs
// After (this retest), the difference, and the alert's new status. Never closes the alert:
// closing is a human decision.
import { ArrowLeft } from 'lucide-react';
import { Badge, Button } from '../../../shared/components';
import type { RetestComparison } from '../api.attention';
import styles from './Attention.module.css';

function signed(v: number, unit: string) {
  return `${v > 0 ? '+' : v < 0 ? '−' : ''}${Math.abs(v).toFixed(0)} ${unit}`;
}

export function RetestCompare({ cmp }: { cmp: RetestComparison }) {
  const faster = cmp.diffMs != null && cmp.diffMs < 0;
  return (
    <section
      className={styles.compare}
      aria-label={`Retest for alert ${cmp.ruleId}: before and after`}
    >
      <dl className={styles.compareGrid}>
        <div className={styles.stat}>
          <dt className={styles.compareLabel}>Before</dt>
          <dd>
            <span className={styles.statValue}>
              {cmp.beforeMedianMs != null ? Math.round(cmp.beforeMedianMs) : '—'}
            </span>{' '}
            ms
            <span className={styles.statSub}>
              {' '}
              routine median that triggered {cmp.ruleId}
              {cmp.beforeTestIds.length ? ` (${cmp.beforeTestIds.length} tests)` : ''}
            </span>
          </dd>
        </div>
        <div className={styles.stat}>
          <dt className={styles.compareLabel}>After</dt>
          <dd>
            <span className={styles.statValue}>{Math.round(cmp.afterMedianMs)}</span> ms
            <span className={styles.statSub}> this retest</span>
          </dd>
        </div>
        <div className={styles.stat}>
          <dt className={styles.compareLabel}>Difference</dt>
          <dd>
            <span className={styles.statValue}>
              {cmp.diffMs != null ? signed(cmp.diffMs, 'ms') : '—'}
            </span>
            {cmp.diffPct != null && (
              <span className={styles.statSub}> ({signed(cmp.diffPct, '%')})</span>
            )}
            {cmp.diffMs != null && (
              <span className={styles.statSub}>
                {faster ? ' faster' : cmp.diffMs > 0 ? ' slower' : ''}
              </span>
            )}
          </dd>
        </div>
        <div className={styles.stat}>
          <dt className={styles.compareLabel}>Alert status</dt>
          <dd>
            <Badge variant={cmp.alertStatus === 'recheck' ? 'info' : 'neutral'}>
              {cmp.alertStatus}
            </Badge>
          </dd>
        </div>
      </dl>
      <p className={styles.meta}>
        The alert stays open. Closing it is a human decision. One retest doesn't confirm or rule out
        fatigue.
      </p>
      <div>
        <Button to={`/alerts/${encodeURIComponent(cmp.alertId)}`} icon={<ArrowLeft size={16} />}>
          Back to the alert
        </Button>
      </div>
    </section>
  );
}
