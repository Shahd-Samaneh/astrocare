// Owner: Shahd. Pure helpers for the crew emergency feed (no React), unit-tested in crew.test.mjs.
// Type-only import, so this file runs under `node --experimental-strip-types` in tests.
import type { CrewEmergencies, CrewEmergency } from './api.crew';

/**
 * Seconds left before a watch escalates. The server clock decides: we take the server time
 * of the last fetch and add the time that passed on this device since then.
 */
export function secondsLeft(
  deadlineTs: string,
  serverTs: string,
  fetchedAtMs: number,
  nowMs: number,
): number {
  const left = Date.parse(deadlineTs) - (Date.parse(serverTs) + (nowMs - fetchedAtMs));
  return Math.max(0, Math.ceil(left / 1000));
}

/** Open watch waiting for the crew member's "I'm OK" (the overlay shows for it). */
export function activeCheck(data: CrewEmergencies | undefined): CrewEmergency | undefined {
  return data?.open.find((e) => e.status === 'watch' && !e.respondedTs);
}

/** Escalated and nobody (CMO or Commander) has acknowledged yet: the red banner shows for these. */
export function unacknowledged(data: CrewEmergencies | undefined): CrewEmergency[] {
  return data?.open.filter((e) => e.status === 'emergency' && !e.acknowledged) ?? [];
}

/** Side-nav state: yellow dot while a watch is open, red count while emergencies are unacknowledged. */
export function navState(data: CrewEmergencies | undefined): {
  watch: boolean;
  emergencies: number;
} {
  return {
    watch: data?.open.some((e) => e.status === 'watch') ?? false,
    emergencies: unacknowledged(data).length,
  };
}

/** Poll fast while a countdown runs, slowly otherwise (all local). */
export function pollMs(data: CrewEmergencies | undefined): number {
  return data?.open.some((e) => e.status === 'watch') ? 1000 : 3000;
}

/** Every time on the Crew alerts page: local time, HH:MM:SS. */
export function timeText(ts: string | null | undefined): string {
  if (!ts) return '—';
  return new Date(ts).toLocaleTimeString('en-GB', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}

const ISO_IN_TEXT = /\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z/g;

/** Server texts carry ISO UTC times ("until 2026-11-15T04:18:40Z"): show them as local HH:MM:SS. */
export function localTimes(text: string): string {
  return text.replace(ISO_IN_TEXT, (iso) => timeText(iso));
}
