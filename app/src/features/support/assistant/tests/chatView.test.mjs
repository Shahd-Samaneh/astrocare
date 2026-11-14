// Chat display rules: source chip links, the health note, model status pill.
// Run: node --experimental-strip-types --test "app/src/features/support/assistant/tests/*.test.mjs"
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { chipLabel, EMPTY_STATE, HEALTH_NOTE, isArabic, isReference, modelStatus, showsHealthNote, sourceLink } from '../chatView.ts';

test('alert chip: rule id first, without the "Alert" / "التنبيه" word (EN and AR answers)', () => {
  const title = 'Heart rate, no recent data';
  assert.equal(chipLabel({ id: 'alert:al-1', title: `Alert R-DATA-01: ${title}` }), `R-DATA-01: ${title}`);
  assert.equal(chipLabel({ id: 'alert:al-1', title: `التنبيه R-DATA-01: ${title}` }), `R-DATA-01: ${title}`);
  assert.equal(chipLabel({ id: 'alert:al-1', title: `R-DATA-01: ${title}` }), `R-DATA-01: ${title}`);
});

test('other chips keep their title as is', () => {
  assert.equal(chipLabel({ id: 'user-data:sleep', title: 'Your data: sleep (7 days)' }), 'Your data: sleep (7 days)');
  assert.equal(chipLabel({ id: 'nasa-hrp-1', title: 'Alert fatigue in spaceflight' }), 'Alert fatigue in spaceflight');
});

test('source chips: alerts and three data areas link inside the app', () => {
  assert.equal(sourceLink({ id: 'alert:al-123' }), '/alerts/al-123');
  assert.equal(sourceLink({ id: 'user-data:sleep' }), '/daily');
  assert.equal(sourceLink({ id: 'user-data:attention' }), '/attention');
  assert.equal(sourceLink({ id: 'user-data:vitals' }), '/vitals');
});

test('source chips: references and other data areas are not links', () => {
  assert.equal(sourceLink({ id: 'nasa-sleep-01' }), null);
  assert.equal(sourceLink({ id: 'user-data:exercise' }), null);
  assert.equal(sourceLink({ id: 'user-data:checkins' }), null);
  assert.equal(sourceLink({ id: 'alert:' }), null);
});

test('alert id is encoded: a chip never builds another path or a host', () => {
  assert.equal(sourceLink({ id: 'alert://evil.example/x' }), '/alerts/%2F%2Fevil.example%2Fx');
  assert.equal(sourceLink({ id: 'alert:../reports' }), '/alerts/..%2Freports');
});

test('only references show their URL as a tooltip', () => {
  assert.equal(isReference({ id: 'nasa-sleep-01' }), true);
  assert.equal(isReference({ id: 'alert:al-1' }), false);
  assert.equal(isReference({ id: 'user-data:sleep' }), false);
});

const src = [{ id: 'alert:al-1', title: 'Alert R-FAT-01' }];

test('health note: alert, template and model answers with sources', () => {
  assert.equal(showsHealthNote({ refused: false, mode: 'alert', sources: src }), true);
  assert.equal(showsHealthNote({ refused: false, mode: 'fallback', sources: src }), true);
  assert.equal(showsHealthNote({ refused: false, mode: 'llm', sources: src }), true);
});

test('health note: not on refusals, not-found replies or data summaries', () => {
  assert.equal(showsHealthNote({ refused: true, mode: 'llm', sources: [] }), false);
  assert.equal(showsHealthNote({ refused: true, mode: 'llm', sources: src }), false);
  assert.equal(showsHealthNote({ refused: false, mode: 'llm', sources: [] }), false); // not found
  assert.equal(showsHealthNote({ refused: false, mode: 'fallback', sources: [] }), false); // no alert
  assert.equal(showsHealthNote({ refused: false, mode: 'data', sources: src }), false);
});

test('health note language follows the answer', () => {
  assert.equal(isArabic('Your sleep was short [1].'), false);
  assert.equal(isArabic('نومك كان قصير [1].'), true);
  assert.ok(HEALTH_NOTE.ar && HEALTH_NOTE.en.endsWith('not a diagnosis.'));
});

test('model status pill', () => {
  assert.equal(modelStatus({ reachable: undefined, warming: true, failed: false }), 'loading');
  assert.equal(modelStatus({ reachable: true, warming: true, failed: false }), 'loading');
  assert.equal(modelStatus({ reachable: true, warming: false, failed: false }), 'ready');
  assert.equal(modelStatus({ reachable: false, warming: false, failed: false }), 'off');
  assert.equal(modelStatus({ reachable: undefined, warming: false, failed: true }), 'off');
  assert.equal(modelStatus({ reachable: undefined, warming: false, failed: false }), 'loading');
});

test('empty state: same two lines in EN and AR, the second one sends medication / dose / diagnosis to the CMO', () => {
  assert.equal(EMPTY_STATE.en.length, 2);
  assert.equal(EMPTY_STATE.ar.length, 2);
  assert.match(EMPTY_STATE.en[1], /medication, dose or diagnosis/);
  assert.match(EMPTY_STATE.en[1], /CMO/);
  assert.match(EMPTY_STATE.ar[1], /CMO/);
  assert.match(EMPTY_STATE.en[0], /NASA\/CSA/);
  assert.match(EMPTY_STATE.ar[0], /NASA\/CSA/);
  assert.ok(EMPTY_STATE.ar.every((l) => isArabic(l)));
});
