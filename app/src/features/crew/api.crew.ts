// Owner: Shahd. Types and calls for Crew alerts (R-LOC-01: possible loss of consciousness).
// Local API only (relative /api paths through the shared client). No remote URLs.
// Feature-owned types, like api.attention.ts: not in shared/types/contracts.ts.
import { api } from '../../shared/api/client';

export type EmergencyStatus = 'watch' | 'emergency' | 'resolved';
export type Outcome = 'responded' | 'sensor_issue' | 'medical_event' | 'other';
export type CrewRole = 'cmo' | 'commander';
export type SignalKind = 'hr_change' | 'chest_gap' | 'no_motion' | 'low_spo2';

export interface LocSignal {
  kind: SignalKind;
  label: string;
  ts: string;
  detail: string;
}

export interface TimelineStep {
  ts: string;
  /** detected | check_shown | responded | no_response | escalated | report_queued | ack_cmo | ack_commander | resolved */
  step: string;
  actor: 'system' | 'crew' | 'cmo' | 'commander' | string;
  text: string;
}

export interface CrewEmergency {
  id: string;
  alertId: string;
  astronautId: string;
  crewName: string;
  status: EmergencyStatus;
  /** The alert stays 'urgent' in the shared contract; `emergency` marks the emergency class. */
  alertLevel: 'urgent';
  emergency: boolean;
  detectedTs: string;
  openedTs: string;
  deadlineTs: string;
  respondedTs: string | null;
  escalatedTs: string | null;
  ackCmoTs: string | null;
  ackCommanderTs: string | null;
  acknowledged: boolean;
  resolvedTs: string | null;
  outcome: Outcome | null;
  note: string | null;
  signals: LocSignal[];
  missing: string[];
  timeline: TimelineStep[];
  reportItemId: string | null;
  reportNote: string | null;
}

export interface CrewEmergencies {
  serverTs: string;
  demo: boolean;
  responseSeconds: number;
  open: CrewEmergency[];
  history: CrewEmergency[];
}

export const CREW_PATH = '/crew/emergencies';
export const EXPERIMENTAL_LABEL = 'Experimental. Not a medical device.';

export const OUTCOME_LABEL: Record<Outcome, string> = {
  responded: 'Crew member responded',
  sensor_issue: 'Sensor issue',
  medical_event: 'Medical event',
  other: 'Other',
};

export const ROLE_LABEL: Record<CrewRole, string> = { cmo: 'CMO', commander: 'Commander' };

const enc = encodeURIComponent;
export const respond = (id: string) => api.post<CrewEmergency>(`${CREW_PATH}/${enc(id)}/respond`);
export const acknowledge = (id: string, role: CrewRole, note?: string) =>
  api.post<CrewEmergency>(`${CREW_PATH}/${enc(id)}/ack`, note ? { role, note } : { role });
export const resolveEmergency = (
  id: string,
  outcome: Outcome,
  note: string,
  role: CrewRole = 'cmo',
) => api.post<CrewEmergency>(`${CREW_PATH}/${enc(id)}/resolve`, { outcome, note, role });
export const simulateLoc = () =>
  api.post<{ alertId: string; emergencyId: string | null }>('/crew/demo/loc');
