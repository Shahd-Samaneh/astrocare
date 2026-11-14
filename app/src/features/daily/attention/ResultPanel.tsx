// Owner: Shahd. Result of one attention test: median, lapses, false starts, % vs baseline.
import { Badge } from '../../../shared/components';
import type { TestResult } from '../api.attention';
import styles from './Attention.module.css';

export const EXPERIMENTAL_NOTE = 'Experimental. Does not decide fitness for duty.';

export function RangeBadge({ withinRange }: { withinRange: boolean | null }) {
  if (withinRange === null) return <Badge variant="neutral">No baseline yet</Badge>;
  return withinRange ? (
    <Badge variant="good">Within your usual range</Badge>
  ) : (
    <Badge variant="review">Outside your usual range</Badge>
  );
}

function pctText(pct: number | null) {
  if (pct === null) return '—';
  if (pct === 0) return '0 %';
  return `${pct > 0 ? '+' : '−'}${Math.abs(pct).toFixed(0)} %`;
}

export function ResultPanel({
  result,
  lastNightHours,
}: {
  result: TestResult;
  lastNightHours?: number | null;
}) {
  const { test, pctVsBaseline, withinRange, baseline } = result;
  return (
    <div className={styles.result}>
      <div className={styles.resultHead}>
        <RangeBadge withinRange={withinRange} />
        {test.context === 'retest' && <Badge variant="info">Retest</Badge>}
      </div>
      <dl className={styles.stats}>
        <div className={styles.stat}>
          <dt>Median</dt>
          <dd>
            <span className={styles.statValue}>{Math.round(test.medianMs)}</span> ms
          </dd>
        </div>
        <div className={styles.stat}>
          <dt>vs your baseline</dt>
          <dd>
            <span className={styles.statValue}>{pctText(pctVsBaseline)}</span>
            {baseline.medianMs != null && (
              <span className={styles.statSub}> of {Math.round(baseline.medianMs)} ms</span>
            )}
          </dd>
        </div>
        <div className={styles.stat}>
          <dt>Lapses</dt>
          <dd>
            <span className={styles.statValue}>{test.lapses}</span>
            <span className={styles.statSub}> of {test.trialsMs.length}</span>
          </dd>
        </div>
        <div className={styles.stat}>
          <dt>False starts</dt>
          <dd>
            <span className={styles.statValue}>{test.falseStarts}</span>
          </dd>
        </div>
      </dl>
      <p className={styles.meta}>
        Trials: {test.trialsMs.map((x) => `${Math.round(x)} ms`).join(' · ')}
        {baseline.rangeLowMs != null && baseline.rangeHighMs != null && (
          <>
            {' '}
            · Usual range {Math.round(baseline.rangeLowMs)}–{Math.round(baseline.rangeHighMs)} ms (
            {baseline.n} earlier tests)
          </>
        )}
      </p>
      {lastNightHours != null && (
        <p className={styles.meta}>
          Context: last night's sleep was <strong>{lastNightHours.toFixed(1)} h</strong>.
        </p>
      )}
      <p className={styles.experimental} role="note">
        {EXPERIMENTAL_NOTE}
      </p>
    </div>
  );
}
