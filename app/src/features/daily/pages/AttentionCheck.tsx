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
  type TestMode,
  type TestResult,
} from '../api.attention';
import { HistoryChart } from '../attention/HistoryChart';
import { EXPERIMENTAL_NOTE, ResultPanel } from '../attention/ResultPanel';
import { SleepRtChart } from '../attention/SleepRtChart';
import { SleepinessQuestion } from '../attention/SleepinessQuestion';
import { TestRunner } from '../attention/TestRunner';
import {
  TRIALS,
  isRunning,
  loadPracticeDefault,
  markFirstTestDone,
  savePracticeChoice,
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

  const history = useApi<DailyCognitiveTest[]>(paths.tests(100));
  const baseline = useApi<AttentionBaseline>(paths.baseline);
  const summary = useApi<DailySummary>(paths.summary(14));
  const thresholds = useApi<DailyThresholds>(paths.thresholds);
  const alert = useApi<DailyAlert>(retestId ? paths.alert(retestId) : null);

  const [result, setResult] = useState<TestResult>();
  const [saving, setSaving] = useState<Saving>({ state: 'idle' });
  const [practice, setPractice] = useState(loadPracticeDefault);
  const [kss, setKss] = useState<number | null | undefined>(undefined);
  const [mode, setMode] = useState<TestMode>('quick');

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
          sleepinessKss: kss ?? null,
          ...(retestId ? { context: 'retest' as const, relatedAlertId: retestId } : {}),
        });
        setResult(r);
        setSaving({ state: 'idle' });
        markFirstTestDone();
        history.reload();
        baseline.reload();
        summary.reload();
      } catch (e) {
        const message = e instanceof ApiError ? e.message : String(e);
        setSaving({ state: 'error', message, raw });
      }
    },
    [retestId, kss, history, baseline, summary],
  );

  const test = useReactionTest(save);
  const phase = test.state.phase;
  const running = isRunning(phase);
  const respond = useCallback(() => test.respond(), [test]);
  const cancel = useCallback(() => test.cancel(), [test]);
  const backToIntro = () => {
    setResult(undefined);
    setSaving({ state: 'idle' });
    setKss(undefined); // a fresh rating for each test
  };
  const start = () => {
    setResult(undefined);
    setSaving({ state: 'idle' });
    test.start({ practice, mode });
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
          subtitle={
            running
              ? 'Esc cancels'
              : mode === 'extended'
                ? '3 minutes · Experimental, not validated'
                : `${TRIALS} trials, about 1 minute`
          }
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
                <Button variant="secondary" onClick={backToIntro} icon={<Play size={16} />}>
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
              <fieldset className={styles.modes}>
                <legend className="sr-only">Test length</legend>
                <label className={styles.modeOption}>
                  <input
                    type="radio"
                    name="pvt-mode"
                    value="quick"
                    checked={mode === 'quick'}
                    onChange={() => setMode('quick')}
                  />
                  <span>
                    <span className={styles.modeTitle}>Quick</span>
                    <br />
                    <span className={styles.modeDesc}>{TRIALS} trials, ~1 min. The default.</span>
                  </span>
                </label>
                <label className={styles.modeOption}>
                  <input
                    type="radio"
                    name="pvt-mode"
                    value="extended"
                    checked={mode === 'extended'}
                    onChange={() => setMode('extended')}
                  />
                  <span>
                    <span className={styles.modeTitle}>Extended (3 minutes)</span>
                    <br />
                    <span className={styles.modeDesc}>
                      Experimental, not validated. More measures, compared only with your other
                      extended tests.
                    </span>
                  </span>
                </label>
              </fieldset>
              <ul className={styles.facts}>
                {mode === 'quick' ? (
                  <>
                    <li>
                      {TRIALS} trials, each after a wait of 2–8 seconds: about 1 minute in total.
                    </li>
                    <li>Responding before the light is a false start, and that trial repeats.</li>
                  </>
                ) : (
                  <>
                    <li>
                      Lights keep coming after waits of 2–10 seconds until 3 minutes have passed.
                    </li>
                    <li>Responding before the light is a false start. It is counted.</li>
                  </>
                )}
                <li>
                  Your median time is compared with your own usual range for the same test length,
                  not with other people.
                </li>
              </ul>
              <SleepinessQuestion value={kss} onChange={setKss} />
              <label className={styles.check}>
                <input
                  type="checkbox"
                  checked={practice}
                  onChange={(e) => {
                    setPractice(e.target.checked);
                    savePracticeChoice(e.target.checked);
                  }}
                />
                Start with one practice trial (Practice: not counted)
              </label>
              <div className={styles.row}>
                <Button onClick={start} icon={<Timer size={16} />} autoFocus>
                  {retestId
                    ? 'Start retest'
                    : mode === 'extended'
                      ? 'Start extended test'
                      : 'Start'}
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
