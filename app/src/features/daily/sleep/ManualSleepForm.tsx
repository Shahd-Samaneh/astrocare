// "Add sleep manually": validates in the browser with the same rules as the server
// (end after start, 0-16 h, awakenings >= 0, rating 1-5) and shows the server's message if it still refuses.
import { useId, useState, type FormEvent } from 'react';
import { Button } from '../../../shared/components';
import { errorText, logApi } from '../api.log';
import styles from './SleepSection.module.css';

const MAX_HOURS = 16;

interface Errors {
  start?: string;
  end?: string;
  awakenings?: string;
  rating?: string;
}

export function ManualSleepForm({ onSaved }: { onSaved: () => void }) {
  const uid = useId();
  const [start, setStart] = useState('');
  const [end, setEnd] = useState('');
  const [awakenings, setAwakenings] = useState('0');
  const [rating, setRating] = useState('');
  const [errors, setErrors] = useState<Errors>({});
  const [formError, setFormError] = useState<string>();
  const [saving, setSaving] = useState(false);

  function validate(): Errors {
    const e: Errors = {};
    const s = start ? new Date(start).getTime() : NaN;
    const f = end ? new Date(end).getTime() : NaN;
    if (Number.isNaN(s)) e.start = 'Enter when you went to sleep.';
    if (Number.isNaN(f)) e.end = 'Enter when you woke up.';
    if (!e.start && !e.end) {
      if (f <= s) e.end = 'Wake-up time must be after the time you went to sleep.';
      else if ((f - s) / 3_600_000 > MAX_HOURS) e.end = `A sleep session can be at most ${MAX_HOURS} hours.`;
    }
    const a = Number(awakenings);
    if (awakenings.trim() === '' || !Number.isInteger(a) || a < 0) e.awakenings = 'Awakenings must be a whole number, 0 or more.';
    if (rating !== '' && !(Number(rating) >= 1 && Number(rating) <= 5)) e.rating = 'Rating must be between 1 and 5.';
    return e;
  }

  async function submit(ev: FormEvent) {
    ev.preventDefault();
    setFormError(undefined);
    const found = validate();
    setErrors(found);
    if (Object.keys(found).length) return;
    setSaving(true);
    try {
      await logApi.addSleep({
        start: new Date(start).toISOString(),
        end: new Date(end).toISOString(),
        awakenings: Number(awakenings),
        ...(rating !== '' ? { selfQuality: Number(rating) } : {}),
      });
      setStart('');
      setEnd('');
      setAwakenings('0');
      setRating('');
      onSaved();
    } catch (e) {
      setFormError(errorText(e));
    } finally {
      setSaving(false);
    }
  }

  const field = (key: keyof Errors) => (errors[key] ? `${uid}-${key}-err` : undefined);

  return (
    <details className={styles.manual}>
      <summary className={styles.manualSummary}>Add sleep manually</summary>
      <form className={styles.form} onSubmit={submit} noValidate>
        <div className={styles.field}>
          <label htmlFor={`${uid}-start`}>Went to sleep</label>
          <input id={`${uid}-start`} type="datetime-local" value={start} onChange={(e) => setStart(e.target.value)}
            aria-invalid={!!errors.start} aria-describedby={field('start')} />
          {errors.start && <p id={`${uid}-start-err`} className={styles.err} role="alert">{errors.start}</p>}
        </div>
        <div className={styles.field}>
          <label htmlFor={`${uid}-end`}>Woke up</label>
          <input id={`${uid}-end`} type="datetime-local" value={end} onChange={(e) => setEnd(e.target.value)}
            aria-invalid={!!errors.end} aria-describedby={field('end')} />
          {errors.end && <p id={`${uid}-end-err`} className={styles.err} role="alert">{errors.end}</p>}
        </div>
        <div className={styles.field}>
          <label htmlFor={`${uid}-awakenings`}>Times you woke up</label>
          <input id={`${uid}-awakenings`} type="number" min={0} step={1} inputMode="numeric" value={awakenings}
            onChange={(e) => setAwakenings(e.target.value)} aria-invalid={!!errors.awakenings} aria-describedby={field('awakenings')} />
          {errors.awakenings && <p id={`${uid}-awakenings-err`} className={styles.err} role="alert">{errors.awakenings}</p>}
        </div>
        <div className={styles.field}>
          <label htmlFor={`${uid}-rating`}>How rested did you feel? (optional)</label>
          <select id={`${uid}-rating`} value={rating} onChange={(e) => setRating(e.target.value)}
            aria-invalid={!!errors.rating} aria-describedby={field('rating')}>
            <option value="">No rating</option>
            <option value="1">1: Very poor</option>
            <option value="2">2: Poor</option>
            <option value="3">3: Okay</option>
            <option value="4">4: Good</option>
            <option value="5">5: Very good</option>
          </select>
          {errors.rating && <p id={`${uid}-rating-err`} className={styles.err} role="alert">{errors.rating}</p>}
        </div>
        {formError && <p className={styles.err} role="alert">{formError}</p>}
        <div>
          <Button type="submit" disabled={saving}>{saving ? 'Saving…' : 'Save sleep'}</Button>
        </div>
      </form>
    </details>
  );
}
