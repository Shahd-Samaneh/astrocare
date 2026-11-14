// Owner: Shahd. Optional pre-test question: Karolinska Sleepiness Scale (KSS, 1–9).
// Standard anchor labels are shown for 1, 3, 5, 7 and 9. A Skip button clears the answer.
// Citation (docs only, never a URL in app/src): Åkerstedt & Gillberg, 1990.
import { useId, useRef } from 'react';
import { Button } from '../../../shared/components';
import { KSS_ANCHORS } from './kss';
import styles from './Attention.module.css';

export interface SleepinessQuestionProps {
  /** undefined = not answered yet, null = skipped. */
  value: number | null | undefined;
  onChange: (v: number | null) => void;
}

export function SleepinessQuestion({ value, onChange }: SleepinessQuestionProps) {
  const id = useId();
  const group = useRef<HTMLDivElement>(null);
  const move = (delta: number) => {
    const v = Math.min(9, Math.max(1, (value ?? 0) + delta));
    onChange(v);
    group.current?.querySelectorAll<HTMLButtonElement>('[role="radio"]')[v - 1]?.focus();
  };

  return (
    <fieldset className={styles.kss}>
      <legend id={id} className={styles.kssLegend}>
        How sleepy do you feel right now? <span className={styles.optional}>(optional)</span>
      </legend>
      <div
        ref={group}
        role="radiogroup"
        aria-labelledby={id}
        className={styles.kssOptions}
        onKeyDown={(e) => {
          if (e.key === 'ArrowRight' || e.key === 'ArrowDown') {
            e.preventDefault();
            move(1);
          } else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
            e.preventDefault();
            move(-1);
          }
        }}
      >
        {Array.from({ length: 9 }, (_, i) => {
          const v = i + 1;
          const selected = value === v;
          const anchor = KSS_ANCHORS[v];
          return (
            <button
              key={v}
              type="button"
              role="radio"
              aria-checked={selected}
              aria-label={anchor ? `${v}: ${anchor}` : `${v}`}
              tabIndex={selected || (!value && v === 1) ? 0 : -1}
              className={`${styles.kssOption} ${selected ? styles.kssSelected : ''}`}
              onClick={() => onChange(v)}
            >
              <span className={styles.kssNum}>{v}</span>
              {anchor && <span className={styles.kssAnchor}>{anchor}</span>}
            </button>
          );
        })}
      </div>
      <div className={styles.row}>
        <Button variant="ghost" onClick={() => onChange(null)} aria-pressed={value === null}>
          {value === null ? 'Skipped' : 'Skip'}
        </Button>
        <span className={styles.meta}>Karolinska Sleepiness Scale, 1–9.</span>
      </div>
    </fieldset>
  );
}
