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

export interface NextStepAction {
  label: string;
  route: string; // in-app route, e.g. "/attention?retest=al-123" ("{alertId}" = this alert's id)
}

export interface NextStep {
  text: string;
  resourceId?: string | null;
  availability?: Availability | null;
  lockedForCMO: boolean;
  action?: NextStepAction | null; // optional button; never shown for a CMO-locked step
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

/** A sourced limit from config/thresholds.yaml (null bound = no limit on that side). */
export interface CabinLimit {
  min: number | null;
  max: number | null;
  unit: string;
  /** Set when the limit applies to an average (co2: 1-hour average). */
  windowMinutes: number | null;
  source: string;
  /** Short form for the screen, e.g. "NASA-STD-3001 [V2 6013]". */
  sourceLabel: string;
  /** Name of the range when it has one, e.g. "Comfort zone" ([V2 6013]). */
  name: string | null;
  /** Wider [V2 6012] crew-health limit: display context only, no rule uses it. */
  healthMin: number | null;
  healthMax: number | null;
  healthSourceLabel: string | null;
}

export interface CabinLatest {
  metric: CabinMetric;
  value: number | null;
  unit: string;
  ts: string | null;
  status: 'usual' | 'above_usual' | 'below_usual' | 'missing';
  ageMinutes: number | null;
  /** Same rule as vitals: no reading for longer than stale_minutes. */
  stale: boolean;
  /** Only present when thresholds.yaml has a numeric limit with a real source. */
  limit: CabinLimit | null;
}

export interface BodySystem {
  id: string;
  status: 'stable' | 'review' | 'no_data';
  text: string;
  alertId: string | null;
  /** Short qualifier after the status, e.g. "within limit" (radiation). */
  statusLabel?: string | null;
  /** The value is a simulated estimate, not a measurement (radiation). */
  simulated?: boolean;
  /** One line under the status: why the system is tracked this way (bone & muscle). */
  reason?: string | null;
}

/** GET /bone/estimate: months in flight × NASA's average bone loss per month. Illustrative only. */
export interface BoneEstimate {
  available: boolean;
  missionDay: number;
  monthsInFlight: number;
  lossPctPerMonthMin: number | null;
  lossPctPerMonthMax: number | null;
  estimatedLossPctMin: number | null;
  estimatedLossPctMax: number | null;
  source: string | null;
  label: string;
  note: string;
  sourceScope: string;
  why: string;
}

/** GET /radiation/estimate: mission day × MSL RAD cruise rate, against the NASA career limit. */
export interface RadiationEstimate {
  available: boolean;
  missionDay: number;
  rateMsvPerDay: number | null;
  cumulativeMsv: number | null;
  careerLimitMsv: number | null;
  pctOfLimit: number | null;
  withinLimit: boolean | null;
  label: string;
  source: Source;
  rateSource: string | null;
  rateSourceLabel: string | null;
  limitSource: string | null;
  limitSourceLabel: string | null;
  note: string;
  scopeNote: string;
  comparison: string;
  comparisonSource: string;
}

/** GET/POST /vision/checks: one near-vision card + Amsler grid self-check for one eye (no sensor). */
export interface VisionCheck {
  id: string;
  ts: string;
  eye: 'left' | 'right' | 'both';
  /** Smallest line read comfortably at arm's length; line 1 is the largest text. */
  nearVisionSmallestLine: number;
  /** Any grid lines looked wavy, blurred or missing. */
  amslerChanged: boolean;
  notes: string | null;
  source: 'self' | 'simulated';
}

export interface VisionCheckIn {
  eye: VisionCheck['eye'];
  nearVisionSmallestLine: number;
  amslerChanged: boolean;
  notes?: string | null;
}

export interface VisionEyeResult {
  eye: 'left' | 'right';
  baseline: VisionCheck | null;
  latest: VisionCheck | null;
  /** > 0 = a larger line (fewer lines read) than at baseline. */
  linesMoved: number | null;
  linesChanged: boolean;
  gridChanged: boolean;
}

/** GET /vision/summary: latest self-check vs the first (baseline) check. Never a diagnosis. */
export interface VisionSummary {
  status: 'stable' | 'review' | 'no_data';
  changed: boolean;
  due: boolean;
  /** "Same as baseline", or the changes joined with "; ". */
  result: string;
  changes: string[];
  eyes: VisionEyeResult[];
  lastTs: string | null;
  lastMissionDay: number | null;
  baselineTs: string | null;
  baselineMissionDay: number | null;
  lineDropMin: number;
  dueDays: number;
  linesOnCard: number;
  disclaimer: string;
  why: string;
  sourceRef: string;
  sourceTitle: string;
}
