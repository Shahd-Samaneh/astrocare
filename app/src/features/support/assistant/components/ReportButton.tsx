// Sends one item to Noura's POST /api/reports/items (contracts §1). Until that endpoint exists
// it shows a message and the page keeps working. `done` / `onDone` let the chat remember that a
// turn was already added (so the button does not come back after navigating away and back).
import { useState, type ReactNode } from 'react';
import { Check, FilePlus2 } from 'lucide-react';
import { ApiError } from '../../../../shared/api/client';
import { Button } from '../../../../shared/components';
import type { ButtonVariant } from '../../../../shared/components/Button';
import { addReportItem } from '../api';
import { reportErrorMessage } from '../reportItems';
import type { NewReportItem } from '../types';
import styles from './ReportButton.module.css';

interface Props {
  item: NewReportItem;
  label: string;
  doneText: ReactNode;
  what: 'question' | 'answer';
  variant?: ButtonVariant;
  done?: boolean;
  onDone?: () => void;
}

export function ReportButton({ item, label, doneText, what, variant = 'secondary', done, onDone }: Props) {
  const [state, setState] = useState<'idle' | 'sending' | 'added' | 'error'>('idle');
  const [message, setMessage] = useState('');

  async function add() {
    setState('sending');
    try {
      await addReportItem(item);
      setState('added');
      onDone?.();
    } catch (e) {
      setState('error');
      setMessage(reportErrorMessage(e instanceof ApiError ? e.status : 0, (e as Error).message, what));
    }
  }

  if (done || state === 'added') {
    return (
      <p className={styles.done} role="status">
        <Check size={16} aria-hidden /> {doneText}
      </p>
    );
  }
  return (
    <div className={styles.wrap}>
      <Button variant={variant} icon={<FilePlus2 size={16} />} onClick={() => void add()} disabled={state === 'sending'}>
        {state === 'sending' ? 'Adding…' : label}
      </Button>
      {state === 'error' && (
        <p className={styles.error} role="alert">
          {message}
        </p>
      )}
    </div>
  );
}
