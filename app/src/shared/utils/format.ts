// Small formatting helpers shared by all features.
import { useEffect, useState } from 'react';
import type { Metric } from '../types/contracts';

export const METRIC_LABELS: Record<Metric, string> = {
  heart_rate: 'Heart rate',
  spo2: 'SpO₂',
  skin_temp: 'Skin temperature',
  bp_sys: 'Blood pressure (sys)',
  bp_dia: 'Blood pressure (dia)',
  resp_rate: 'Respiration rate',
};

/** 51600 s -> "14 h 20 m"; 252 s -> "4 m 12 s". */
export function formatDuration(totalSec: number): string {
  const s = Math.max(0, Math.round(totalSec));
  const d = Math.floor(s / 86400);
  const h = Math.floor((s % 86400) / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  if (d > 0) return `${d} d ${h} h`;
  if (h > 0) return `${h} h ${String(m).padStart(2, '0')} m`;
  return `${m} m ${String(sec).padStart(2, '0')} s`;
}

/** ISO timestamp -> "3 days ago", "6 h ago", "just now". */
export function relativeTime(iso: string, now = Date.now()): string {
  const diff = (now - new Date(iso).getTime()) / 1000;
  const future = diff < 0;
  const a = Math.abs(diff);
  let txt: string;
  if (a < 60) return 'just now';
  if (a < 3600) txt = `${Math.floor(a / 60)} min`;
  else if (a < 86400) txt = `${Math.floor(a / 3600)} h`;
  else {
    const d = Math.floor(a / 86400);
    txt = `${d} day${d === 1 ? '' : 's'}`;
  }
  return future ? `in ${txt}` : `${txt} ago`;
}

/** "142:07:31" + elapsed seconds -> "142:07:31:05" style ticking MET (DDD:HH:MM:SS). */
export function formatMet(met: string, elapsedSec: number): string {
  const [d, h, m] = met.split(':').map(Number);
  const total = ((d * 24 + h) * 60 + m) * 60 + Math.floor(elapsedSec);
  const dd = Math.floor(total / 86400);
  const hh = Math.floor((total % 86400) / 3600);
  const mm = Math.floor((total % 3600) / 60);
  const ss = total % 60;
  const p = (n: number) => String(n).padStart(2, '0');
  return `${String(dd).padStart(3, '0')}:${p(hh)}:${p(mm)}:${p(ss)}`;
}

export function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

/** Re-renders every `ms` and returns Date.now(). */
export function useNow(ms = 1000): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), ms);
    return () => window.clearInterval(id);
  }, [ms]);
  return now;
}
