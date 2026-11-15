// Reaction-test runner: controller timing rules and what the response area shows.
// Run: node --experimental-strip-types --test "app/src/features/daily/attention/*.test.mjs"
import assert from 'node:assert/strict';
import { beforeEach, test } from 'node:test';

// ---- a fake clock for window timers, requestAnimationFrame and performance.now() ----------
let now = 0;
let timers = [];
let nextId = 1;
function schedule(fn, ms) {
  const id = nextId++;
  timers.push({ id, at: now + ms, fn });
  return id;
}
globalThis.window = {
  setTimeout: (fn, ms = 0) => schedule(fn, ms),
  clearTimeout: (id) => {
    timers = timers.filter((t) => t.id !== id);
  },
  requestAnimationFrame: (fn) => schedule(() => fn(now), 0),
};
Object.defineProperty(globalThis, 'performance', { value: { now: () => now }, configurable: true });

/** Advance the fake clock by `ms`, running every timer that falls due, in order. */
function tick(ms) {
  const end = now + ms;
  for (;;) {
    timers.sort((a, b) => a.at - b.at);
    const t = timers[0];
    if (!t || t.at > end) break;
    timers.shift();
    now = t.at;
    t.fn();
  }
  now = end;
}

const { createController, NO_RESPONSE_MS, MAX_DELAY_MS, FEEDBACK_MS, FALSE_START_MS, TRIALS } =
  await import('./useReactionTest.ts');
const { runnerView, WAIT_TEXT, NOW_TEXT, EARLY_TEXT, MISSED_TEXT } =
  await import('./runnerView.ts');

function setup() {
  const done = { current: () => {} };
  let result;
  done.current = (r) => {
    result = r;
  };
  const ctrl = createController(() => {}, done);
  return { ctrl, result: () => result };
}
/** Jump the clock exactly to the moment the stimulus shows (then run its paint frame). */
function untilStimulus(ctrl) {
  while (ctrl.state.phase !== 'stimulus') {
    timers.sort((x, y) => x.at - y.at);
    assert.ok(timers[0] && timers[0].at - now <= MAX_DELAY_MS, 'no stimulus scheduled');
    tick(timers[0].at - now);
  }
  tick(0);
}

beforeEach(() => {
  now = 0;
  timers = [];
});

test('the no-response timeout is 10 s', () => {
  assert.equal(NO_RESPONSE_MS, 10000);
});

test('no response within 10 s is recorded as a 10000 ms lapse, shown as "Missed", and the test moves on', () => {
  const { ctrl } = setup();
  ctrl.start();
  untilStimulus(ctrl);
  tick(NO_RESPONSE_MS - 1);
  assert.equal(ctrl.state.phase, 'stimulus'); // still waiting for a response
  tick(1);
  assert.equal(ctrl.state.phase, 'feedback');
  assert.deepEqual(ctrl.state.trialsMs, [10000]);
  assert.equal(ctrl.state.lastMissed, true);
  const v = runnerView(ctrl.state, NO_RESPONSE_MS);
  assert.equal(v.headline, MISSED_TEXT);
  assert.equal(v.onCircle, '');
  assert.match(v.hint, /10 s/);
  tick(FEEDBACK_MS);
  assert.equal(ctrl.state.phase, 'waiting'); // next trial
});

test('a test where nobody responds still finishes after 5 lapses (it can never hang)', () => {
  const { ctrl, result } = setup();
  ctrl.start();
  tick(TRIALS * (MAX_DELAY_MS + NO_RESPONSE_MS + FEEDBACK_MS) + 1000);
  assert.equal(ctrl.state.phase, 'done');
  assert.deepEqual(result().trialsMs, Array(TRIALS).fill(10000));
});

