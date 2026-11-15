// Display rules for the digital twin (no React, no three.js) so they can be unit tested:
//   node --experimental-strip-types --test "app/src/features/twin/tests/*.test.mjs"
import type { RegionId, TwinRegion, TwinSensor, TwinStatus, TwinValue } from './types';

export const PATHS = {
  state: '/twin/state',
  timeline: '/twin/timeline',
} as const;

export const DISCLAIMER = 'Visual summary. Not a medical device.';
export const ESTIMATE_LABEL = 'Estimate · simulated';
export const NO_DATA = 'No data';

/** CSS token per status (read at runtime with getComputedStyle so 3D colours follow the theme). */
export const STATUS_TOKEN: Record<TwinStatus, string> = {
  ok: '--ok',
  watch: '--accent',
  review: '--warn',
  urgent: '--danger',
  nodata: '--text-faint',
};

export const STATUS_LABEL: Record<TwinStatus, string> = {
  ok: 'OK',
  watch: 'Watch',
  review: 'Review',
  urgent: 'Urgent',
  nodata: 'No data',
};

/** Shared Badge variant for each status (Badge has quality + alert-level variants). */
export const STATUS_BADGE: Record<TwinStatus, 'good' | 'info' | 'review' | 'urgent' | 'missing'> = {
  ok: 'good',
  watch: 'info',
  review: 'review',
  urgent: 'urgent',
  nodata: 'missing',
};

/** Short names used in the summary list, tooltips and the 3D aria description. */
export const REGION_SHORT: Record<RegionId, string> = {
  brain: 'Brain',
  eyes: 'Eyes',
  heart: 'Heart',
  lungs: 'Lungs',
  bones: 'Bones',
  radiation: 'Radiation',
  temperature: 'Temperature',
  sensors: 'Sensors',
};

const RANK: Record<TwinStatus, number> = { urgent: 0, review: 1, watch: 2, nodata: 3, ok: 4 };

/** Regions sorted most-severe first (stable within a status). */
export function bySeverity(regions: TwinRegion[]): TwinRegion[] {
  return regions
    .map((r, i) => [r, i] as const)
    .sort((a, b) => RANK[a[0].status] - RANK[b[0].status] || a[1] - b[1])
    .map(([r]) => r);
}

function plural(n: number, one: string, many = `${one}s`): string {
  return `${n} ${n === 1 ? one : many}`;
}

/** "2 systems to review, 1 sensor disconnected" (the sensors region is counted as sensors, not a system). */
export function overallSummary(regions: TwinRegion[]): string {
  const systems = regions.filter((r) => r.id !== 'sensors');
  const urgent = systems.filter((r) => r.status === 'urgent').length;
  const review = systems.filter((r) => r.status === 'review').length;
  const watch = systems.filter((r) => r.status === 'watch').length;
  const nodata = systems.filter((r) => r.status === 'nodata').length;
  const sensors = regions.find((r) => r.id === 'sensors')?.sensors ?? [];
  const down = sensors.filter((s) => s.status === 'disconnected').length;
  const low = sensors.filter((s) => s.status === 'low_battery').length;

  const parts: string[] = [];
  if (urgent) parts.push(`${plural(urgent, 'system')} urgent`);
  if (review) parts.push(`${plural(review, 'system')} to review`);
  if (watch) parts.push(`${plural(watch, 'system')} to watch`);
  if (nodata) parts.push(`${plural(nodata, 'system')} with no data`);
  if (down) parts.push(`${plural(down, 'sensor')} disconnected`);
  if (low) parts.push(`${plural(low, 'sensor')} on low battery`);
  return parts.length ? parts.join(', ') : 'All systems OK';
}

/** "33.9 °C", "5.1 h", "No data". */
export function formatValue(v: TwinValue): string {
  if (v.value === null || v.value === undefined || v.value === '') return NO_DATA;
  return v.unit ? `${v.value} ${v.unit}` : String(v.value);
}

/** Quality chip text, or null when nothing needs saying. */
export function qualityLabel(q: string | null | undefined): string | null {
  switch (q) {
    case 'stale':
      return 'Stale';
    case 'missing':
      return null; // the value already reads "No data"
    case 'low':
      return 'Low quality';
    case 'estimate':
      return ESTIMATE_LABEL;
    case 'illustrative':
      return 'Illustrative';
    case 'self-check':
      return 'Self-check';
    default:
      return null;
  }
}

/** On-body sensors get a marker number (1, 2, 3 …) in GET /sensors order; others get none. */
export function numberSensors(sensors: TwinSensor[]): { sensor: TwinSensor; marker: number | null }[] {
  let n = 0;
  return sensors.map((sensor) => ({ sensor, marker: sensor.anchor ? ++n : null }));
}

export function sensorStatusLabel(s: TwinSensor): string {
  const status = s.status === 'low_battery' ? 'low battery' : s.status;
  return s.anchor ? `${status} · ${s.location}` : `${status} · ${s.location} (not worn)`;
}

/** Heartbeat period in seconds for the 3D pulse, or null for no pulse. */
export function beatPeriod(bpm: number | null | undefined): number | null {
  if (bpm === null || bpm === undefined || !Number.isFinite(bpm) || bpm <= 0) return null;
  return 60 / bpm;
}

/** "Today (live)" or "Viewing day 136 (history)". */
export function viewingLabel(day: number | null, today: number): string {
  return day === null || day === today ? 'Today (live)' : `Viewing day ${day} (history)`;
}

/** Next day while playing; null = reached today (switch to live and stop). */
export function nextPlayDay(current: number | null, from: number, today: number): number | null {
  if (current === null || current >= today) return from;
  const next = current + 1;
  return next >= today ? null : next;
}

export function regionOpenLabel(r: Pick<TwinRegion, 'routeLabel'>): string {
  return `Open ${r.routeLabel}`;
}
