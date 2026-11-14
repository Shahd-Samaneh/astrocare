// Local copies of the assistant contract types (docs/proposals/support-contracts.md, A1–A3).
// Switch to imports from shared/types/contracts.ts once Haya merges them.

export type RefusalReason = 'medication' | 'diagnosis';
// llm: local model; fallback: template (model off / too slow);
// alert / data: built on the device from the open alert / your data, without the model
export type AnswerMode = 'llm' | 'fallback' | 'alert' | 'data';

export interface AssistantSource {
  id: string;
  title: string;
  url?: string | null;
}

// One next step of the explained alert (mode 'alert' / alert template). `link` is an in-app path
// ("/daily#checkin"), only when the alert's NextStep has one: contracts.ts has no such field yet
// (proposal A13), so today every step is plain text.
export interface AnswerStep {
  text: string;
  link?: string | null;
  lockedForCMO: boolean;
}

export interface AssistantAnswer {
  answer: string;
  sources: AssistantSource[];
  missing: string[];
  refused: boolean;
  refusalReason?: RefusalReason | null;
  mode: AnswerMode;
  latencyMs: number;
  note?: string | null; // small notice under the badge (template / too slow / cut off)
  alertRuleId?: string | null; // mode 'alert': the rule the answer explains
  nextSteps?: AnswerStep[]; // mode 'alert' / alert template (missing on older servers)
}

export interface AssistantPermissions {
  assistant: { vitals: boolean; sleep: boolean; tests: boolean; exercise: boolean; checkins: boolean };
  report: { checkins: boolean };
}

export interface AssistantInfo {
  ollamaUrl: string;
  reachable: boolean;
  chatModel: string;
  embedModel: string;
  modelsAvailable: string[];
  modelSizeBytes?: number | null;
  ramBytes?: number | null;
  avgLatencyMs?: number | null;
  avgFirstTokenMs?: number | null;
  tokensPerSec?: number | null;
  answersLogged: number;
  chunksIndexed: number;
}

// Noura's report items (contracts §1), only the part the assistant sends.
export interface NewReportItem {
  kind: 'cmo_question' | 'note';
  title: string;
  text: string;
  sourceFeature: 'assistant';
  refId?: string;
}
