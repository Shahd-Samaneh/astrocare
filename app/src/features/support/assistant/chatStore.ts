// The conversation, kept outside the page component so it survives navigating away and back.
// - module-level state: an answer that is still streaming keeps arriving while you are on
//   another page, and is there when you come back
// - mirrored to sessionStorage (this tab only, cleared when the tab closes) so a reload keeps
//   the finished turns; every storage call is wrapped in try/catch (private mode, quota, ...)
import { useSyncExternalStore } from 'react';
import { askAssistantStream } from './api';
import type { AssistantAnswer } from './types';

// After this long the UI says the local model is still working (proposal A5: assistant_slow_reply_ms).
const SLOW_REPLY_MS = 10000;
const STORAGE_KEY = 'astrocare.assistant.chat.v1';
const MAX_STORED_TURNS = 50;

export interface Turn {
  id: number;
  question: string;
  answer?: AssistantAnswer;
  partial?: string; // streamed text so far (before the final answer)
  firstTokenMs?: number | null;
  error?: string;
  interrupted?: boolean; // was still being answered when the page was reloaded
  reported?: boolean; // already added to the report (note or CMO question)
}

export interface ChatState {
  turns: Turn[];
  busy: boolean;
  slow: boolean;
  answered: number; // finished questions in this session (refreshes the measured-latency panel)
}

function load(): Turn[] {
  try {
    const raw = window.sessionStorage.getItem(STORAGE_KEY);
    const turns = raw ? (JSON.parse(raw) as Turn[]) : [];
    if (!Array.isArray(turns)) return [];
    // a question that was in flight cannot resume after a reload
    return turns.map((t) => (t.answer || t.error ? t : { ...t, partial: undefined, interrupted: true }));
  } catch {
    return [];
  }
}

function save(turns: Turn[]) {
  try {
    if (turns.length) {
      const keep = turns.slice(-MAX_STORED_TURNS).map((t) => ({ ...t, partial: undefined })); // undefined: not stored
      window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(keep));
    } else {
      window.sessionStorage.removeItem(STORAGE_KEY);
    }
  } catch {
    // storage off or full: the chat still works for this visit
  }
}

let state: ChatState = { turns: load(), busy: false, slow: false, answered: 0 };
let nextId = state.turns.reduce((m, t) => Math.max(m, t.id), 0) + 1;
const listeners = new Set<() => void>();

function set(patch: Partial<ChatState>) {
  const turnsChanged = patch.turns !== undefined && patch.turns !== state.turns;
  state = { ...state, ...patch };
  // streamed tokens are not stored (only the final turn is), so storage is not written per token
  if (turnsChanged && !state.turns.some((t) => t.partial !== undefined)) save(state.turns);
  listeners.forEach((l) => l());
}

function updateTurn(id: number, f: (t: Turn) => Turn) {
  set({ turns: state.turns.map((t) => (t.id === id ? f(t) : t)) });
}

export const getChat = () => state;

export function subscribeChat(listener: () => void) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function useChat(): ChatState {
  return useSyncExternalStore(subscribeChat, getChat, getChat);
}

export function markReported(id: number) {
  updateTurn(id, (t) => ({ ...t, reported: true }));
}

/** "Clear chat": drops every turn (not while an answer is still coming). */
export function clearChat() {
  if (state.busy) return;
  set({ turns: [] });
}

/** Ask one question. Returns false when it was not sent (empty, or another one is in progress). */
export function askQuestion(question: string): boolean {
  const q = question.trim();
  if (!q || state.busy) return false;
  const id = nextId++;
  set({ turns: [...state.turns, { id, question: q }], busy: true, slow: false });
  const timer = window.setTimeout(() => set({ slow: true }), SLOW_REPLY_MS);

  void (async () => {
    try {
      const answer = await askAssistantStream(q, (ev) => {
        if (ev.type === 'token') {
          window.clearTimeout(timer);
          if (state.slow) set({ slow: false });
          updateTurn(id, (x) => ({ ...x, partial: (x.partial ?? '') + ev.text }));
        } else if (ev.type === 'reset') {
          updateTurn(id, (x) => ({ ...x, partial: undefined }));
        } else {
          updateTurn(id, (x) => ({
            ...x,
            answer: ev.answer,
            partial: undefined,
            firstTokenMs: ev.stats?.firstTokenMs ?? null,
          }));
        }
      });
      updateTurn(id, (x) => (x.answer ? x : { ...x, answer, partial: undefined }));
    } catch (e) {
      updateTurn(id, (x) => ({ ...x, partial: undefined, error: (e as Error).message || 'Unknown error' }));
    } finally {
      window.clearTimeout(timer);
      set({ busy: false, slow: false, answered: state.answered + 1 });
    }
  })();
  return true;
}
