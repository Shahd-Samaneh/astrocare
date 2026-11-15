// Owner: Shahd. Attention check: a 5-trial reaction-time test (PVT-style).
//   /attention                    routine test
//   /attention?retest=<alertId>   retest for an alert (e.g. R-FAT-01): saved with context 'retest'
// Experimental. Does not decide fitness for duty.
import { ArrowLeft, Play, RotateCcw, Timer } from 'lucide-react';
import { useCallback, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { ApiError, useApi } from '../../../shared/api/client';
import { useAppStatus } from '../../../shared/api/AppStatusContext';
import { Button, Card, ErrorState, LoadingState, PageHeader } from '../../../shared/components';
import {
  paths,
  postTest,
  type AttentionBaseline,
  type DailyAlert,
  type DailyCognitiveTest,
  type DailySummary,
  type DailyThresholds,
  type InputMethod,
  type TestResult,
} from '../api.attention';
import { EXPERIMENTAL_NOTE, ResultPanel } from '../attention/ResultPanel';
import { RetestCompare } from '../attention/RetestCompare';
import { SleepRtChart } from '../attention/SleepRtChart';
import { TestRunner } from '../attention/TestRunner';
import {
  NO_RESPONSE_MS,
  TRIALS,
  isRunning,
  useReactionTest,
  type RawResult,
} from '../attention/useReactionTest';
import styles from '../attention/Attention.module.css';
import { NasaBasis } from '../common/NasaBasis';

type Saving =
  { state: 'idle' } | { state: 'saving' } | { state: 'error'; message: string; raw: RawResult };

const WHY =
  'Tiredness can slow reactions before you notice it yourself. A one-minute test, compared with your own usual range, ' +
  'helps spot that early.';

export default function AttentionCheck() {
  const [params] = useSearchParams();
  const retestId = params.get('retest');
  const { status } = useAppStatus();

  // tests feed the 14-day chart (it uses the last 14 days of routine quick tests)
  const history = useApi<DailyCognitiveTest[]>(paths.tests(200));
  const baseline = useApi<AttentionBaseline>(paths.baseline);
  const summary = useApi<DailySummary>(paths.summary(14));
  const thresholds = useApi<DailyThresholds>(paths.thresholds);
  const alert = useApi<DailyAlert>(retestId ? paths.alert(retestId) : null);

  const [result, setResult] = useState<TestResult>();
  const [saving, setSaving] = useState<Saving>({ state: 'idle' });

  const save = useCallback(
    async (raw: RawResult) => {
      if (!raw.trialsMs.length) {
        setSaving({ state: 'error', message: 'no responses were recorded', raw });
        return;
      }
      setSaving({ state: 'saving' });
      try {
        const r = await postTest({
          trialsMs: raw.trialsMs,
          falseStarts: raw.falseStarts,
          mode: raw.mode,
          trialOffsetsMs: raw.offsetsMs,
          inputMethod: raw.inputMethod,
          ...(retestId ? { context: 'retest' as const, relatedAlertId: retestId } : {}),
        });
        setResult(r);
        setSaving({ state: 'idle' });
        history.reload();
        baseline.reload();
        summary.reload();
      } catch (e) {
        const message = e instanceof ApiError ? e.message : String(e);
        setSaving({ state: 'error', message, raw });
      }
    },
    [retestId, history, baseline, summary],
  );

  const test = useReactionTest(save);
  const running = isRunning(test.state.phase);
  const respond = useCallback((m: InputMethod) => test.respond(m), [test]);
  const cancel = useCallback(() => test.cancel(), [test]);
  const backToIntro = () => {
    setResult(undefined);
    setSaving({ state: 'idle' });
  };
  const start = () => {
    setResult(undefined);
    setSaving({ state: 'idle' });
    test.start();
  };

  const dateText = new Date().toLocaleDateString('en-GB', {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
  });
  const eyebrow = `Daily · ${status ? `Mission day ${status.missionDay} · ` : ''}${dateText}`;
  const ruleLabel = alert.data?.ruleId ?? 'R-FAT-01';

  return (
    <>
      <PageHeader eyebrow={eyebrow} title="Attention check" />

      {retestId && (
        <div className={styles.retestBanner} role="status">
          <RotateCcw size={18} aria-hidden />
          <span>
            <strong>Retest for alert {ruleLabel}</strong>
            {alert.data ? ` · ${alert.data.title}` : ''}. The result is linked to the alert and
            moves it to “recheck”.
          </span>
          {alert.error && (
            <span className={styles.meta}>
              (alert not found: the result is still saved as a retest)
            </span>
          )}
        </div>
      )}

      <div className={styles.column}>
        <Card
          title={running ? 'Test in progress' : result ? 'Your result' : 'Reaction-time test'}
          subtitle={running ? 'Esc cancels' : `${TRIALS} trials, about 1 minute`}
        >
          {running ? (
            <TestRunner state={test.state} onRespond={respond} onCancel={cancel} />
          ) : saving.state === 'saving' ? (
            <LoadingState label="Saving your result…" />
          ) : saving.state === 'error' ? (
            <ErrorState
              message={`Your result was not saved: ${saving.message}`}
              onRetry={() => save(saving.raw)}
            />
          ) : result ? (
            <>
              {result.retest && <RetestCompare cmp={result.retest} />}
              <ResultPanel result={result} />
              <div className={styles.row}>
                {retestId && !result.retest && (
                  <Button
                    to={`/alerts/${encodeURIComponent(retestId)}`}
                    icon={<ArrowLeft size={16} />}
                  >
                    Back to the alert
                  </Button>
                )}
                <Button variant="secondary" onClick={backToIntro} icon={<Play size={16} />}>
                  Test again
                </Button>
              </div>
            </>
          ) : (
            <div className={styles.intro}>
              <p>
                A circle will light up after a random wait. Respond as fast as you can: click, tap
                or press <kbd>Space</kbd>.
              </p>
              <ul className={styles.facts}>
                <li>{TRIALS} trials, each after a wait of 2–8 seconds: about 1 minute in total.</li>
                <li>
                  Responding too early is a false start, and that trial repeats. No response within{' '}
                  {NO_RESPONSE_MS / 1000} seconds counts as missed (a lapse).
                </li>
                <li>Your median is compared with your own usual range, not with other people.</li>
              </ul>
              <p className={styles.experimental} role="note">
                {EXPERIMENTAL_NOTE}
              </p>
              <div className={styles.row}>
                <Button onClick={start} icon={<Timer size={16} />} autoFocus>
                  {retestId ? 'Start retest' : 'Start'}
                </Button>
              </div>
            </div>
          )}
        </Card>

        {!running && (
          <Card
            title="Sleep and reaction time, last 14 days"
            subtitle="Sleep per night (bars) and daily median of routine tests (line)"
          >
            {(summary.loading && !summary.data) || (history.loading && !history.data) ? (
              <LoadingState />
            ) : summary.error ? (
              <ErrorState message={summary.error.message} onRetry={summary.reload} />
            ) : (
              <SleepRtChart
                nights={summary.data?.sleep?.nights ?? []}
                tests={history.data ?? []}
                baseline={baseline.data}
                thresholds={thresholds.data}
                lastDay={status?.missionDay}
              />
            )}
          </Card>
        )}

        <NasaBasis
          variant="test"
          ids={['nasa-pvt-iss', 'nasa-hrp-bmed-risk', 'nasa-hrp-sleep-risk']}
          why={WHY}
        />
      </div>
    </>
  );
}
