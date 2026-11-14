// Display rules for the chat (no React, no fetch) so they can be unit tested:
//   node --experimental-strip-types --test "app/src/features/support/assistant/tests/*.test.mjs"
import type { AssistantAnswer, AssistantSource } from './types';

/** In-app page for a source chip, or null when the chip is not a link. "alert:<id>" goes to the
 *  alert, three "Your data" areas go to their pages; references (NASA/CSA) and the other data
 *  areas are plain chips (a reference URL is only a tooltip: the app never opens a remote page). */
const DATA_PAGES: Record<string, string> = {
  'user-data:sleep': '/daily',
  'user-data:attention': '/attention',
  'user-data:vitals': '/vitals',
};

export function sourceLink(source: Pick<AssistantSource, 'id'>): string | null {
  if (source.id.startsWith('alert:')) {
    const id = source.id.slice('alert:'.length);
    return id ? `/alerts/${encodeURIComponent(id)}` : null;
  }
  return DATA_PAGES[source.id] ?? null;
}

/** A reference (not an alert, not "Your data"): shown with its URL as a tooltip. */
export const isReference = (source: Pick<AssistantSource, 'id'>) =>
  !source.id.startsWith('alert:') && !source.id.startsWith('user-data:');

/** The chip text. Alert sources come as "Alert R-DATA-01: <title>" or "التنبيه R-DATA-01: <title>":
 *  the chip drops that word and keeps "R-DATA-01: <title>", so an Arabic word never sits between
 *  the (English) rule id and the title and scrambles the mixed-direction line. */
const ALERT_PREFIX = /^\s*(?:Alert|التنبيه)\s+/i;

export function chipLabel(source: Pick<AssistantSource, 'id' | 'title'>): string {
  return source.id.startsWith('alert:') ? source.title.replace(ALERT_PREFIX, '') : source.title;
}

/** True when the text has Arabic letters (the answer is in Arabic). */
export const isArabic = (text: string) => /[؀-ۿ]/.test(text);

/** The "pattern, not a diagnosis" line: alert, alert-template and model answers that talk about
 *  the user's health. Not on refusals, and not on "not found" / "no alert" replies (no sources). */
export function showsHealthNote(answer: Pick<AssistantAnswer, 'refused' | 'mode' | 'sources'>): boolean {
  return !answer.refused && answer.mode !== 'data' && answer.sources.length > 0;
}

export const HEALTH_NOTE = {
  en: 'This is a pattern to review, not a diagnosis.',
  ar: 'هذا نمط للمراجعة، وليس تشخيصاً.',
} as const;

/** Empty chat (before the first message): what the assistant does and what it never does. */
export const EMPTY_STATE = {
  en: [
    'I can explain your alerts, summarise your last 7 days, and answer from NASA/CSA references on this device.',
    'I never give medication, dose or diagnosis advice. Those questions go to the CMO.',
  ],
  ar: [
    'أستطيع شرح تنبيهاتك، وتلخيص آخر 7 أيام، والإجابة من مراجع NASA/CSA المحفوظة على هذا الجهاز.',
    'لا أقدّم أبداً نصائح عن الأدوية أو الجرعات أو التشخيص. هذه الأسئلة تُحال إلى الضابط الطبي للطاقم (CMO).',
  ],
} as const;

export type ModelStatus = 'ready' | 'loading' | 'off';

/** The pill in the chat header. Off: the service or Ollama is not reachable (answers come from
 *  the user's data and templates). Loading: the warm-up is still running or info is not in yet. */
export function modelStatus(s: { reachable?: boolean; warming: boolean; failed: boolean }): ModelStatus {
  if (s.failed || s.reachable === false) return s.warming ? 'loading' : 'off';
  if (s.warming || s.reachable === undefined) return 'loading';
  return 'ready';
}

export const MODEL_STATUS_TEXT: Record<ModelStatus, string> = {
  ready: 'Local model ready',
  loading: 'Loading model…',
  off: 'Model off — answers from your data only',
};
