// Local copies of the support contract types (docs/proposals/support-contracts.md, N1–N5).
// Switch to shared/types/contracts.ts once Haya merges them.
import type { Report } from '../../../shared/types/contracts';

export type ReportItemKind = 'alert' | 'cmo_question' | 'note';
export type SourceFeature = 'monitoring' | 'daily' | 'assistant' | 'relax';

export interface ReportItem {
  id: string;
  kind: ReportItemKind;
  refId?: string | null;
  title: string;
  text: string;
  sourceFeature: SourceFeature;
  createdTs: string;
  reportId?: string | null;
}

export type SectionId =
  | 'summary'
  | 'alerts'
  | 'vitals'
  | 'cabin'
  | 'sleep'
  | 'attention'
  | 'exercise'
  | 'checkins'
  | 'relax'
  | 'items'
  | 'radiation';

export const SECTIONS: { id: SectionId; label: string; defaultOn: boolean; note?: string }[] = [
  { id: 'summary', label: 'Summary', defaultOn: true },
  { id: 'alerts', label: 'Alerts', defaultOn: true },
  { id: 'vitals', label: 'Vital signs', defaultOn: true },
  { id: 'cabin', label: 'Cabin conditions', defaultOn: false },
  { id: 'sleep', label: 'Sleep', defaultOn: true },
  { id: 'attention', label: 'Attention checks', defaultOn: true },
  { id: 'exercise', label: 'Exercise', defaultOn: false },
  { id: 'checkins', label: 'Check-ins', defaultOn: false, note: 'Only included with permission' },
  { id: 'relax', label: 'Relaxation sessions', defaultOn: false },
  { id: 'items', label: 'Items for the CMO', defaultOn: true },
  { id: 'radiation', label: 'Radiation', defaultOn: false },
];

export interface ReportOut extends Report {
  sentTs?: string | null;
}

export interface CommsStatus {
  connected: boolean;
  simulatedWindow: boolean;
  nextWindowTs: string;
  windowDurationMin: number;
  queuedCount: number;
  signalDelaySec: number;
  lastWindowTs?: string | null;
}