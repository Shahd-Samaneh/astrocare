// Owner: Shahd. Unit tests for the crew feed helpers (no browser):
//   node --experimental-strip-types --test "app/src/features/crew/*.test.mjs"
import assert from 'node:assert/strict';
import { test } from 'node:test';
import {
  activeCheck,
  localTimes,
  navState,
  pollMs,
  secondsLeft,
  timeText,
  unacknowledged,
} from './crewState.ts';

const em = (over = {}) => ({
  id: 'em-1',
  status: 'watch',
  respondedTs: null,
  acknowledged: false,
  deadlineTs: '2026-11-15T10:00:30Z',
  ...over,
});
const feed = (open) => ({
  serverTs: '2026-11-15T10:00:00Z',
  demo: true,
  responseSeconds: 30,
  open,
  history: [],
});

test('countdown follows the server clock, then the device clock since the fetch', () => {
  const fetchedAt = 1_000_000;
  assert.equal(
    secondsLeft('2026-11-15T10:00:30Z', '2026-11-15T10:00:00Z', fetchedAt, fetchedAt),
    30,
  );
  assert.equal(
    secondsLeft('2026-11-15T10:00:30Z', '2026-11-15T10:00:00Z', fetchedAt, fetchedAt + 12_300),
    18,
  );
  assert.equal(
    secondsLeft('2026-11-15T10:00:30Z', '2026-11-15T10:00:00Z', fetchedAt, fetchedAt + 45_000),
    0,
  );
});

test('the check shows only for an open watch without a response', () => {
  assert.equal(activeCheck(feed([em()]))?.id, 'em-1');
  assert.equal(activeCheck(feed([em({ respondedTs: '2026-11-15T10:00:05Z' })])), undefined);
  assert.equal(activeCheck(feed([em({ status: 'emergency' })])), undefined);
  assert.equal(activeCheck(undefined), undefined);
});

test('banner and red count only for escalated, unacknowledged emergencies', () => {
  const data = feed([
    em({ id: 'a', status: 'emergency' }),
    em({ id: 'b', status: 'emergency', acknowledged: true }),
    em({ id: 'c' }),
  ]);
  assert.deepEqual(
    unacknowledged(data).map((e) => e.id),
    ['a'],
  );
  assert.deepEqual(navState(data), { watch: true, emergencies: 1 });
  assert.deepEqual(navState(feed([])), { watch: false, emergencies: 0 });
});

test('polls every second while a watch counts down, else every 3 s', () => {
  assert.equal(pollMs(feed([em()])), 1000);
  assert.equal(pollMs(feed([em({ status: 'emergency' })])), 3000);
  assert.equal(pollMs(undefined), 3000);
});

test('times in server texts are shown in local time as HH:MM:SS', () => {
  const iso = '2026-11-15T04:18:40Z';
  const out = localTimes(`Wrist sensor showed movement until ${iso}, then no movement for 40 s.`);
  assert.equal(
    out,
    `Wrist sensor showed movement until ${timeText(iso)}, then no movement for 40 s.`,
  );
  assert.match(timeText(iso), /^\d{2}:\d{2}:\d{2}$/);
  assert.doesNotMatch(out, /Z|UTC/);
  assert.equal(localTimes('No response within 30 s.'), 'No response within 30 s.');
});
