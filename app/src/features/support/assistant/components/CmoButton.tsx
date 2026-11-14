// "Add the question to the report for the CMO" -> POST /api/reports/items (Noura, contracts §1).
// Until that endpoint exists it shows a message and the page keeps working.
import { useState } from 'react';
import { Check, FilePlus2 } from 'lucide-react';
import { ApiError } from '../../../../shared/api/client';
import { Button } from '../../../../shared/components';
import { addCmoQuestion } from '../api';
import styles from './CmoButton.module.css';

type State = 'idle' | 'sending' | 'added' | 'error';

export function CmoButton({ question }: { question: string }) {
  const [state, setState] = useState<State>('idle');
  const [message, setMessage] = useState('');

  async function add() {
    setState('sending');
    try {
      await addCmoQuestion(question);
      setState('added');
    } catch (e) {
      setState('error');
      const status = e instanceof ApiError ? e.status : 0;
      setMessage(
        status === 404 || status === 405
          ? 'The report service is not available yet, so the question was not added. Please try again later.'
          : `The question could not be added (${(e as Error).message}). Please try again.`,
      );
    }
  }

  if (state === 'added') {
    return (
      <p className={styles.done} role="status">
        <Check size={16} aria-hidden /> Added to the report for the CMO. It will be sent at the next comm window.
      </p>
    );
  }
  return (
    <div className={styles.wrap}>
      <Button variant="warn" icon={<FilePlus2 size={16} />} onClick={() => void add()} disabled={state === 'sending'}>
        {state === 'sending' ? 'Adding…' : 'Add the question to the report for the CMO'}
      </Button>
      {state === 'error' && (
        <p className={styles.error} role="alert">
          {message}
        </p>
      )}
    </div>
  );
}
