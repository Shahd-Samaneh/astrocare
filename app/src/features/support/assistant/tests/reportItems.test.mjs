// "Add to report" under every answer -> POST /api/reports/items { kind: 'note', ... }.
// Run: node --experimental-strip-types --test "app/src/features/support/assistant/tests/*.test.mjs"
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { cmoReportItem, noteReportItem, reportErrorMessage, stripCitations } from '../reportItems.ts';

test('note item: question as title, answer text, assistant as source', () => {
  const item = noteReportItem('  How does sleep loss affect me?  ', {
    answer: 'Sleep loss slows reaction time [1].\n\n- Your latest test was slower [2, 3].',
  });
  assert.deepEqual(item, {
    kind: 'note',
    title: 'How does sleep loss affect me?',
    text: 'Sleep loss slows reaction time.\n\n- Your latest test was slower.',
    sourceFeature: 'assistant',
  });
});

test('note item never carries the sources list', () => {
  const item = noteReportItem('Q', {
    answer: 'Text [1].',
    sources: [{ id: 'nasa-hrp-sleep-risk', title: 'Sleep risk (NASA HRP)' }],
  });
  assert.deepEqual(Object.keys(item).sort(), ['kind', 'sourceFeature', 'text', 'title']);
  assert.ok(!item.text.includes('NASA') && !item.text.includes('[1]'));
});

test('refusal answers can be added too (kind note)', () => {
  const item = noteReportItem('Is this a diagnosis?', { answer: "I can't give a diagnosis." });
  assert.equal(item.kind, 'note');
  assert.equal(item.text, "I can't give a diagnosis.");
});

test('CMO item is unchanged', () => {
  assert.deepEqual(cmoReportItem('Can I take melatonin?'), {
    kind: 'cmo_question',
    title: 'Medication question for CMO',
    text: 'Can I take melatonin?',
    sourceFeature: 'assistant',
  });
});

test('graceful message when the reports endpoint is not there', () => {
  for (const status of [404, 405]) {
    assert.match(reportErrorMessage(status, 'HTTP 404', 'answer'), /not available yet, so the answer was not added/);
  }
  assert.match(reportErrorMessage(0, 'Local service unreachable', 'answer'), /\(Local service unreachable\)/);
  assert.match(reportErrorMessage(404, 'x', 'question'), /the question was not added/);
});

test('stripCitations keeps everything else', () => {
  assert.equal(stripCitations('A [1]. B [1, 2]; C[3] **bold** [x]'), 'A. B; C **bold** [x]');
});
