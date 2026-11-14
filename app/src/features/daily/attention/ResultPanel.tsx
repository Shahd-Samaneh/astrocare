// Owner: Shahd. Result of one attention test: median, lapses, false starts, % vs baseline.
import { Badge, SimulatedBadge } from '../../../shared/components';
import type { TestResult } from '../api.attention';
import { KSS_ANCHORS } from './kss';
import { TrialPlot } from './TrialPlot';
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
  lapseMs = null,
}: {
  result: TestResult;
  lapseMs?: number | null;
}) {
  const { test, pctVsBaseline, withinRange, baseline } = result;
  const sleepContext = result.sleepContext ?? { sleptHours: null, hoursAwake: null, source: null };
  const extended = test.mode === 'extended';
  const building = baseline.building ?? false;
  const m = test.measures;
  return (
    <div className={styles.result}>
      <div className={styles.resultHead}>
        {building ? (
          <Badge variant="neutral">
            Building your baseline ({baseline.n}/{baseline.needed ?? 3})
          </Badge>
        ) : (
          <RangeBadge withinRange={withinRange} />
        )}
        {extended && <Badge variant="pink">Extended · Experimental, not validated</Badge>}
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
      {extended && m && (
        <dl className={styles.stats} aria-label="Extended test measures">
          <div className={styles.stat}>
            <dt>Mean RT</dt>
            <dd>
              <span className={styles.statValue}>{Math.round(m.meanMs)}</span> ms
            </dd>
          </div>
          <div className={styles.stat}>
            <dt>Fastest 10 %</dt>
            <dd>
              <span className={styles.statValue}>{Math.round(m.fastest10MeanMs)}</span> ms
            </dd>
          </div>
          <div className={styles.stat}>
            <dt>Slowest 10 %</dt>
            <dd>
              <span className={styles.statValue}>{Math.round(m.slowest10MeanMs)}</span> ms
            </dd>
          </div>
          <div className={styles.stat}>
            <dt>Response speed</dt>
            <dd>
              <span className={styles.statValue}>{m.responseSpeed.toFixed(2)}</span> 1/s
            </dd>
          </div>
        </dl>
      )}
      {result.inputDiffers && (
        <p className={styles.notice} role="note">
          Different input method from your usual tests ({test.inputMethod} vs{' '}
          {baseline.usualInputMethod}). Comparison may be less reliable.
        </p>
      )}
      {building && (
        <p className={styles.meta}>
          Building your baseline ({baseline.n}/{baseline.needed ?? 3}):{' '}
          {extended ? 'extended' : 'quick'} tests are only compared with tests of the same length.
          After {baseline.needed ?? 3} earlier tests you’ll see whether a result is within your
          usual range.
        </p>
      )}
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
      <p className={styles.meta}>
        Context (from your sleep log): slept{' '}
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
      {test.sleepinessKss != null && (
        <p className={styles.meta}>
          You rated sleepiness <strong>{test.sleepinessKss}/9</strong>
          {KSS_ANCHORS[test.sleepinessKss] ? ` (${KSS_ANCHORS[test.sleepinessKss]})` : ''}, next to
          a measured median of <strong>{Math.round(test.medianMs)} ms</strong>. Self-rating and
          measured speed can disagree. Both are useful.
        </p>
      )}
      <TrialPlot test={test} lapseMs={lapseMs} />
      <p className={styles.experimental} role="note">
        {EXPERIMENTAL_NOTE}
      </p>
    </div>
  );
}
