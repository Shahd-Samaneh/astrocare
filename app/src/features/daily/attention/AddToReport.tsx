// Owner: Shahd. "Add to report" for one attention result.
// Uses Noura's report items API (POST /api/reports/items). If that endpoint isn't there
// (404 on the probe or on the POST), the button is hidden. Only test numbers are sent:
// never a private check-in note.
import { Check, FilePlus } from 'lucide-react';
import { useState } from 'react';
import { ApiError, api, useApi } from '../../../shared/api/client';
import { Button } from '../../../shared/components';
import type { TestResult } from '../api.attention';
import styles from './Attention.module.css';

const ITEMS = '/reports/items';

/** One line with median, lapses, % vs baseline and sleepiness. Exported for reuse. */
// eslint-disable-next-line react-refresh/only-export-components
export function reportLine(r: TestResult): string {
  const t = r.test;
  const parts = [
    `Median ${Math.round(t.medianMs)} ms`,
    `${t.lapses} lapse${t.lapses === 1 ? '' : 's'}`,
    r.pctVsBaseline == null
      ? 'no baseline yet'
      : `${r.pctVsBaseline > 0 ? '+' : ''}${r.pctVsBaseline.toFixed(0)} % vs baseline${
          r.baseline.building ? ' (baseline still building)' : ''
        }`,
    t.sleepinessKss != null ? `sleepiness ${t.sleepinessKss}/9 (KSS)` : 'sleepiness not rated',
  ];
  const kind = `${t.mode === 'extended' ? 'extended, experimental' : 'quick'}, ${t.context}`;
  return `${parts.join(', ')} (${kind} test). Experimental, does not decide fitness for duty.`;
}

export function AddToReport({ result }: { result: TestResult }) {
  const probe = useApi<unknown[]>(`${ITEMS}?pending=true`);
  const [state, setState] = useState<'idle' | 'busy' | 'added' | 'missing' | 'error'>('idle');
  const [message, setMessage] = useState<string>();

  if (state === 'missing' || (probe.error && probe.error.status === 404)) return null;
  if (probe.loading && !probe.data) return null;

  const add = async () => {
    setState('busy');
    try {
      const date = new Date(result.test.ts).toLocaleDateString('en-GB', {
        day: 'numeric',
        month: 'short',
        year: 'numeric',
      });
      await api.post(ITEMS, {
        kind: 'note',
        title: `Attention check ${date}`,
        text: reportLine(result),
        sourceFeature: 'daily',
        refId: result.test.id,
      });
      setState('added');
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) {
        setState('missing');
        return;
      }
      setMessage(e instanceof ApiError ? e.message : String(e));
      setState('error');
    }
  };

  return (
    <span className={styles.row}>
      {state === 'added' ? (
        <span className={styles.added} role="status">
          <Check size={16} aria-hidden /> Added ✓
        </span>
      ) : (
        <Button
          variant="secondary"
          onClick={add}
          disabled={state === 'busy'}
          icon={<FilePlus size={16} />}
        >
          {state === 'busy' ? 'Adding…' : 'Add to report'}
        </Button>
      )}
      {state === 'error' && (
        <span className={styles.meta} role="alert">
          Not added: {message}
        </span>
      )}
    </span>
  );
}
