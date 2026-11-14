// Ready-made question chips. Pure functions (no React, no fetch) so they can be unit tested:
//   node --experimental-strip-types --test "app/src/features/support/assistant/tests/*.test.mjs"
// If there is an open review/urgent alert, the first chip names its rule ("Why did I get R-FAT-01?"),
// so the answer explains that exact alert (the backend picks the alert by rule id).
import type { Alert } from '../../../shared/types/contracts';

export type UiLang = 'en' | 'ar';

const BASE: Record<UiLang, string[]> = {
  en: [
    'Why did I get the alert?',
    'How can sleep loss affect my performance on the mission?',
    'What does my data from the last 7 days show?',
    'Can I take melatonin to sleep better?', // shows the medication refusal
  ],
  ar: [
    'ليش طلعلي التنبيه؟',
    'كيف ممكن قلة النوم تأثر على أدائي بالمهمة؟',
    'شو بتبيّن بياناتي آخر 7 أيام؟',
    'بقدر آخد ميلاتونين لأنام أحسن؟', // shows the medication refusal
  ],
};

const LEVEL_RANK: Record<string, number> = { urgent: 2, review: 1 };

/** The alert the first chip asks about: open (not closed), review or urgent; urgent first, then newest. */
export function chipAlert(alerts: readonly Alert[] | null | undefined): Alert | null {
  let best: Alert | null = null;
  for (const a of alerts ?? []) {
    if (a.status === 'closed' || !LEVEL_RANK[a.level] || !a.ruleId) continue;
    if (
      !best ||
      LEVEL_RANK[a.level] > LEVEL_RANK[best.level] ||
      (LEVEL_RANK[a.level] === LEVEL_RANK[best.level] && a.ts > best.ts)
    ) {
      best = a;
    }
  }
  return best;
}

export function alertQuestion(ruleId: string, lang: UiLang): string {
  return lang === 'ar' ? `ليش طلعلي تنبيه ${ruleId}؟` : `Why did I get ${ruleId}?`;
}

/** The chips to show, in order. Without a matching alert the generic list is used as is. */
export function readyQuestions(alerts: readonly Alert[] | null | undefined, lang: UiLang = 'en'): string[] {
  const base = BASE[lang];
  const alert = chipAlert(alerts);
  return alert ? [alertQuestion(alert.ruleId, lang), ...base.slice(1)] : [...base];
}

/** 'ar' when the page is in Arabic (<html lang="ar...">), otherwise 'en'. */
export function uiLang(doc: Pick<Document, 'documentElement'> | undefined = globalThis.document): UiLang {
  const lang = doc?.documentElement?.lang ?? '';
  return lang.toLowerCase().startsWith('ar') ? 'ar' : 'en';
}
