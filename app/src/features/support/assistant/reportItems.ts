// Report items the assistant sends to Noura's POST /api/reports/items (contracts §1).
// Pure functions (no fetch) so they can be unit tested.
import type { AssistantAnswer, NewReportItem } from './types';

/** "[1]", "[1, 2]" and the space before them. The numbers point at the source list, which a
 *  report item does not carry, so they are removed. */
export const stripCitations = (s: string) => s.replace(/[ \t]*\[\d+(?:,\s*\d+)*\]/g, '');

/** "Add to report" under any answer: the question as the title, the answer text without its
 *  sources list (and without the [n] markers that point at it). */
export function noteReportItem(question: string, answer: Pick<AssistantAnswer, 'answer'>): NewReportItem {
  return {
    kind: 'note',
    title: question.trim(),
    text: stripCitations(answer.answer).trim(),
    sourceFeature: 'assistant',
  };
}

/** "Add the question to the report for the CMO" under a medication refusal. */
export function cmoReportItem(question: string): NewReportItem {
  return {
    kind: 'cmo_question',
    title: 'Medication question for CMO',
    text: question,
    sourceFeature: 'assistant',
  };
}

/** The message shown when adding failed. 404/405: the reports endpoint is not there yet. */
export function reportErrorMessage(status: number, message: string, what: 'question' | 'answer'): string {
  return status === 404 || status === 405
    ? `The report service is not available yet, so the ${what} was not added. Please try again later.`
    : `The ${what} could not be added (${message}). Please try again.`;
}
