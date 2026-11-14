// Mock data for Nadia's Daily pages, shaped exactly like the API contract.
// Used only when VITE_DAILY_MOCKS=true (see api.log.ts); the real API is the default.
// State is kept in memory so the whole flow (rate, log, choose an alternative) can be tried offline.
import type { Alert, ExerciseLog, SleepSession } from '../../../shared/types/contracts';
import type {
  AlternativesResult,
  EquipmentRef,
  ExerciseAlternativeOption,
  ExerciseItem,
  ExerciseLogBody,
  Intensity,
  ManualSleepBody,
  SleepNight,
  SleepSummary,
  TodayPlan,
} from '../types.log';

const delay = <T,>(value: T, ms = 150): Promise<T> => new Promise((resolve) => setTimeout(() => resolve(value), ms));
const rank: Record<Intensity, number> = { light: 0, moderate: 1, hard: 2 };
const TODAY = 142;
const SHORT_BELOW = 6;

// ---- sleep ----------------------------------------------------------------------
const hoursByDay: Record<number, number> = { 136: 7.4, 137: 7.2, 138: 7.5, 139: 7.3, 140: 7.1, 141: 5.0, 142: 4.9 };
const nights: SleepNight[] = Object.entries(hoursByDay).map(([d, h], i) => ({
  id: `sleep-${d}`,
  date: `2026-11-${String(5 + i).padStart(2, '0')}`,
  missionDay: Number(d),
  hours: h,
  awakenings: h < SHORT_BELOW ? 4 : 1,
  selfQuality: h < SHORT_BELOW ? 2 : 4,
  short: h < SHORT_BELOW,
}));

export const mockSleepSummary = (): Promise<SleepSummary> => {
  const first = nights.slice(0, 3);
  const avg = Math.round((first.reduce((s, n) => s + n.hours, 0) / first.length) * 100) / 100;
  return delay({
    nights: nights.map((n) => ({ ...n })),
    personalAvgHours: avg,
    shortThresholdHours: SHORT_BELOW,
    lastNight: { ...nights[nights.length - 1] },
  });
};

export const mockRateSleep = (id: string, selfQuality: number): Promise<SleepSession> => {
  const n = nights.find((x) => x.id === id);
  if (n) n.selfQuality = selfQuality;
  return delay({
    id, start: '', end: '', durationMin: Math.round((n?.hours ?? 0) * 60), awakenings: n?.awakenings ?? 0,
    selfQuality, source: 'simulated',
  });
};

export const mockAddSleep = (b: ManualSleepBody): Promise<SleepSession> => {
  const durationMin = Math.round((new Date(b.end).getTime() - new Date(b.start).getTime()) / 60000);
  const hours = Math.round((durationMin / 60) * 100) / 100;
  nights.push({
    id: `sleep-manual-${nights.length}`, date: b.end.slice(0, 10), missionDay: TODAY + 1, hours,
    awakenings: b.awakenings, selfQuality: b.selfQuality ?? null, short: hours < SHORT_BELOW,
  });
  return delay({
    id: `sleep-manual-${nights.length}`, start: b.start, end: b.end, durationMin, awakenings: b.awakenings,
    selfQuality: b.selfQuality ?? null, source: 'manual',
  });
};

// ---- exercise ---------------------------------------------------------------------
const eq = (id: string, name: string, status: EquipmentRef['status']): EquipmentRef => ({ id, name, status });
const ARED = eq('eq-ared', 'Resistive exercise device', 'available');
const CYCLE = eq('eq-cycle', 'Cycle ergometer', 'available');
const TREADMILL = eq('eq-treadmill', 'Treadmill with harness', 'available');
const BANDS = eq('eq-bands', 'Resistance bands', 'low');

interface MockAlt { id: string; type: string; durationMin: number; intensity: Intensity; equipment: EquipmentRef | null }
const alts: Record<string, MockAlt> = {
  'alt-bands-circuit': { id: 'alt-bands-circuit', type: 'Resistance bands circuit', durationMin: 40, intensity: 'moderate', equipment: BANDS },
  'alt-cevis-easy': { id: 'alt-cevis-easy', type: 'CEVIS easy spin', durationMin: 30, intensity: 'light', equipment: CYCLE },
  'alt-mobility': { id: 'alt-mobility', type: 'Mobility and stretching', durationMin: 20, intensity: 'light', equipment: null },
};

