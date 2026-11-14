// Owner: Shahd. State machine for the reaction test (PVT-style), two modes:
//   quick     5 trials, random 2–8 s waits (≈ 1 min). A false start repeats that trial.
//   extended  random 2–10 s waits until 3 minutes have passed (experimental, not validated).
//
//   [practice trial, not counted] → waiting → stimulus → response → feedback → … → done
//   A response during "waiting" is a false start: it is counted (not during practice).
//   No response within NO_RESPONSE_MS records NO_RESPONSE_MS (a lapse) so the test can't hang.
// Timing uses performance.now(). The stimulus time is taken in the animation frame
// that paints the stimulus, so render time isn't counted against the user. Each response
// also records its offset from the start of the real test (for the time-on-task chart).
import { useEffect, useReducer, useRef, useState } from 'react';
import type { InputMethod, TestMode } from '../api.attention';

export const TRIALS = 5;
export const MIN_DELAY_MS = 2000;
export const MAX_DELAY_MS = 8000;
export const EXTENDED_MAX_DELAY_MS = 10000;
export const EXTENDED_DURATION_MS = 3 * 60 * 1000;
export const NO_RESPONSE_MS = 5000;
const FEEDBACK_MS = 1000; // the frozen reaction time stays on screen ~1 s
const FALSE_START_MS = 1500;

export type Phase = 'idle' | 'waiting' | 'stimulus' | 'feedback' | 'falseStart' | 'done';

export interface ReactionState {
  phase: Phase;
  mode: TestMode;
  trialsMs: number[];
  /** Response time since the real test started, one per trial (ms). */
  offsetsMs: number[];
  falseStarts: number;
  lastMs?: number;
  /** True while the practice trial runs (its result is never recorded). */
  practicing: boolean;
  /** The feedback being shown is for the practice trial. */
  lastWasPractice?: boolean;
  /** performance.now() when the real (non-practice) test started. */
  startedAt?: number;
  /** Input method of the first real response (click, tap or key). */
  inputMethod?: InputMethod;
}

export interface StartOptions {
  practice: boolean;
  mode?: TestMode;
}

export interface RawResult {
  mode: TestMode;
  inputMethod?: InputMethod;
  trialsMs: number[];
  offsetsMs: number[];
  falseStarts: number;
}

const INITIAL: ReactionState = {
  phase: 'idle',
  mode: 'quick',
  trialsMs: [],
  offsetsMs: [],
  falseStarts: 0,
  practicing: false,
};

type DoneHandler = (result: RawResult) => void;

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

  const finish = () => {
    clear();
    set({ phase: 'done' });
    onDone.current({
      mode: state.mode,
      inputMethod: state.inputMethod,
      trialsMs: state.trialsMs,
      offsetsMs: state.offsetsMs,
      falseStarts: state.falseStarts,
    });
  };

  const record = (ms: number) => {
    clear();
    if (state.practicing) {
      set({ phase: 'feedback', lastMs: ms, practicing: false, lastWasPractice: true });
      timer = window.setTimeout(wait, FEEDBACK_MS);
      return;
    }
    const offset = Math.round(performance.now() - (state.startedAt ?? performance.now()));
    const trialsMs = [...state.trialsMs, Math.round(ms)];
    const offsetsMs = [...state.offsetsMs, offset];
    if (state.mode === 'quick' && trialsMs.length >= TRIALS) {
      state = { ...state, trialsMs, offsetsMs, lastMs: ms, lastWasPractice: false };
      finish();
      return;
    }
    set({ phase: 'feedback', trialsMs, offsetsMs, lastMs: ms, lastWasPractice: false });
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
    const now = performance.now();
    if (!state.practicing && state.startedAt === undefined) state = { ...state, startedAt: now };
    const extended = state.mode === 'extended' && !state.practicing;
    if (extended && now - (state.startedAt as number) >= EXTENDED_DURATION_MS) {
      finish();
      return;
    }
    set({ phase: 'waiting' });
    const maxDelay = state.mode === 'extended' ? EXTENDED_MAX_DELAY_MS : MAX_DELAY_MS;
    const delay = MIN_DELAY_MS + Math.random() * (maxDelay - MIN_DELAY_MS);
    if (extended) {
      const left = (state.startedAt as number) + EXTENDED_DURATION_MS - now;
      if (delay >= left) {
        timer = window.setTimeout(finish, Math.max(0, left)); // time is up during this wait
        return;
      }
    }
    timer = window.setTimeout(showStimulus, delay);
  }

  return {
    get state() {
      return state;
    },
    start(opts: StartOptions = { practice: false }) {
      clear();
      state = { ...INITIAL, mode: opts.mode ?? 'quick', practicing: opts.practice };
      wait();
    },
    respond(method?: InputMethod) {
      const counts = state.phase === 'waiting' || state.phase === 'stimulus';
      if (counts && !state.practicing && !state.inputMethod && method) {
        state = { ...state, inputMethod: method };
      }
      if (state.phase === 'waiting') {
        clear();
        set({
          phase: 'falseStart',
          falseStarts: state.practicing ? state.falseStarts : state.falseStarts + 1,
        });
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

// ---- practice preference (per device, localStorage; always wrapped in try/catch) ----
const PRACTICE_KEY = 'astrocare.daily.attention.practice';
const FIRST_DONE_KEY = 'astrocare.daily.attention.firstTestDone';

/** Stored choice if any; otherwise on until the first test on this device is saved. */
export function loadPracticeDefault(): boolean {
  try {
    const v = window.localStorage.getItem(PRACTICE_KEY);
    if (v === '1') return true;
    if (v === '0') return false;
    return window.localStorage.getItem(FIRST_DONE_KEY) !== '1';
  } catch {
    return true;
  }
}

export function savePracticeChoice(on: boolean): void {
  try {
    window.localStorage.setItem(PRACTICE_KEY, on ? '1' : '0');
  } catch {
    /* storage unavailable: the choice just isn't remembered */
  }
}

export function markFirstTestDone(): void {
  try {
    window.localStorage.setItem(FIRST_DONE_KEY, '1');
  } catch {
    /* ignore */
  }
}
