// Owner: Shahd. Result of one attention test: median, % vs baseline, lapses, false starts,
// and last night's sleep as context.
import { Badge, SimulatedBadge } from '../../../shared/components';
import { rangeStatusOf, type RangeStatus, type TestResult } from '../api.attention';
import styles from './Attention.module.css';

export const EXPERIMENTAL_NOTE = 'Experimental. Does not decide fitness for duty.';

/** Only a result slower by >= attention_slower_pct is shown as needing review. */
export function RangeBadge({ status }: { status: RangeStatus | null }) {
  switch (status) {
    case null:
      return <Badge variant="neutral">No baseline yet</Badge>;
    case 'within':
      return <Badge variant="good">Within your usual range</Badge>;
    case 'faster':
      return <Badge variant="info">Faster than usual</Badge>;
    case 'slower':
      return <Badge variant="neutral">A little slower than usual</Badge>;
    case 'flagged':
      return <Badge variant="review">Slower than usual</Badge>;
  }
}

function pctText(pct: number | null) {
  if (pct === null) return '—';
  if (pct === 0) return '0 %';
  return `${pct > 0 ? '+' : '−'}${Math.abs(pct).toFixed(0)} %`;
}

export function ResultPanel({ result }: { result: TestResult }) {
  const { test, pctVsBaseline, withinRange, baseline } = result;
  const sleepContext = result.sleepContext ?? { sleptHours: null, hoursAwake: null, source: null };
  const building = baseline.building ?? false;
  return (
    <div className={styles.result}>
      <div className={styles.resultHead}>
        {building ? (
          <Badge variant="neutral">
            Building your baseline ({baseline.n}/{baseline.needed ?? 3})
          </Badge>
        ) : (
          <RangeBadge status={rangeStatusOf(result.rangeStatus, withinRange, pctVsBaseline)} />
        )}
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
          <dt>vs your baseline{building ? ' (preliminary)' : ''}</dt>
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
            <span className={styles.statSub}> of {test.trialsMs.length} responses</span>
          </dd>
        </div>
        <div className={styles.stat}>
          <dt>False starts</dt>
          <dd>
            <span className={styles.statValue}>{test.falseStarts}</span>
          </dd>
        </div>
      </dl>
      {building ? (
        <p className={styles.meta}>
          After {baseline.needed ?? 3} earlier tests you’ll see whether a result is within your
          usual range.
        </p>
      ) : (
        baseline.rangeLowMs != null &&
        baseline.rangeHighMs != null && (
          <p className={styles.meta}>
            Your usual range: {Math.round(baseline.rangeLowMs)}–{Math.round(baseline.rangeHighMs)}{' '}
            ms ({baseline.n} earlier tests).
          </p>
        )
      )}
      <p className={styles.meta}>
        Last night (from your sleep log): slept{' '}
        <strong>
          {sleepContext.sleptHours != null ? `${sleepContext.sleptHours.toFixed(1)} h` : '—'}
        </strong>{' '}
        · awake for{' '}
        <strong>
          {sleepContext.hoursAwake != null ? `${Math.round(sleepContext.hoursAwake)} h` : '—'}
        </strong>
        {sleepContext.source && (
          <>
            {' '}
            <SimulatedBadge source={sleepContext.source} />
          </>
        )}
      </p>
      <p className={styles.experimental} role="note">
        {EXPERIMENTAL_NOTE}
      </p>
    </div>
  );
}