const logs: Record<string, ExerciseLog> = {};
const plan = (id: string, day: number, type: string, durationMin: number, intensity: Intensity, equipment: EquipmentRef | null, alternatives: string[]): ExerciseItem => ({
  id, day, type, durationMin, intensity, equipmentId: equipment?.id ?? null, equipment,
  equipmentStatus: equipment?.status ?? null, available: true, alternatives, log: null,
});
const items: ExerciseItem[] = [
  plan('ex-140', 140, 'ARED resistance session (full body)', 60, 'hard', ARED, Object.keys(alts)),
  plan('ex-141', 141, 'CEVIS interval ride', 45, 'hard', CYCLE, ['alt-mobility']),
  plan('ex-142', 142, 'ARED resistance session (full body)', 60, 'hard', ARED, Object.keys(alts)),
  plan('ex-143', 143, 'T2 treadmill intervals (with harness)', 40, 'hard', TREADMILL, ['alt-cevis-easy', 'alt-mobility']),
];
logs['ex-140'] = { id: 'exl-140', planId: 'ex-140', ts: '', status: 'done', reason: null, alternativeId: null };
logs['ex-141'] = { id: 'exl-141', planId: 'ex-141', ts: '', status: 'partial', reason: 'fatigue', alternativeId: 'alt-mobility' };

export const mockExercisePlan = (day?: number): Promise<ExerciseItem[]> =>
  delay(items.filter((p) => day === undefined || p.day === day).map((p) => ({ ...p, log: logs[p.id] ?? null })));

export const mockAlternatives = (planId: string, reason: string): Promise<AlternativesResult> => {
  const p = items.find((x) => x.id === planId);
  let list = (p?.alternatives ?? []).map((id) => alts[id]).filter(Boolean);
  if (reason === 'equipment') list = list.filter((a) => a.equipment?.id !== p?.equipmentId);
  if (reason === 'fatigue' || reason === 'pain') {
    list = [...list].sort((a, b) => rank[a.intensity] - rank[b.intensity] || a.durationMin - b.durationMin);
  }
  const options: ExerciseAlternativeOption[] = list.map((a) => ({
    id: a.id, type: a.type, durationMin: a.durationMin, intensity: a.intensity, equipmentId: a.equipment?.id ?? null,
    equipment: a.equipment, equipmentStatus: a.equipment?.status ?? null,
    why: [
      ...(rank[a.intensity] < rank[p?.intensity ?? 'hard'] ? ['Lighter'] : []),
      a.equipment ? `Uses ${a.equipment.name}, ${a.equipment.status === 'low' ? 'low stock' : 'available'}` : 'No equipment needed',
    ],
  }));
  return delay(
    options.length ? { alternatives: options } : { alternatives: [], message: `No alternative available without ${p?.equipment?.name ?? 'this equipment'}. Try rescheduling.` },
  );
};

export const mockLogExercise = (b: ExerciseLogBody): Promise<ExerciseLog> => {
  const entry: ExerciseLog = {
    id: `exl-mock-${Date.now()}`, planId: b.planId, ts: new Date().toISOString(), status: b.status,
    reason: b.reason ?? null, alternativeId: b.alternativeId ?? null,
  };
  logs[b.planId] = entry;
  return delay(entry);
};

// ---- today -----------------------------------------------------------------------------
export const mockTodayPlan = (): Promise<TodayPlan> => {
  const exLog = logs['ex-142'];
  return delay({
    missionDay: TODAY,
    fatigueFlag: true,
    items: [
      { kind: 'checkin', title: 'Daily check-in', status: 'todo', route: '/daily#checkin' },
      { kind: 'attention', title: 'Attention test', status: 'done', route: '/attention' },
      {
        kind: 'exercise', title: 'Exercise: ARED resistance session (full body), 60 min (example plan)',
        status: !exLog ? 'todo' : exLog.status === 'skipped' ? 'skipped' : 'done', route: '/daily#exercise',
      },
      { kind: 'sleep_rating', title: "Rate last night's sleep", status: nights[nights.length - 1].selfQuality ? 'done' : 'todo', route: '/daily#sleep' },
    ],
  });
};

export const mockFatigueAlert = (): Promise<Alert[]> =>
  delay([
    {
      id: 'al-mock-fat', ruleId: 'R-FAT-01', level: 'review', ts: '', status: 'new',
      title: 'Possible fatigue pattern: short sleep and slower reaction time',
      whatChanged: '', dataUsed: [], missing: ["Today's check-in"], possibleFactors: [], nextSteps: [], sources: [],
    },
  ]);
