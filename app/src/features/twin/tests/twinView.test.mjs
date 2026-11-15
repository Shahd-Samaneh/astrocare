// Digital twin display rules: summary line, status mapping, timeline labels, sensor numbering.
// Run: node --experimental-strip-types --test "app/src/features/twin/tests/*.test.mjs"
import assert from 'node:assert/strict';
import { test } from 'node:test';
import {
  ESTIMATE_LABEL, NO_DATA, STATUS_BADGE, STATUS_TOKEN, beatPeriod, bySeverity, formatValue, nextPlayDay,
  numberSensors, overallSummary, qualityLabel, viewingLabel,
} from '../twinView.ts';

const region = (id, status, extra = {}) => ({ id, status, headline: id, values: [], alerts: [], alertRefs: [], route: '/', routeLabel: 'X', sources: [], sourceTitles: [], estimate: false, pulseBpm: null, sensors: null, label: id, ...extra });
const sensor = (id, status, anchor) => ({ id, name: id, location: 'loc', status, lastSeen: '', anchor });

test('summary counts systems to review and disconnected sensors', () => {
  const regions = [
    region('brain', 'review'),
    region('heart', 'ok'),
    region('lungs', 'review'),
    region('temperature', 'nodata'),
    region('sensors', 'watch', { sensors: [sensor('a', 'connected', 'chest'), sensor('b', 'disconnected', 'upperArm')] }),
  ];
  assert.equal(overallSummary(regions), '2 systems to review, 1 system with no data, 1 sensor disconnected');
  assert.equal(overallSummary([region('heart', 'ok'), region('sensors', 'ok', { sensors: [] })]), 'All systems OK');
});

test('each status has a theme token and a shared Badge variant', () => {
  assert.deepEqual(STATUS_TOKEN, { ok: '--ok', watch: '--accent', review: '--warn', urgent: '--danger', nodata: '--text-faint' });
  assert.equal(STATUS_BADGE.nodata, 'missing'); // dashed chip
});

test('most severe first, stable order within a status', () => {
  const sorted = bySeverity([region('a', 'ok'), region('b', 'review'), region('c', 'urgent'), region('d', 'review')]);
  assert.deepEqual(sorted.map((r) => r.id), ['c', 'b', 'd', 'a']);
});

test('missing values read "No data", never a number', () => {
  assert.equal(formatValue({ label: 'x', value: null, unit: 'bpm' }), NO_DATA);
  assert.equal(formatValue({ label: 'x', value: 0, unit: 'mSv' }), '0 mSv');
  assert.equal(formatValue({ label: 'x', value: 'connected', unit: null }), 'connected');
  assert.equal(qualityLabel('estimate'), ESTIMATE_LABEL);
  assert.equal(qualityLabel('stale'), 'Stale');
  assert.equal(qualityLabel('good'), null);
});

test('no pulse without a heart rate', () => {
  assert.equal(beatPeriod(null), null);
  assert.equal(beatPeriod(0), null);
  assert.equal(beatPeriod(60), 1);
});

test('timeline label and play steps', () => {
  assert.equal(viewingLabel(null, 142), 'Today (live)');
  assert.equal(viewingLabel(142, 142), 'Today (live)');
  assert.equal(viewingLabel(136, 142), 'Viewing day 136 (history)');
  assert.equal(nextPlayDay(null, 129, 142), 129);
  assert.equal(nextPlayDay(129, 129, 142), 130);
  assert.equal(nextPlayDay(141, 129, 142), null); // next is today: back to live, stop
});

test('only sensors worn on the body get a marker number', () => {
  const out = numberSensors([sensor('chest', 'connected', 'chest'), sensor('cuff', 'low_battery', null), sensor('wrist', 'connected', 'leftWrist')]);
  assert.deepEqual(out.map((o) => o.marker), [1, null, 2]);
});
