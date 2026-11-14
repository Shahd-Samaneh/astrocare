// API calls for Nadia's part of Daily health. Everything goes to the local API (relative /api paths).
//
// Mocks: while the sub-routers are not yet included by server/features/daily/router.py you can
// develop against shape-exact mocks (features/daily/mocks) by adding this line to app/.env.local:
//     VITE_DAILY_MOCKS=true
// The real API is the default.
import { useCallback, useEffect, useRef, useState } from 'react';
import { ApiError, api } from '../../shared/api/client';
import type { Alert, ExerciseLog, ExerciseReason, SleepSession } from '../../shared/types/contracts';
import {
  mockAddSleep, mockAlternatives, mockExercisePlan, mockFatigueAlert, mockLogExercise, mockRateSleep,
  mockSleepSummary, mockTodayPlan,
} from './mocks';
import type {
  AlternativesResult, ExerciseItem, ExerciseLogBody, ManualSleepBody, SleepSummary, TodayPlan,
} from './types.log';

const USE_MOCKS = import.meta.env.VITE_DAILY_MOCKS === 'true';

/** PATCH helper: the shared client only has get/post (proposal: add patch/put/del). */
async function patch<T>(path: string, body: unknown): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`/api${path}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, 'Local service unreachable');
  }
  const text = await res.text();
  const data: unknown = text ? JSON.parse(text) : undefined;
  if (!res.ok) {
    const detail = (data as { detail?: unknown } | undefined)?.detail;
    throw new ApiError(res.status, typeof detail === 'string' ? detail : `HTTP ${res.status}`, data);
  }
  return data as T;
}

export const logApi = {
  sleepSummary: (days = 7): Promise<SleepSummary> =>
    USE_MOCKS ? mockSleepSummary() : api.get<SleepSummary>(`/sleep/summary?days=${days}`),
  rateSleep: (id: string, selfQuality: number): Promise<SleepSession> =>
    USE_MOCKS ? mockRateSleep(id, selfQuality) : patch<SleepSession>(`/sleep/${encodeURIComponent(id)}/rating`, { selfQuality }),
  addSleep: (body: ManualSleepBody): Promise<SleepSession> =>
    USE_MOCKS ? mockAddSleep(body) : api.post<SleepSession>('/sleep', body),
  exercisePlan: (day?: number): Promise<ExerciseItem[]> =>
    USE_MOCKS ? mockExercisePlan(day) : api.get<ExerciseItem[]>(day === undefined ? '/exercise/plan' : `/exercise/plan?day=${day}`),
  alternatives: (planId: string, reason: ExerciseReason): Promise<AlternativesResult> =>
    USE_MOCKS
      ? mockAlternatives(planId, reason)
      : api.get<AlternativesResult>(`/exercise/alternatives?planId=${encodeURIComponent(planId)}&reason=${reason}`),
  logExercise: (body: ExerciseLogBody): Promise<ExerciseLog> =>
    USE_MOCKS ? mockLogExercise(body) : api.post<ExerciseLog>('/exercise/log', body),
  todayPlan: (): Promise<TodayPlan> => (USE_MOCKS ? mockTodayPlan() : api.get<TodayPlan>('/today/plan')),
  alerts: (): Promise<Alert[]> => (USE_MOCKS ? mockFatigueAlert() : api.get<Alert[]>('/alerts')),
};

export interface QueryState<T> {
  data: T | undefined;
  error: ApiError | undefined;
  loading: boolean;
  reload: () => void;
}

/** Loads `fetcher()` on mount and whenever `key` changes or `reload()` is called. */
export function useDailyQuery<T>(key: string, fetcher: () => Promise<T>): QueryState<T> {
  const [data, setData] = useState<T>();
  const [error, setError] = useState<ApiError>();
  const [loading, setLoading] = useState(true);
  const [tick, setTick] = useState(0);
  const latest = useRef(fetcher);
  latest.current = fetcher;
  const reload = useCallback(() => setTick((t) => t + 1), []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    latest
      .current()
      .then((d) => {
        if (cancelled) return;
        setData(d);
        setError(undefined);
      })
      .catch((e: unknown) => {
        if (!cancelled) setError(e instanceof ApiError ? e : new ApiError(0, String(e)));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [key, tick]);

  return { data, error, loading, reload };
}

/** Shown to the person when an action fails. */
export function errorText(e: unknown): string {
  return e instanceof Error ? e.message : 'Something went wrong. Please try again.';
}
