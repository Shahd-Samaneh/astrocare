// Types for Nadia's part of Daily health (sleep, exercise, today plan).
// They mirror the JSON of server/features/daily/{sleep,exercise,today}.py and
// docs/daily-contract.md §2. Fields marked "extra" are optional additions to the contract.
import type { ExerciseLog, ExerciseReason, ResourceStatus } from '../../shared/types/contracts';

export interface SleepNight {
  id: string; // extra: lets the UI PATCH the rating
  date: string; // YYYY-MM-DD (UTC) of the wake-up
  missionDay: number;
  hours: number;
  awakenings: number;
  selfQuality: number | null;
  short: boolean; // extra: hours < sleep_short_hours (threshold stays on the server)
}

export interface SleepSummary {
  nights: SleepNight[]; // oldest first
  personalAvgHours: number | null;
  shortThresholdHours?: number | null; // extra
  lastNight: SleepNight | null;
}

export type Intensity = 'light' | 'moderate' | 'hard';
export type EquipmentStatus = ResourceStatus | 'unknown';

export interface EquipmentRef {
  id: string;
  name: string;
  status: EquipmentStatus;
}

export interface ExerciseItem {
  id: string;
  day: number;
  type: string;
  durationMin: number;
  intensity: Intensity;
  equipmentId: string | null;
  equipment: EquipmentRef | null;
  equipmentStatus: EquipmentStatus | null;
  available: boolean;
  alternatives: string[]; // ids of other items
  log: (ExerciseLog & { alternativeType?: string }) | null; // extra: latest log of this item
}

export interface ExerciseAlternativeOption {
  id: string;
  type: string;
  durationMin: number;
  intensity: Intensity;
  equipmentId: string | null;
  equipment: EquipmentRef | null;
  equipmentStatus: EquipmentStatus | null;
  why: string[]; // e.g. ["Lighter", "Uses Cycle ergometer, available"]
}

export interface AlternativesResult {
  alternatives: ExerciseAlternativeOption[];
  message?: string;
}

export interface ExerciseLogBody {
  planId: string;
  status: 'done' | 'partial' | 'skipped';
  reason?: ExerciseReason;
  alternativeId?: string;
}

export type TodayKind = 'checkin' | 'attention' | 'exercise' | 'sleep_rating';

export interface TodayItem {
  kind: TodayKind;
  title: string;
  status: 'todo' | 'done' | 'skipped';
  route: string;
}

export interface TodayPlan {
  missionDay: number;
  items: TodayItem[];
  fatigueFlag: boolean;
}

export interface ManualSleepBody {
  start: string; // ISO 8601 UTC
  end: string;
  awakenings: number;
  selfQuality?: number;
}
