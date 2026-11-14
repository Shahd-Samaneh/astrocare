// Owner: Shahd. API calls and types for the attention check, check-in and NASA basis.
// Local API only (relative /api paths through the shared client). No remote URLs.
//
// The Daily contract extensions (context, relatedAlertId, nextSteps[].action) live here
// until Haya merges them into shared/types/contracts.ts (docs/proposals/daily-contracts.md).
import { api } from '../../shared/api/client';
import type { Alert, CheckIn, CognitiveTest, NextStep } from '../../shared/types/contracts';

export type TestContext = 'routine' | 'retest';

export interface DailyCognitiveTest extends CognitiveTest {
  context: TestContext;
  relatedAlertId?: string | null;
}

export interface AttentionBaseline {
  medianMs: number | null;
  n: number;
  rangeLowMs: number | null;
  rangeHighMs: number | null;
  testIds: string[];
}

export interface TestResult {
  test: DailyCognitiveTest;
  pctVsBaseline: number | null;
  withinRange: boolean | null;
  baseline: AttentionBaseline;
}

export interface NewTest {
  trialsMs: number[];
  falseStarts: number;
  context?: TestContext;
  relatedAlertId?: string;
}

export interface NasaSource {
  id: string;
  org: string;
  title: string;
  why: string;
  // `url` is also sent by the server, but the offline app never opens it.
}

export interface NextStepAction {
  label: string;
  route: string;
}

export interface DailyNextStep extends NextStep {
  action?: NextStepAction | null;
}

export interface DailyAlert extends Omit<Alert, 'nextSteps'> {
  nextSteps: DailyNextStep[];
}

/** Check-in as returned without includePrivate: no notePrivate key. */
export type PublicCheckIn = Omit<CheckIn, 'notePrivate'>;

export interface NewCheckIn {
  mood?: number;
  stress?: number;
  notePrivate?: string;
  skipped: boolean;
}

export interface DailySummary {
  days: number;
  sleep: {
    lastNight?: { hours: number; missionDay?: number; selfQuality?: number | null } | null;
    personalAvgHours?: number | null;
  };
  attention: {
    baseline: AttentionBaseline;
    latest: DailyCognitiveTest | null;
    latestPctVsBaseline: number | null;
    latestWithinRange: boolean | null;
  };
  checkins: {
    todayStatus: 'todo' | 'done' | 'skipped';
    latest: PublicCheckIn | null;
  };
  activeDailyAlerts: DailyAlert[];
}

export const paths = {
  tests: (n = 10) => `/tests?n=${n}`,
  baseline: '/tests/baseline',
  summary: (days = 7) => `/daily/summary?days=${days}`,
  sources: '/daily/sources',
  alert: (id: string) => `/alerts/${encodeURIComponent(id)}`,
};

export const postTest = (body: NewTest) => api.post<TestResult>('/tests', body);
export const postCheckIn = (body: NewCheckIn) => api.post<CheckIn>('/checkins', body);
