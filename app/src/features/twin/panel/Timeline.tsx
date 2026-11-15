// Mission timeline scrubber: a slider over the mission days, Play (about 0.8 s per day) and Today.
import { Pause, Play } from 'lucide-react';
import { useEffect, useRef } from 'react';
import { Button } from '../../../shared/components';
import { nextPlayDay, viewingLabel } from '../twinView';
import styles from './Panel.module.css';

export const PLAY_STEP_MS = 800;

export interface TimelineProps {
  from: number;
  today: number;
  /** null = today (live). */
  day: number | null;
  playing: boolean;
  loading: boolean;
  error: boolean;
  onDay: (day: number | null) => void;
  onPlaying: (playing: boolean) => void;
}

export function Timeline({ from, today, day, playing, loading, error, onDay, onPlaying }: TimelineProps) {
  const current = useRef(day);
  current.current = day;

  useEffect(() => {
    if (!playing) return;
    const id = window.setInterval(() => {
      const next = nextPlayDay(current.current, from, today);
      onDay(next);
      if (next === null) onPlaying(false); // reached today: back to live
    }, PLAY_STEP_MS);
    return () => window.clearInterval(id);
  }, [playing, from, today, onDay, onPlaying]);

  const value = day ?? today;
  const label = viewingLabel(day, today);
  const disabled = loading || error;

  return (
    <div className={styles.timeline} role="group" aria-label="Mission timeline">
      <div className={styles.timelineHead}>
        <span className={`${styles.viewing} ${day === null ? styles.live : styles.past}`} aria-live="polite">
          {label}
        </span>
        {loading && <span className={styles.muted}>Loading history…</span>}
        {error && <span className={styles.muted}>History unavailable right now.</span>}
      </div>
      <div className={styles.timelineRow}>
        <Button
          variant="secondary"
          onClick={() => {
            if (!playing && (day === null || day >= today)) onDay(from); // start from the first day
            onPlaying(!playing);
          }}
          disabled={disabled}
          aria-pressed={playing}
          icon={playing ? <Pause size={16} /> : <Play size={16} />}
        >
          {playing ? 'Pause' : 'Play'}
        </Button>
        <label className={styles.slider}>
          <span className="sr-only">Mission day</span>
          <input
            type="range"
            min={from}
            max={today}
            step={1}
            value={value}
            disabled={disabled}
            aria-valuetext={label}
            onChange={(e) => {
              onPlaying(false);
              const d = Number(e.target.value);
              onDay(d >= today ? null : d);
            }}
          />
          <span className={styles.scale} aria-hidden>
            <span>Day {from}</span>
            <span>Day {today}</span>
          </span>
        </label>
        <Button
          variant="ghost"
          onClick={() => {
            onPlaying(false);
            onDay(null);
          }}
          disabled={day === null && !playing}
        >
          Today
        </Button>
      </div>
    </div>
  );
}
