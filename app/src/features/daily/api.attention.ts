// Owner: Shahd. API calls and types for the attention check, check-in and NASA basis.
// Local API only (relative /api paths through the shared client). No remote URLs.
//
// The Daily contract extensions (context, relatedAlertId, nextSteps[].action) live here
// until Haya merges them into shared/types/contracts.ts (docs/proposals/daily-contracts.md).
import { api } from '../../shared/api/client';
import type { Alert, CheckIn, CognitiveTest, NextStep, Source } from '../../shared/types/contracts';

export type TestContext = 'routine' | 'retest';
export type TestMode = 'quick' | 'extended';
export type InputMethod = 'mouse' | 'touch' | 'keyboard';

export interface DailyCognitiveTest extends CognitiveTest {
  context: TestContext;
  relatedAlertId?: string | null;
  /** Mission day of the test (derived on the server). */
  missionDay?: number | null;
  /** 'quick' (5 trials) or 'extended' (3 min). Absent on older servers = quick. */
  mode?: TestMode;
  /** Karolinska Sleepiness Scale 1–9, null if skipped. */
  sleepinessKss?: number | null;
  inputMethod?: InputMethod | null;
  /** Response time since the test started, per trial (ms). */
  trialOffsetsMs?: number[] | null;
  measures?: PvtMeasures | null;
}

export interface AttentionBaseline {
  medianMs: number | null;
  n: number;
  rangeLowMs: number | null;
  rangeHighMs: number | null;
  testIds: string[];
  mode?: TestMode;
  /** Fewer than `needed` tests of this mode: "Building your baseline (n/3)". */
  building?: boolean;
  needed?: number;
  usualInputMethod?: InputMethod | null;
}

/** From the sleep log: the last sleep session that ended before the test. */
export interface SleepContext {
  sleepId: string | null;
  sleptHours: number | null;
  hoursAwake: number | null;
  source: Source | null;
}

export interface TestResult {
  test: DailyCognitiveTest;
  pctVsBaseline: number | null;
  withinRange: boolean | null;
  baseline: AttentionBaseline;
  sleepContext: SleepContext;
}

export interface NewTest {
  trialsMs: number[];
  falseStarts: number;
  context?: TestContext;
  relatedAlertId?: string;
  sleepinessKss?: number | null;
  mode?: TestMode;
  trialOffsetsMs?: number[];
}

export interface PvtMeasures {
  meanMs: number;
  fastest10MeanMs: number;
  slowest10MeanMs: number;
  /** Mean of 1/RT, in 1/s. */
  responseSpeed: number;
  lapses: number;
  falseStarts: number;
  n: number;
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

/** One night from sleep_summary (Nadia) or our fallback. Extra fields may be absent. */
export interface SleepNight {
  missionDay: number;
  hours: number;
  date?: string;
  awakenings?: number;
  selfQuality?: number | null;
  start?: string;
  end?: string;
  source?: string;
}

export interface ThresholdInfo {
  value: number | null;
  unit: string;
  source: string;
  note: string;
}
export type DailyThresholds = Record<string, ThresholdInfo>;

export interface DailySummary {
  days: number;
  sleep: {
    nights?: SleepNight[];
    lastNight?: SleepNight | null;
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
  baselineFor: (mode: TestMode) => `/tests/baseline?mode=${mode}`,
  summary: (days = 7) => `/daily/summary?days=${days}`,
  sources: '/daily/sources',
  thresholds: '/daily/thresholds',
  alert: (id: string) => `/alerts/${encodeURIComponent(id)}`,
};

export const postTest = (body: NewTest) => api.post<TestResult>('/tests', body);
export const postCheckIn = (body: NewCheckIn) => api.post<CheckIn>('/checkins', body);
