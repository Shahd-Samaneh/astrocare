// Assistant API calls. Relative /api paths only (same origin, localhost): never a remote host.
import { api, API_BASE, ApiError } from '../../../shared/api/client';
import type { AssistantAnswer, AssistantPermissions, NewReportItem } from './types';

export const askAssistant = (question: string) => api.post<AssistantAnswer>('/assistant/ask', { question });

export type StreamEvent =
  | { type: 'token'; text: string }
  | { type: 'reset' }
  | { type: 'final'; answer: AssistantAnswer; stats?: { model?: string | null; firstTokenMs?: number | null } };

/**
 * POST /api/assistant/ask/stream and call `onEvent` for every NDJSON event as it arrives.
 * Resolves with the final answer. If streaming is not available (older server), falls back
 * to the plain /ask call.
 */
export async function askAssistantStream(
  question: string,
  onEvent: (ev: StreamEvent) => void,
  signal?: AbortSignal,
): Promise<AssistantAnswer> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}/assistant/ask/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question }),
      signal,
    });
  } catch (err) {
    if ((err as Error).name === 'AbortError') throw err;
    throw new ApiError(0, 'Local service unreachable');
  }
  if (res.status === 404 || res.status === 405 || !res.body) {
    const answer = await askAssistant(question);
    onEvent({ type: 'final', answer });
    return answer;
  }
  if (!res.ok) throw new ApiError(res.status, `HTTP ${res.status}`);

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let final: AssistantAnswer | undefined;
  const handle = (line: string) => {
    if (!line.trim()) return;
    const ev = JSON.parse(line) as StreamEvent;
    if (ev.type === 'final') final = ev.answer;
    onEvent(ev);
  };
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let nl = buffer.indexOf('\n');
    while (nl >= 0) {
      handle(buffer.slice(0, nl));
      buffer = buffer.slice(nl + 1);
      nl = buffer.indexOf('\n');
    }
  }
  handle(buffer + decoder.decode());
  if (!final) throw new ApiError(0, 'The answer stream ended early');
  return final;
}

/** Ask the backend to load the local models into memory (best effort, ignore failures). */
export const warmUpAssistant = () => api.post<{ ok: boolean }>('/assistant/warmup').catch(() => undefined);

export const getPermissions = () => api.get<AssistantPermissions>('/assistant/permissions');

// shared/api/client.ts has no `put` yet (proposal A4), so this one call uses fetch directly.
export async function putPermissions(patch: Partial<{ [G in keyof AssistantPermissions]: Partial<AssistantPermissions[G]> }>) {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}/assistant/permissions`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(patch),
    });
  } catch {
    throw new ApiError(0, 'Local service unreachable');
  }
  if (!res.ok) throw new ApiError(res.status, `HTTP ${res.status}`);
  return (await res.json()) as AssistantPermissions;
}

/** Noura's POST /api/reports/items (contracts §1): CMO questions and "Add to report" notes. */
export const addReportItem = (item: NewReportItem) => api.post<unknown>('/reports/items', item);
