// Owner: Shahd. The large response area for the running test.
// Click, tap or Space responds. Esc cancels. Space is handled on window only (not on the
// element) so a focused element never counts one key press twice.
// PVT-style display: when the stimulus appears, a millisecond counter counts up from 0;
// on the response it freezes on the reaction time for ~1 s. With prefers-reduced-motion
// a static highlighted target is shown instead. The counter is display only: the
// measured time always comes from the controller (useReactionTest), so timing is identical.
import { useEffect, useRef, useState } from 'react';
import { Button } from '../../../shared/components';
import type { InputMethod } from '../api.attention';
import { EXTENDED_DURATION_MS, TRIALS, isRunning, type ReactionState } from './useReactionTest';
import styles from './Attention.module.css';

export interface TestRunnerProps {
  state: ReactionState;
  onRespond: (method: InputMethod) => void;
  onCancel: () => void;
}

const MESSAGE: Record<string, { big: string; small: string }> = {
  waiting: { big: 'Wait…', small: 'Respond as soon as the circle lights up.' },
  stimulus: { big: 'Now!', small: 'Click, tap or press Space.' },
  falseStart: { big: 'Too soon', small: 'That was before the signal. Wait for the next one.' },
};

function usePrefersReducedMotion(): boolean {
  const query = '(prefers-reduced-motion: reduce)';
  const [reduced, setReduced] = useState(() =>
    typeof window !== 'undefined' && window.matchMedia ? window.matchMedia(query).matches : false,
  );
  useEffect(() => {
    if (!window.matchMedia) return;
    const mq = window.matchMedia(query);
    const on = () => setReduced(mq.matches);
    mq.addEventListener('change', on);
    return () => mq.removeEventListener('change', on);
  }, []);
  return reduced;
}

/** Counts up from 0 ms while mounted (requestAnimationFrame). Display only. */
function CountingMs() {
  const [ms, setMs] = useState(0);
  useEffect(() => {
    const t0 = performance.now();
    let raf = 0;
    const tick = () => {
      setMs(performance.now() - t0);
      raf = window.requestAnimationFrame(tick);
    };
    raf = window.requestAnimationFrame(tick);
    return () => window.cancelAnimationFrame(raf);
  }, []);
  return <>{String(Math.floor(ms)).padStart(3, '0')}</>;
}

function mmss(ms: number) {
  const s = Math.max(0, Math.floor(ms / 1000));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
}

/** Extended mode: elapsed time of the 3 minutes (updated 4× a second). */
function ExtendedProgress({ startedAt, responses }: { startedAt?: number; responses: number }) {
  const [now, setNow] = useState(() => performance.now());
  useEffect(() => {
    const id = window.setInterval(() => setNow(performance.now()), 250);
    return () => window.clearInterval(id);
  }, []);
  const elapsed = startedAt === undefined ? 0 : Math.min(EXTENDED_DURATION_MS, now - startedAt);
  return (
    <>
      <span
        className={styles.progress}
        aria-label={`Extended test: ${mmss(elapsed)} of ${mmss(EXTENDED_DURATION_MS)}, ${responses} responses`}
      >
        {mmss(elapsed)} / {mmss(EXTENDED_DURATION_MS)}
      </span>
      <progress className={styles.timeBar} max={EXTENDED_DURATION_MS} value={elapsed} aria-hidden />
      <span className={styles.meta}>{responses} responses</span>
    </>
  );
}

export function TestRunner({ state, onRespond, onCancel }: TestRunnerProps) {
  const areaRef = useRef<HTMLDivElement>(null);
  const running = isRunning(state.phase);
  const reducedMotion = usePrefersReducedMotion();

  useEffect(() => {
    areaRef.current?.focus();
  }, []);

  useEffect(() => {
    if (!running) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.code === 'Space' || e.key === ' ') {
        e.preventDefault();
        if (!e.repeat) onRespond('keyboard');
      } else if (e.key === 'Escape') {
        e.preventDefault();
        onCancel();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [running, onRespond, onCancel]);

  const trialNo = Math.min(state.trialsMs.length + 1, TRIALS);
  const msg =
    state.phase === 'feedback'
      ? {
          big: `${Math.round(state.lastMs ?? 0)} ms`,
          small: state.lastWasPractice
            ? 'Practice done (not counted). The real test starts now.'
            : 'Get ready for the next one.',
        }
      : state.practicing && state.phase === 'falseStart'
        ? { big: 'Too soon', small: 'Practice: wait for the signal, then respond.' }
        : state.phase === 'falseStart' && state.mode === 'quick'
          ? { big: 'Too soon', small: 'That was before the signal. This trial will repeat.' }
          : (MESSAGE[state.phase] ?? MESSAGE.waiting);
  const progressLabel = state.practicing
    ? 'Practice: not counted'
    : `Trial ${trialNo} of ${TRIALS}`;

  return (
    <div className={styles.runner}>
      <div className={styles.runnerHead}>
        {state.practicing ? (
          <span className={`${styles.progress} ${styles.practice}`}>Practice: not counted</span>
        ) : state.mode === 'extended' ? (
          <ExtendedProgress startedAt={state.startedAt} responses={state.trialsMs.length} />
        ) : (
          <span className={styles.progress} aria-label={progressLabel}>
            Trial {trialNo}/{TRIALS}
          </span>
        )}
        <ol
          className={`${styles.dots} ${state.mode === 'extended' ? styles.hidden : ''}`}
          aria-hidden
        >
          {Array.from({ length: TRIALS }, (_, i) => (
            <li
              key={i}
              className={
                i < state.trialsMs.length
                  ? styles.dotDone
                  : i === state.trialsMs.length
                    ? styles.dotNow
                    : ''
              }
            />
          ))}
        </ol>
        <Button variant="ghost" onClick={onCancel} aria-label="Cancel the test (Esc)">
          Cancel (Esc)
        </Button>
      </div>

      <div
        ref={areaRef}
        role="button"
        tabIndex={0}
        aria-label="Response area. Respond when the circle lights up: click, tap or press Space."
        aria-describedby="pvt-live"
        className={`${styles.target} ${styles[`phase_${state.phase}`] ?? ''}`}
        onPointerDown={(e) => {
          e.preventDefault();
          onRespond(e.pointerType === 'mouse' ? 'mouse' : 'touch'); // pen counts as touch
        }}
      >
        {state.phase === 'stimulus' && !reducedMotion ? (
          <span className={styles.counter} aria-hidden>
            <CountingMs />
            <span className={styles.counterUnit}>ms</span>
          </span>
        ) : state.phase === 'feedback' ? (
          <span className={`${styles.counter} ${styles.counterFrozen}`} aria-hidden>
            {Math.round(state.lastMs ?? 0)}
            <span className={styles.counterUnit}>ms</span>
          </span>
        ) : (
          <>
            <span className={styles.stimulus} aria-hidden />
            <span className={styles.big}>{msg.big}</span>
          </>
        )}
        <span className={styles.small}>{msg.small}</span>
      </div>
      <p id="pvt-live" className="sr-only" aria-live="assertive">
        {state.practicing ? `Practice. ${msg.big}` : msg.big}
      </p>
      {state.falseStarts > 0 && (
        <p className={styles.meta}>
          False starts so far: <strong>{state.falseStarts}</strong>
        </p>
      )}
    </div>
  );
}
