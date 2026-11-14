// Source of truth for the data contract. Change both files together, via Haya.
// Mirror of server/core/models.py. JSON is camelCase; timestamps are ISO 8601 UTC strings ("...Z").

export type Quality = 'good' | 'low' | 'stale' | 'missing';
export type Source = 'dataset' | 'simulated' | 'manual' | 'sensor';
export type Metric = 'heart_rate' | 'spo2' | 'skin_temp' | 'bp_sys' | 'bp_dia' | 'resp_rate';
export type CabinMetric = 'co2' | 'cabin_temp' | 'noise' | 'humidity';
export type SensorStatus = 'connected' | 'disconnected' | 'low_battery';
export type AlertLevel = 'info' | 'review' | 'urgent';
export type AlertStatus = 'new' | 'ack' | 'recheck' | 'closed';
export type Availability = 'available' | 'out_of_stock' | 'expired' | 'allergy_conflict';
export type ResourceKind = 'medicine' | 'equipment';
export type ResourceStatus = 'available' | 'low' | 'out_of_stock' | 'expired';
export type ExerciseStatus = 'done' | 'partial' | 'skipped';
export type ExerciseReason = 'pain' | 'fatigue' | 'equipment' | 'time';
export type AudioMode = 'nature' | 'music' | 'none';
export type ReportStatus = 'draft' | 'ready' | 'queued' | 'sent';
/** Baseline keys: any vital metric plus derived personal baselines. */
export type BaselineKey = Metric | 'pvt_median_ms' | 'sleep_hours';

export const METRICS: Metric[] = ['heart_rate', 'spo2', 'skin_temp', 'bp_sys', 'bp_dia', 'resp_rate'];

export interface Reading {
  id: string;
  astronautId: string;
  metric: Metric;
  value: number;
  unit: string;
  ts: string;
  source: Source;
  quality: Quality;
}

export interface CabinReading {
  id: string;
  metric: CabinMetric;
  value: number;
  unit: string;
  ts: string;
  source: Source;
}

export interface Sensor {
  id: string;
  name: string;
  location: string;
  metrics: string[];
  status: SensorStatus;
  lastSeen: string;
}

export interface Baseline {
  mean: number;
  sd: number;
  n: number;
}

export interface Profile {
  id: string;
  name: string;
  missionDay: number;
  allergies: string[];
  currentMeds: string[];
  history: string[];
  baseline: Partial<Record<BaselineKey, Baseline>>;
}

export interface SleepSession {
  id: string;
  start: string;
  end: string;
  durationMin: number;
  awakenings: number;
  selfQuality?: number | null; // 1-5
  source: Source;
}

export interface CognitiveTest {
  id: string;
  ts: string;
  trialsMs: number[];
  medianMs: number;
  lapses: number;
  falseStarts: number;
}

export interface CheckIn {
  id: string;
  ts: string;
  mood?: number | null; // 1-5
  stress?: number | null; // 1-5
  notePrivate?: string | null;
  skipped: boolean;
}

export interface ExerciseAlternative {
  id: string;
  type: string;
  durationMin: number;
  equipmentId?: string | null;
  note?: string | null;
}

export interface ExercisePlan {
  id: string;
  day: number; // mission day
  type: string;
  durationMin: number;
  equipmentId?: string | null;
  alternatives: ExerciseAlternative[];
}

export interface ExerciseLog {
  id: string;
  planId: string;
  ts: string;
  status: ExerciseStatus;
  reason?: ExerciseReason | null;
  alternativeId?: string | null;
}

export interface Resource {
  id: string;
  kind: ResourceKind;
  name: string;
  qty: number;
  unit: string;
  expiry?: string | null;
  status: ResourceStatus;
  contraindicatedAllergies: string[];
}

export interface NextStep {
  text: string;
  resourceId?: string | null;
  availability?: Availability | null;
  lockedForCMO: boolean;
}

export interface Alert {
  id: string;
  ruleId: string;
  level: AlertLevel;
  ts: string;
  title: string;
  whatChanged: string;
  dataUsed: string[]; // reading ids
  missing: string[];
  possibleFactors: string[];
  nextSteps: NextStep[];
  status: AlertStatus;
  sources: string[];
}

export interface RelaxSession {
  id: string;
  ts: string;
  sceneId: string;
  audioMode: AudioMode;
  durationMin: number;
  stressBefore: number;
  stressAfter?: number | null;
}

export interface ReportSection {
  id: string;
  title: string;
  body: string;
}

export interface Report {
  id: string;
  createdTs: string;
  status: ReportStatus;
  sections: ReportSection[];
  filePath?: string | null;
}

export interface ActionLog {
  id: string;
  ts: string;
  actor: string;
  action: string;
  refId?: string | null;
}

export interface AppStatus {
  missionName: string;
  missionDay: number;
  met: string; // "DDD:HH:MM", e.g. "142:07:31"
  localMode: boolean;
  nextCommWindowTs: string;
  signalDelaySec: number;
  lastSyncTs: string;
  outboxCount: number;
  simulated: boolean;
  crewName: string;
  crewInitials: string;
}

/** GET /api/readings/latest (monitoring helper, not a stored entity). */
export interface LatestReading {
  metric: Metric;
  reading: Reading | null;
  quality: Quality;
  ageMinutes: number | null;
  sensorName: string | null;
  sensorStatus: SensorStatus | null;
}
