// Owner: Shahd. The large response area for the running test.
// Click, tap or Space responds. Esc cancels. Space is handled on window only (not on the
// element) so a focused element never counts one key press twice.
import { useEffect, useRef } from 'react';
import { Button } from '../../../shared/components';
import { TRIALS, isRunning, type ReactionState } from './useReactionTest';
import styles from './Attention.module.css';

export interface TestRunnerProps {
  state: ReactionState;
  onRespond: () => void;
  onCancel: () => void;
}

const MESSAGE: Record<string, { big: string; small: string }> = {
  waiting: { big: 'Wait…', small: 'Respond as soon as the circle lights up.' },
  stimulus: { big: 'Now!', small: 'Click, tap or press Space.' },
  falseStart: { big: 'Too soon', small: 'That was before the signal. This trial will repeat.' },
};

export function TestRunner({ state, onRespond, onCancel }: TestRunnerProps) {
  const areaRef = useRef<HTMLDivElement>(null);
  const running = isRunning(state.phase);

  useEffect(() => {
    areaRef.current?.focus();
  }, []);

  useEffect(() => {
    if (!running) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.code === 'Space' || e.key === ' ') {
        e.preventDefault();
        if (!e.repeat) onRespond();
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
      ? { big: `${Math.round(state.lastMs ?? 0)} ms`, small: 'Get ready for the next one.' }
      : (MESSAGE[state.phase] ?? MESSAGE.waiting);

  return (
    <div className={styles.runner}>
      <div className={styles.runnerHead}>
        <span className={styles.progress} aria-label={`Trial ${trialNo} of ${TRIALS}`}>
          Trial {trialNo}/{TRIALS}
        </span>
        <ol className={styles.dots} aria-hidden>
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
          onRespond();
        }}
      >
        <span className={styles.stimulus} aria-hidden />
        <span className={styles.big}>{msg.big}</span>
        <span className={styles.small}>{msg.small}</span>
      </div>
      <p id="pvt-live" className="sr-only" aria-live="assertive">
        {msg.big}
      </p>
      {state.falseStarts > 0 && (
        <p className={styles.meta}>
          False starts so far: <strong>{state.falseStarts}</strong>
        </p>
      )}
    </div>
  );
}
