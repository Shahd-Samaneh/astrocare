// Owner: Shahd. What the response area shows in each phase of the reaction test.
// Pure function (no React), so the display rules are unit-tested without a browser.
//   waiting     dim area, small hollow circle, "Wait for the light…", no number
//   stimulus    large lit circle, "Now!" (no live counter)
//   feedback    the circle stays lit with the reaction time on it for ~1 s
//               (or "Missed" after noResponseMs without a response)
//   falseStart  warning colour, "Too early.", then the trial repeats
// Type-only import, so this file runs under `node --experimental-strip-types` in tests.
import type { ReactionState } from './useReactionTest';

export type Light = 'off' | 'on' | 'frozen' | 'missed' | 'early';

export interface RunnerView {
  light: Light;
  /** Text on the circle: the frozen reaction time ("312 ms") after a response, else ''. */
  onCircle: string;
  headline: string;
  hint: string;
  /** Short text for the assertive live region (screen readers). */
  live: string;
}

export const WAIT_TEXT = 'Wait for the light…';
export const NOW_TEXT = 'Now!';
export const NOW_HINT = 'Click, tap or press Space';
export const EARLY_TEXT = 'Too early.';
export const EARLY_HINT = 'Wait for the light. This trial starts again.';
export const MISSED_TEXT = 'Missed';

/** `noResponseMs` is the controller's NO_RESPONSE_MS (passed in, see the import note). */
export function runnerView(state: ReactionState, noResponseMs: number): RunnerView {
  switch (state.phase) {
    case 'stimulus':
      return { light: 'on', onCircle: '', headline: NOW_TEXT, hint: NOW_HINT, live: NOW_TEXT };
    case 'feedback': {
      if (state.lastMissed) {
        return {
          light: 'missed',
          onCircle: '',
          headline: MISSED_TEXT,
          hint: `No response within ${noResponseMs / 1000} s, counted as a lapse.`,
          live: `${MISSED_TEXT}.`,
        };
      }
      const ms = Math.round(state.lastMs ?? 0);
      return {
        light: 'frozen',
        onCircle: `${ms} ms`,
        headline: '',
        hint: 'Get ready for the next one.',
        live: `${ms} milliseconds`,
      };
    }
    case 'falseStart':
      return {
        light: 'early',
        onCircle: '',
        headline: EARLY_TEXT,
        hint: EARLY_HINT,
        live: `${EARLY_TEXT} ${EARLY_HINT}`,
      };
    default:
      return {
        light: 'off',
        onCircle: '',
        headline: WAIT_TEXT,
        hint: 'Respond as soon as the circle lights up.',
        live: WAIT_TEXT,
      };
  }
}