test('a full quick test: 5 responses, then the same payload shape as before (mode quick)', () => {
  const { ctrl, result } = setup();
  ctrl.start();
  for (let i = 0; i < TRIALS; i++) {
    untilStimulus(ctrl);
    tick(200 + i * 10);
    ctrl.respond('keyboard');
    if (i < TRIALS - 1) tick(FEEDBACK_MS);
  }
  assert.equal(ctrl.state.phase, 'done');
  const r = result();
  assert.equal(r.mode, 'quick');
  assert.deepEqual(r.trialsMs, [200, 210, 220, 230, 240]);
  assert.equal(r.offsetsMs.length, TRIALS);
  assert.equal(r.inputMethod, 'keyboard');
  assert.equal(r.falseStarts, 0);
  assert.equal('sleepinessKss' in r, false);
});

test('after a response the reaction time shows on the circle for about 1 s, then the next wait starts', () => {
  const { ctrl } = setup();
  ctrl.start();
  untilStimulus(ctrl);
  tick(250);
  ctrl.respond('keyboard');
  assert.equal(ctrl.state.phase, 'feedback');
  assert.equal(ctrl.state.lastMissed, false);
  const v = runnerView(ctrl.state, NO_RESPONSE_MS);
  assert.equal(v.light, 'frozen');
  assert.equal(v.onCircle, '250 ms');
  tick(FEEDBACK_MS - 1);
  assert.equal(ctrl.state.phase, 'feedback');
  tick(1);
  assert.equal(ctrl.state.phase, 'waiting');
});

test('waiting shows no number, a hollow circle and "Wait for the light…"', () => {
  const { ctrl } = setup();
  ctrl.start();
  assert.equal(ctrl.state.phase, 'waiting');
  const v = runnerView(ctrl.state, NO_RESPONSE_MS);
  assert.equal(v.onCircle, '');
  assert.equal(v.light, 'off');
  assert.equal(v.headline, WAIT_TEXT);
  assert.doesNotMatch(`${v.onCircle} ${v.headline} ${v.hint}`, /\d/);
});

test('waiting after a previous response still shows no number', () => {
  const { ctrl } = setup();
  ctrl.start();
  untilStimulus(ctrl);
  tick(300);
  ctrl.respond('mouse');
  tick(FEEDBACK_MS);
  assert.equal(ctrl.state.phase, 'waiting');
  assert.equal(runnerView(ctrl.state, NO_RESPONSE_MS).onCircle, ''); // lastMs is kept, but not shown
});

test('stimulus: lit circle and "Now!", with no number (no live counter)', () => {
  const { ctrl } = setup();
  ctrl.start();
  untilStimulus(ctrl);
  tick(120);
  const v = runnerView(ctrl.state, NO_RESPONSE_MS);
  assert.equal(v.light, 'on');
  assert.equal(v.headline, NOW_TEXT);
  assert.equal(v.hint, 'Click, tap or press Space');
  assert.equal(v.onCircle, '');
  assert.doesNotMatch(`${v.onCircle} ${v.headline} ${v.hint}`, /\d/);
});

test('false start: "Too early.", counted, then the trial repeats', () => {
  const { ctrl } = setup();
  ctrl.start();
  ctrl.respond('keyboard');
  assert.equal(ctrl.state.phase, 'falseStart');
  assert.equal(ctrl.state.falseStarts, 1);
  const v = runnerView(ctrl.state, NO_RESPONSE_MS);
  assert.equal(v.headline, EARLY_TEXT);
  assert.equal(v.light, 'early');
  assert.equal(v.onCircle, '');
  tick(FALSE_START_MS);
  assert.equal(ctrl.state.phase, 'waiting');
  assert.deepEqual(ctrl.state.trialsMs, []); // nothing recorded: the same trial runs again
  untilStimulus(ctrl);
  tick(260);
  ctrl.respond('keyboard');
  assert.deepEqual(ctrl.state.trialsMs, [260]);
  assert.equal(ctrl.state.falseStarts, 1);
});

test('cancel stops the test without a result', () => {
  const { ctrl, result } = setup();
  ctrl.start();
  untilStimulus(ctrl);
  ctrl.cancel();
  assert.equal(ctrl.state.phase, 'idle');
  tick(NO_RESPONSE_MS * 2);
  assert.equal(ctrl.state.phase, 'idle');
  assert.equal(result(), undefined);
});
