// Digital twin API types (owner: Shahd). Mirror of server/features/twin/models.py.
// Twin-only view models: not part of the shared contract (shared/types/contracts.ts).
import type { SensorStatus } from '../../shared/types/contracts';

export type TwinStatus = 'ok' | 'watch' | 'review' | 'urgent' | 'nodata';
export type RegionId = 'brain' | 'eyes' | 'heart' | 'lungs' | 'bones' | 'radiation' | 'temperature' | 'sensors';
export type SensorAnchor = 'chest' | 'upperArm' | 'leftWrist';

export interface TwinValue {
  label: string;
  /** null = no data (never an invented value). */
  value: number | string | null;
  unit: string | null;
  /** Reading quality, or 'estimate' / 'illustrative' / 'self-check' for values that are not measurements. */
  quality?: string | null;
}

export interface TwinAlertRef {
  id: string;
  ruleId: string;
  title: string;
  level: string;
}

export interface TwinSource {
  id: string;
  title: string;
}

export interface TwinSensor {
  id: string;
  name: string;
  location: string;
  status: SensorStatus;
  lastSeen: string;
  /** null = not worn on the body (e.g. the blood pressure cuff in the medical kit): panel only. */
  anchor: SensorAnchor | null;
}

export interface TwinRegion {
  id: RegionId;
  label: string;
  status: TwinStatus;
  headline: string;
  values: TwinValue[];
  alerts: string[];
  alertRefs: TwinAlertRef[];
  route: string;
  routeLabel: string;
  sources: string[];
  sourceTitles: TwinSource[];
  estimate: boolean;
  pulseBpm: number | null;
  sensors: TwinSensor[] | null;
}

export interface TwinState {
  missionDay: number;
  simulated: boolean;
  generatedAt: string;
  disclaimer: string;
  regions: TwinRegion[];
}

export interface TwinDay {
  missionDay: number;
  isToday: boolean;
  asOf: string;
  regions: TwinRegion[];
}

export interface TwinTimeline {
  fromDay: number;
  toDay: number;
  today: number;
  simulated: boolean;
  disclaimer: string;
  days: TwinDay[];
}
