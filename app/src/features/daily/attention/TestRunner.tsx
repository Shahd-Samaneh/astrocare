// Owner: Shahd. The large response area for the running test (quick, 5 trials).
// Click, tap or Space responds. Esc cancels. Space is handled on window only (not on the
// element) so a focused element never counts one key press twice.
// Waiting: a dim area with a small hollow circle and no number. Stimulus: a large circle in
// the accent colour lights up with "Now!". After a response the reaction time shows on the
// circle for ~1 s. With prefers-reduced-motion only the glow animation is off (CSS).
// The measured time always comes from the controller (useReactionTest). Display rules:
// runnerView.ts.
import { useEffect, useRef } from 'react';
import { Button } from '../../../shared/components';
import type { InputMethod } from '../api.attention';
import { runnerView } from './runnerView';
import { NO_RESPONSE_MS, TRIALS, isRunning, type ReactionState } from './useReactionTest';
import styles from './Attention.module.css';

export interface TestRunnerProps {
  state: ReactionState;
  onRespond: (method: InputMethod) => void;
  onCancel: () => void;
}

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
  const view = runnerView(state, NO_RESPONSE_MS);

  return (
    <div className={styles.runner}>
      <div className={styles.runnerHead}>
        <span className={styles.progress} aria-label={`Trial ${trialNo} of ${TRIALS}`}>
          Trial {trialNo}/{TRIALS}
        </span>
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
        <span className={styles.lightBox} aria-hidden>
          <span className={`${styles.light} ${styles[`light_${view.light}`]}`}>
            {view.onCircle && <span className={styles.onCircle}>{view.onCircle}</span>}
          </span>
        </span>
        {view.headline && <span className={styles.big}>{view.headline}</span>}
        <span className={styles.small}>{view.hint}</span>
      </div>
      <p id="pvt-live" className="sr-only" aria-live="assertive">
        {view.live}
      </p>
      {state.falseStarts > 0 && (
        <p className={styles.meta}>
          False starts so far: <strong>{state.falseStarts}</strong>
        </p>
      )}
    </div>
  );
}
