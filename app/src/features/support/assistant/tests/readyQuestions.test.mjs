// Ready-made question chips (item: "Why did I get <ruleId>?" first when a review/urgent alert is open).
// Run (no npm, no extra dependency; Node >= 22.6):
//   node --experimental-strip-types --test "app/src/features/support/assistant/tests/*.test.mjs"
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { chipAlert, readyQuestions, uiLang } from '../readyQuestions.ts';

const alert = (over) => ({
  id: 'al-1',
  ruleId: 'R-FAT-01',
  level: 'review',
  ts: '2026-11-14T06:10:00Z',
  title: 'Short sleep',
  whatChanged: '',
  dataUsed: [],
  missing: [],
  possibleFactors: [],
  nextSteps: [],
  status: 'new',
  sources: [],
  ...over,
});

test('no alerts: the generic list, first chip unchanged', () => {
  for (const alerts of [undefined, null, []]) {
    const chips = readyQuestions(alerts);
    assert.equal(chips[0], 'Why did I get the alert?');
    assert.equal(chips.length, 4);
  }
});

test('an open review alert: the first chip names its rule, the rest stay', () => {
  const chips = readyQuestions([alert()]);
  assert.equal(chips[0], 'Why did I get R-FAT-01?');
  assert.deepEqual(chips.slice(1), readyQuestions([]).slice(1));
});

test('info and closed alerts do not change the chip', () => {
  assert.equal(readyQuestions([alert({ level: 'info' })])[0], 'Why did I get the alert?');
  assert.equal(readyQuestions([alert({ status: 'closed', level: 'urgent' })])[0], 'Why did I get the alert?');
});

test('ack and recheck alerts are still open', () => {
  assert.equal(readyQuestions([alert({ status: 'ack' })])[0], 'Why did I get R-FAT-01?');
  assert.equal(readyQuestions([alert({ status: 'recheck' })])[0], 'Why did I get R-FAT-01?');
});

test('urgent beats review even when older; newest wins among equals', () => {
  const alerts = [
    alert({ id: 'a', ruleId: 'R-FAT-01', level: 'review', ts: '2026-11-14T09:00:00Z' }),
    alert({ id: 'b', ruleId: 'R-HR-02', level: 'urgent', ts: '2026-11-13T09:00:00Z' }),
    alert({ id: 'c', ruleId: 'R-HR-03', level: 'urgent', ts: '2026-11-13T10:00:00Z' }),
    alert({ id: 'd', ruleId: 'R-X-09', level: 'urgent', ts: '2026-11-15T10:00:00Z', status: 'closed' }),
  ];
  assert.equal(chipAlert(alerts).id, 'c');
  assert.equal(readyQuestions(alerts)[0], 'Why did I get R-HR-03?');
});

test('Arabic UI: Arabic chips, and the Arabic alert question with the rule id', () => {
  assert.equal(readyQuestions([], 'ar')[0], 'ليش طلعلي التنبيه؟');
  const chips = readyQuestions([alert()], 'ar');
  assert.equal(chips[0], 'ليش طلعلي تنبيه R-FAT-01؟');
  assert.equal(chips.length, 4);
});

test('uiLang reads <html lang>', () => {
  assert.equal(uiLang({ documentElement: { lang: 'ar' } }), 'ar');
  assert.equal(uiLang({ documentElement: { lang: 'ar-JO' } }), 'ar');
  assert.equal(uiLang({ documentElement: { lang: 'en' } }), 'en');
  assert.equal(uiLang({ documentElement: { lang: '' } }), 'en');
  assert.equal(uiLang(undefined), 'en');
});
