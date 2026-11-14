// Owner: Shahd. Daily check-in: mood 1–5, stress 1–5, optional private note, Save or Skip.
// Nadia embeds it in Daily log at #checkin:
//   import { CheckInPanel } from '../index';   <CheckInPanel />
// The private note is never sent to the assistant or reports unless the crew member allows it.
import { Check } from 'lucide-react';
import { useId, useRef, useState } from 'react';
import { ApiError, useApi } from '../../../shared/api/client';
import { Badge, Button, Card, ErrorState, LoadingState } from '../../../shared/components';
import { formatTime } from '../../../shared/utils/format';
import { paths, postCheckIn, type DailySummary } from '../api.attention';
import { NasaBasis } from '../common/NasaBasis';
import styles from './CheckInPanel.module.css';

const MOOD = ['Very low', 'Low', 'Okay', 'Good', 'Very good'];
const STRESS = ['Very calm', 'Calm', 'Some stress', 'High', 'Very high'];
const WHY =
  'Long, isolated missions can wear on mood and stress. A 20-second daily check-in makes slow changes visible ' +
  'and gives context to other signals, such as a slower reaction time.';

function Scale({
  label,
  options,
  value,
  onChange,
}: {
  label: string;
  options: string[];
  value: number | undefined;
  onChange: (v: number) => void;
}) {
  const id = useId();
  const group = useRef<HTMLDivElement>(null);
  // Roving focus: arrow keys change the value and move focus to the new option.
  const move = (delta: number) => {
    const v = Math.min(options.length, Math.max(1, (value ?? 0) + delta));
    onChange(v);
    group.current?.querySelectorAll<HTMLButtonElement>('[role="radio"]')[v - 1]?.focus();
  };
  return (
    <div className={styles.scale}>
      <span id={id} className={styles.scaleLabel}>
        {label}
      </span>
      <div
        ref={group}
        role="radiogroup"
        aria-labelledby={id}
        className={styles.options}
        onKeyDown={(e) => {
          if (e.key === 'ArrowRight' || e.key === 'ArrowUp') {
            e.preventDefault();
            move(1);
          } else if (e.key === 'ArrowLeft' || e.key === 'ArrowDown') {
            e.preventDefault();
            move(-1);
          }
        }}
      >
        {options.map((text, i) => {
          const v = i + 1;
          const selected = value === v;
          return (
            <button
              key={v}
              type="button"
              role="radio"
              aria-checked={selected}
              tabIndex={selected || (value === undefined && v === 1) ? 0 : -1}
              className={`${styles.option} ${selected ? styles.selected : ''}`}
              onClick={() => onChange(v)}
            >
              <span className={styles.optionNum}>{v}</span>
              <span className={styles.optionText}>{text}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}

export interface CheckInPanelProps {
  /** Anchor id for links such as /daily#checkin. */
  id?: string;
  /** Hide the "Why we track this" panel (e.g. when the page shows its own). */
  hideBasis?: boolean;
}

export function CheckInPanel({ id = 'checkin', hideBasis = false }: CheckInPanelProps) {
  const summary = useApi<DailySummary>(paths.summary(1));
  const [mood, setMood] = useState<number>();
  const [stress, setStress] = useState<number>();
  const [note, setNote] = useState('');
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  const noteId = useId();
  const hintId = useId();

  const today = summary.data?.checkins;
  const done = today && today.todayStatus !== 'todo' && !editing;

  const submit = async (skipped: boolean) => {
    setBusy(true);
    setError(undefined);
    try {
      await postCheckIn(
        skipped ? { skipped: true } : { mood, stress, notePrivate: note.trim() || undefined, skipped: false },
      );
      setEditing(false);
      setMood(undefined);
      setStress(undefined);
      setNote('');
      summary.reload();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const latest = today?.latest;

  return (
    <Card
      id={id}
      title="Daily check-in"
      subtitle="How are you today? About 20 seconds."
      actions={done ? <Badge variant="good">Done today ✓</Badge> : <Badge variant="missing">Not done today</Badge>}
      className={styles.card}
    >
      {summary.loading && !summary.data ? (
        <LoadingState />
      ) : summary.error ? (
        <ErrorState message={summary.error.message} onRetry={summary.reload} />
      ) : done ? (
        <div className={styles.done} role="status">
          <p className={styles.doneTitle}>
            <Check size={18} aria-hidden /> Done today ✓
          </p>
          {latest && (
            <p className={styles.meta}>
              {latest.skipped
                ? `Skipped at ${formatTime(latest.ts)}.`
                : `At ${formatTime(latest.ts)}: mood ${latest.mood} (${MOOD[(latest.mood ?? 1) - 1]}), stress ${latest.stress} (${STRESS[(latest.stress ?? 1) - 1]}).`}
            </p>
          )}
          <div>
            <Button variant="secondary" onClick={() => setEditing(true)}>
              Add another check-in
            </Button>
          </div>
        </div>
      ) : (
        <form
          className={styles.form}
          onSubmit={(e) => {
            e.preventDefault();
            void submit(false);
          }}
        >
          <Scale label="Mood" options={MOOD} value={mood} onChange={setMood} />
          <Scale label="Stress" options={STRESS} value={stress} onChange={setStress} />
          <div className={styles.field}>
            <label htmlFor={noteId} className={styles.scaleLabel}>
              Private note (optional)
            </label>
            <textarea
              id={noteId}
              className={styles.textarea}
              value={note}
              maxLength={2000}
              rows={3}
              onChange={(e) => setNote(e.target.value)}
              aria-describedby={hintId}
            />
            <p id={hintId} className={styles.hint}>
              Private: not shared with the assistant or reports unless you allow it.
            </p>
          </div>
          {error && (
            <p className={styles.error} role="alert">
              Not saved: {error}
            </p>
          )}
          <div className={styles.actions}>
            <Button type="submit" disabled={busy || mood === undefined || stress === undefined}>
              {busy ? 'Saving…' : 'Save'}
            </Button>
            <Button variant="ghost" disabled={busy} onClick={() => void submit(true)}>
              Skip today
            </Button>
            {editing && (
              <Button variant="ghost" disabled={busy} onClick={() => setEditing(false)}>
                Cancel
              </Button>
            )}
          </div>
        </form>
      )}
      {!hideBasis && <NasaBasis ids={['nasa-hrp-bmed-risk', 'nasa-hrp-hazards']} why={WHY} />}
    </Card>
  );
}
