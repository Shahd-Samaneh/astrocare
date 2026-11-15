// Owner: Shahd. State machine for the reaction test (PVT-style, quick: 5 trials).
//
//   waiting → stimulus → feedback (~1 s) → waiting … → done after TRIALS responses
//   A response during "waiting" is a false start: it is counted, "Too early." is shown,
//   and that trial's wait starts again (the trial repeats).
//   No response within NO_RESPONSE_MS (10 s) records NO_RESPONSE_MS as a lapse and shows
//   "Missed", so the test can never hang.
// Timing uses performance.now(). The stimulus time is taken in the animation frame
// that paints the stimulus, so render time isn't counted against the user. Each response
// also records its offset from the start of the test (sent to the server as before).
import { useEffect, useReducer, useRef, useState } from 'react';
import type { InputMethod } from '../api.attention';

export const TRIALS = 5;
export const MIN_DELAY_MS = 2000;
export const MAX_DELAY_MS = 8000;
export const NO_RESPONSE_MS = 10000;
export const FEEDBACK_MS = 1000; // the reaction time stays on the circle ~1 s
export const FALSE_START_MS = 1500; // "Too early." is shown, then that trial's wait restarts

export type Phase = 'idle' | 'waiting' | 'stimulus' | 'feedback' | 'falseStart' | 'done';

export interface ReactionState {
  phase: Phase;
  trialsMs: number[];
  /** Response time since the test started, one per trial (ms). */
  offsetsMs: number[];
  falseStarts: number;
  lastMs?: number;
  /** The last trial got no response within NO_RESPONSE_MS (recorded as a lapse). */
  lastMissed?: boolean;
  /** performance.now() when the test started. */
  startedAt?: number;
  /** Input method of the first response (click, tap or key). */
  inputMethod?: InputMethod;
}

export interface RawResult {
  mode: 'quick';
  inputMethod?: InputMethod;
  trialsMs: number[];
  offsetsMs: number[];
  falseStarts: number;
}

const INITIAL: ReactionState = {
  phase: 'idle',
  trialsMs: [],
  offsetsMs: [],
  falseStarts: 0,
};

type DoneHandler = (result: RawResult) => void;

/** Exported for tests; components use useReactionTest. */
export function createController(render: () => void, onDone: { current: DoneHandler }) {
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

  const finish = () => {
    clear();
    set({ phase: 'done' });
    onDone.current({
      mode: 'quick',
      inputMethod: state.inputMethod,
      trialsMs: state.trialsMs,
      offsetsMs: state.offsetsMs,
      falseStarts: state.falseStarts,
    });
  };

  const record = (ms: number, missed = false) => {
    clear();
    const offset = Math.round(performance.now() - (state.startedAt ?? performance.now()));
    const trialsMs = [...state.trialsMs, Math.round(ms)];
    const offsetsMs = [...state.offsetsMs, offset];
    if (trialsMs.length >= TRIALS) {
      state = { ...state, trialsMs, offsetsMs, lastMs: ms, lastMissed: missed };
      finish();
      return;
    }
    set({ phase: 'feedback', trialsMs, offsetsMs, lastMs: ms, lastMissed: missed });
    timer = window.setTimeout(wait, FEEDBACK_MS);
  };

  const showStimulus = () => {
    stimulusAt = performance.now();
    set({ phase: 'stimulus' });
    window.requestAnimationFrame(() => {
      if (state.phase === 'stimulus') stimulusAt = performance.now();
    });
    timer = window.setTimeout(() => record(NO_RESPONSE_MS, true), NO_RESPONSE_MS);
  };

  function wait() {
    clear();
    if (state.startedAt === undefined) state = { ...state, startedAt: performance.now() };
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
      state = { ...INITIAL };
      wait();
    },
    respond(method?: InputMethod) {
      const counts = state.phase === 'waiting' || state.phase === 'stimulus';
      if (counts && !state.inputMethod && method) state = { ...state, inputMethod: method };
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
