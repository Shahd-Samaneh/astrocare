// Calls for the Relax screen. Relative /api paths only.
import { api, API_BASE, ApiError } from '../../../shared/api/client';
import type { AudioMode } from '../../../shared/types/contracts';
import type { Duration, RelaxSession } from './types';

/** Saved at the START, so an interrupted session is kept without stressAfter. */
export const startSession = (body: {
  sceneId: string;
  audioMode: AudioMode;
  durationMin: Duration;
  stressBefore: number;
}) => api.post<RelaxSession>('/relax/sessions', body);

// shared api has no PATCH yet, so use fetch directly.
export async function finishSession(id: string, stressAfter: number): Promise<RelaxSession> {
  const res = await fetch(`${API_BASE}/relax/sessions/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ stressAfter }),
  });
  if (!res.ok) throw new ApiError(res.status, `HTTP ${res.status}`);
  return (await res.json()) as RelaxSession;
}