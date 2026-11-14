// Local copies until Haya merges proposal N6 (stress 1–10, scene media fields).
import type { AudioMode } from '../../../shared/types/contracts';

export interface Scene {
  id: string;
  name: string;
  description: string;
  audio: AudioMode[];
  image?: string | null; // local /api/relax/media/... URL, or null -> CSS gradient
  audioFiles: { nature?: string | null; music?: string | null };
}

export interface RelaxSession {
  id: string;
  ts: string;
  sceneId: string;
  audioMode: AudioMode;
  durationMin: number;
  stressBefore: number; // 1–10
  stressAfter?: number | null; // null = ended early / not rated
}

export const DURATIONS = [3, 5, 10] as const;
export type Duration = (typeof DURATIONS)[number];

export const AUDIO_LABEL: Record<AudioMode, string> = {
  nature: 'Nature sounds',
  music: 'Music',
  none: 'Silence',
};