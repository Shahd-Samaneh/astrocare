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
  type TestResult,
} from '../api.attention';
import { HistoryChart } from '../attention/HistoryChart';
import { EXPERIMENTAL_NOTE, ResultPanel } from '../attention/ResultPanel';
import { SleepRtChart } from '../attention/SleepRtChart';
import { TestRunner } from '../attention/TestRunner';
import { TRIALS, isRunning, useReactionTest } from '../attention/useReactionTest';
import styles from '../attention/Attention.module.css';
import { NasaBasis } from '../common/NasaBasis';

type Saving =
  | { state: 'idle' }
  | { state: 'saving' }
  | { state: 'error'; message: string; trials: number[]; falseStarts: number };

const WHY =
  'Tiredness can slow reactions before you notice it yourself. A one-minute test, compared with your own usual range, ' +
  'helps spot that early.';

export default function AttentionCheck() {
  const [params] = useSearchParams();
  const retestId = params.get('retest');
  const { status } = useAppStatus();

  const history = useApi<DailyCognitiveTest[]>(paths.tests(100));
  const baseline = useApi<AttentionBaseline>(paths.baseline);
  const summary = useApi<DailySummary>(paths.summary(14));
  const thresholds = useApi<DailyThresholds>(paths.thresholds);
  const alert = useApi<DailyAlert>(retestId ? paths.alert(retestId) : null);

  const [result, setResult] = useState<TestResult>();
  const [saving, setSaving] = useState<Saving>({ state: 'idle' });

  const save = useCallback(
    async (trialsMs: number[], falseStarts: number) => {
      setSaving({ state: 'saving' });
      try {
        const r = await postTest({
          trialsMs,
          falseStarts,
          ...(retestId ? { context: 'retest' as const, relatedAlertId: retestId } : {}),
        });
        setResult(r);
        setSaving({ state: 'idle' });
        history.reload();
        baseline.reload();
        summary.reload();
      } catch (e) {
        const message = e instanceof ApiError ? e.message : String(e);
        setSaving({ state: 'error', message, trials: trialsMs, falseStarts });
      }
    },
    [retestId, history, baseline, summary],
  );

  const test = useReactionTest(save);
  const phase = test.state.phase;
  const running = isRunning(phase);
  const respond = useCallback(() => test.respond(), [test]);
  const cancel = useCallback(() => test.cancel(), [test]);
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
              onRetry={() => save(saving.trials, saving.falseStarts)}
            />
          ) : result ? (
            <>
              <ResultPanel result={result} />
              <div className={styles.row}>
                {retestId && (
                  <Button
                    to={`/alerts/${encodeURIComponent(retestId)}`}
                    icon={<ArrowLeft size={16} />}
                  >
                    Back to the alert
                  </Button>
                )}
                <Button variant="secondary" onClick={start} icon={<Play size={16} />}>
                  Test again
                </Button>
              </div>
            </>
          ) : (
            <div className={styles.intro}>
              <p>
                A light will appear after a random wait. Respond as fast as you can by clicking,
                tapping or pressing <kbd>Space</kbd>.
              </p>
              <ul className={styles.facts}>
                <li>{TRIALS} trials, each after a wait of 2–8 seconds: about 1 minute in total.</li>
                <li>Responding before the light is a false start, and that trial repeats.</li>
                <li>
                  Your median time is compared with your own usual range, not with other people.
                </li>
              </ul>
              <div className={styles.row}>
                <Button onClick={start} icon={<Timer size={16} />} autoFocus>
                  {retestId ? 'Start retest' : 'Start'}
                </Button>
              </div>
              <p className={styles.experimental} role="note">
                {EXPERIMENTAL_NOTE}
              </p>
            </div>
          )}
        </Card>

        {!running && (
          <Card
            title="Last 10 tests"
            subtitle="Median reaction time over your usual range (shaded)"
          >
            {history.loading && !history.data ? (
              <LoadingState />
            ) : history.error ? (
              <ErrorState message={history.error.message} onRetry={history.reload} />
            ) : (
              <HistoryChart tests={(history.data ?? []).slice(0, 10)} baseline={baseline.data} />
            )}
          </Card>
        )}

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
