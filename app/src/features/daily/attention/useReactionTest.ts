// Owner: Shahd. State machine for the 5-trial reaction test (PVT-style).
//
//   waiting (random 2–8 s) → stimulus → response → feedback → next trial … → done
//   A response during "waiting" is a false start: it is counted and that trial repeats.
//   No response within NO_RESPONSE_MS records NO_RESPONSE_MS (a lapse) so the test can't hang.
// Timing uses performance.now(). The stimulus time is taken in the animation frame
// that paints the stimulus, so render time isn't counted against the user.
import { useEffect, useReducer, useRef, useState } from 'react';

export const TRIALS = 5;
export const MIN_DELAY_MS = 2000;
export const MAX_DELAY_MS = 8000;
export const NO_RESPONSE_MS = 5000;
const FEEDBACK_MS = 900;
const FALSE_START_MS = 1500;

export type Phase = 'idle' | 'waiting' | 'stimulus' | 'feedback' | 'falseStart' | 'done';

export interface ReactionState {
  phase: Phase;
  trialsMs: number[];
  falseStarts: number;
  lastMs?: number;
}

const INITIAL: ReactionState = { phase: 'idle', trialsMs: [], falseStarts: 0 };

type DoneHandler = (trialsMs: number[], falseStarts: number) => void;

function createController(render: () => void, onDone: { current: DoneHandler }) {
  let state: ReactionState = INITIAL;
  let timer: number | undefined;
  let stimulusAt = 0;

  const set = (patch: Partial<ReactionState>) => {
    state = { ...state, ...patch };
    render();
  };
  const clear = () => {
    if (timer !== undefined) window.clearTimeout(timer);
    timer = undefined;
  };

  const record = (ms: number) => {
    clear();
    const trialsMs = [...state.trialsMs, Math.round(ms)];
    if (trialsMs.length >= TRIALS) {
      set({ phase: 'done', trialsMs, lastMs: ms });
      onDone.current(trialsMs, state.falseStarts);
      return;
    }
    set({ phase: 'feedback', trialsMs, lastMs: ms });
    timer = window.setTimeout(wait, FEEDBACK_MS);
  };

  const showStimulus = () => {
    stimulusAt = performance.now();
    set({ phase: 'stimulus' });
    window.requestAnimationFrame(() => {
      if (state.phase === 'stimulus') stimulusAt = performance.now();
    });
    timer = window.setTimeout(() => record(NO_RESPONSE_MS), NO_RESPONSE_MS);
  };

  function wait() {
    clear();
    set({ phase: 'waiting' });
    const delay = MIN_DELAY_MS + Math.random() * (MAX_DELAY_MS - MIN_DELAY_MS);
    timer = window.setTimeout(showStimulus, delay);
  }

  return {
    get state() {
      return state;
    },
    start() {
      clear();
      state = INITIAL;
      wait();
    },
    respond() {
      if (state.phase === 'waiting') {
        clear();
        set({ phase: 'falseStart', falseStarts: state.falseStarts + 1 });
        timer = window.setTimeout(wait, FALSE_START_MS);
      } else if (state.phase === 'stimulus') {
        record(performance.now() - stimulusAt);
      }
    },
    cancel() {
      clear();
      set(INITIAL);
    },
    dispose: clear,
  };
}

export function useReactionTest(onDone: DoneHandler) {
  const [, render] = useReducer((x: number) => x + 1, 0);
  const doneRef = useRef<DoneHandler>(onDone);
  useEffect(() => {
    doneRef.current = onDone;
  }, [onDone]);
  const [ctrl] = useState(() => createController(render, doneRef));
  useEffect(() => () => ctrl.dispose(), [ctrl]);
  return ctrl;
}

export const isRunning = (p: Phase) =>
  p === 'waiting' || p === 'stimulus' || p === 'feedback' || p === 'falseStart';
